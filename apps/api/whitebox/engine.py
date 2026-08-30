from __future__ import annotations

import asyncio
import hashlib
import json
import difflib
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import (
    Artifact, BookAnalysisReport, DecisionSet, ExecutionNode, QualityReport, ReviewSet, Revision,
    SkillToolCall, TextDiff,
)
from .providers import DeepSeekProvider, ProviderError
from .registry import get_node_definition, is_model_node_type
from .storage import Storage


class RunCancelled(Exception):
    pass


class WaitingApproval(Exception):
    pass


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        self._subscribers.get(run_id, set()).discard(queue)

    def publish(self, run_id: str, payload: dict) -> None:
        for queue in self._subscribers.get(run_id, set()):
            queue.put_nowait(payload)


class WorkflowEngine:
    def __init__(
        self,
        storage: Storage,
        broker: EventBroker,
        deepseek: DeepSeekProvider | None = None,
        provider_resolver=None,
        project_root: Path | None = None,
    ):
        self.storage = storage
        self.broker = broker
        self.deepseek = deepseek or DeepSeekProvider()
        self.provider_resolver = provider_resolver
        self.project_root = project_root or storage.path.parent
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancelled: set[str] = set()

    def start(self, run_id: str) -> None:
        task = self.tasks.get(run_id)
        if task and not task.done():
            return
        self.tasks[run_id] = asyncio.create_task(self.execute(run_id))

    def resume(self, run_id: str) -> None:
        task = self.tasks.get(run_id)
        if task and not task.done():
            task.add_done_callback(lambda _: self.start(run_id))
            return
        self.start(run_id)

    async def emit(self, run_id: str, node_run_id: str | None, event_type: str, payload: dict) -> None:
        event = self.storage.append_event(str(uuid4()), run_id, node_run_id, event_type, payload)
        self.broker.publish(run_id, event.model_dump(mode="json"))

    async def execute(self, run_id: str) -> None:
        run = self.storage.get_run(run_id)
        if not run:
            return
        self.storage.update_run(run_id, "running")
        await self.emit(run_id, None, "run.started", {"graphHash": run.graph_hash})

        try:
            completed = {item.node_id: item for item in run.node_runs if item.status == "succeeded"}
            nodes = {node.id: node for node in run.snapshot.nodes}
            while len(completed) < len(nodes):
                if run_id in self.cancelled:
                    self.storage.update_run(run_id, "cancelled")
                    await self.emit(run_id, None, "run.cancelled", {})
                    return

                current = self.storage.get_run(run_id)
                if not current:
                    return
                node_runs = {item.node_id: item for item in current.node_runs}
                ready = [
                    node for node in nodes.values()
                    if node.id not in completed
                    and all(parent in completed for parent in node.dependencies)
                ]
                if not ready:
                    raise RuntimeError("执行图没有可运行节点")

                for node in ready:
                    node_run = node_runs[node.id]
                    artifact = await self._execute_node(run_id, node_run.id, node, completed)
                    refreshed = self.storage.get_run(run_id)
                    completed[node.id] = next(item for item in refreshed.node_runs if item.node_id == node.id)
                    await self.emit(
                        run_id, node_run.id, "node.succeeded",
                        {"nodeId": node.id, "artifactId": artifact.id},
                    )

            self.storage.update_run(run_id, "succeeded")
            await self.emit(run_id, None, "run.succeeded", {})
        except RunCancelled:
            self.storage.update_run(run_id, "cancelled")
            await self.emit(run_id, None, "run.cancelled", {})
        except WaitingApproval:
            return
        except Exception as exc:
            self.storage.update_run(run_id, "failed")
            await self.emit(run_id, None, "run.failed", {"error": str(exc)})

    async def _execute_node(
        self, run_id: str, node_run_id: str, node: ExecutionNode, completed: dict
    ) -> Artifact:
        ordered_sources = list(node.input_links.values()) or node.dependencies
        input_artifact_ids = [completed[parent].output_artifact_id for parent in ordered_sources]
        previous_snapshot = next((item.input_snapshot for item in self.storage.get_run(run_id).node_runs if item.id == node_run_id), None)
        input_snapshot = {**(previous_snapshot or {}), "artifact_ids": input_artifact_ids, "contents": [self.storage.get_artifact(item).content for item in input_artifact_ids if self.storage.get_artifact(item)]}
        attempt = next(
            item.attempt for item in self.storage.get_run(run_id).node_runs if item.id == node_run_id
        ) + 1
        now = datetime.now(UTC).isoformat()
        self.storage.update_node_run(
            node_run_id, status="running", attempt=attempt,
            input_artifact_ids=input_artifact_ids, input_snapshot=input_snapshot, started_at=now, error=None,
        )
        attempt_id = str(uuid4())
        self.storage.create_attempt(attempt_id, node_run_id, attempt, input_artifact_ids)
        await self.emit(run_id, node_run_id, "node.started", {"nodeId": node.id, "attempt": attempt})
        try:
            await self._cooperative_delay(run_id)
            if node.config.get("fail_if_text") and attempt <= int(node.config.get("fail_attempts", 0)):
                values = [str(node.config.get("default", ""))]
                values.extend(str(self.storage.get_artifact(item).content.get("text", "")) for item in input_artifact_ids if self.storage.get_artifact(item))
                if str(node.config["fail_if_text"]) in " ".join(values):
                    raise RuntimeError(str(node.config.get("failure_message", "模拟节点失败")))
            cache_key = self._cache_key(node, input_artifact_ids)
            definition = get_node_definition(node.type)
            cache_enabled = bool(
                definition
                and definition.execution.cache == "content-addressed"
                and not definition.execution.side_effect
            )
            cached = self.storage.get_cached_artifact(cache_key) if cache_enabled else None
            if cached:
                artifact = Artifact(
                    id=str(uuid4()), run_id=run_id, node_run_id=node_run_id,
                    schema_type=cached.schema_type, content=cached.content,
                    content_hash=cached.content_hash, parent_artifact_ids=input_artifact_ids,
                    created_at=datetime.now(UTC),
                )
                self.storage.save_artifact(artifact)
                self.storage.complete_attempt(
                    attempt_id, "cached", artifact.id, cached_from_artifact_id=cached.id
                )
                await self.emit(
                    run_id, node_run_id, "node.cached",
                    {"nodeId": node.id, "sourceArtifactId": cached.id, "artifactId": artifact.id},
                )
            else:
                schema_type = "writing.Draft@1"
                if is_model_node_type(node.type):
                    content, schema_type, skill_artifact_ids = await self._run_llm_node(
                        run_id, node_run_id, attempt_id, node, input_artifact_ids
                    )
                elif node.type in {"writing.revision_diff", "writing.quality_gate"}:
                    content, schema_type = self._run_writing_tool(node, input_artifact_ids)
                elif node.type == "core.approval":
                    approval = self.storage.get_approval_for_node(node_run_id)
                    if approval and approval.status == "approved":
                        content, schema_type = approval.model_dump(mode="json"), "core.Approval@1"
                    elif approval and approval.status == "rejected":
                        raise RuntimeError("人工审批已驳回")
                    else:
                        approval = self.storage.create_approval(
                            str(uuid4()), run_id, node_run_id, input_artifact_ids
                        )
                        self.storage.complete_attempt(attempt_id, "waiting_approval")
                        self.storage.update_node_run(
                            node_run_id, status="waiting_approval",
                            completed_at=datetime.now(UTC).isoformat(),
                        )
                        self.storage.update_run(run_id, "waiting_approval")
                        await self.emit(
                            run_id, node_run_id, "approval.requested",
                            {"approvalId": approval.id, "artifactIds": input_artifact_ids},
                        )
                        raise WaitingApproval
                elif node.type in {"writing.chapter_archive", "writing.state_proposal"}:
                    content, schema_type = self._run_archive_tool(node, input_artifact_ids)
                elif node.type == "flow.map":
                    content, schema_type, map_artifact_ids = await self._run_map_node(
                        run_id, node_run_id, node, input_artifact_ids
                    )
                else:
                    content = self._run_node(run_id, node, input_artifact_ids, attempt)
                    if node.type in {"workflow.input", "flow.join"}:
                        schema_type = "core.Text@1"
                    elif node.type == "flow.split":
                        schema_type = "core.List@1"
                    elif node.type == "reference.book_source":
                        schema_type = "core.Text@1"
                    elif node.type == "workflow.output":
                        parent = self.storage.get_artifact(input_artifact_ids[0])
                        schema_type = parent.schema_type if parent else "core.Artifact@1"
                    if node.type == "flow.join" and content.get("operation") == "join_list":
                        schema_type = "core.List@1"
                encoded = json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
                artifact = Artifact(
                    id=str(uuid4()), run_id=run_id, node_run_id=node_run_id,
                    schema_type=schema_type, content=content,
                    content_hash=hashlib.sha256(encoded).hexdigest(),
                    parent_artifact_ids=[
                        *input_artifact_ids, *locals().get("skill_artifact_ids", []),
                        *locals().get("map_artifact_ids", []),
                    ],
                    created_at=datetime.now(UTC),
                )
                self.storage.save_artifact(artifact)
                if cache_enabled:
                    self.storage.save_cache_entry(cache_key, artifact.id)
                self.storage.complete_attempt(attempt_id, "succeeded", artifact.id)
            self.storage.update_node_run(
                node_run_id, status="succeeded", output_artifact_id=artifact.id,
                completed_at=datetime.now(UTC).isoformat(),
            )
            return artifact
        except RunCancelled:
            self.storage.complete_attempt(attempt_id, "cancelled", error="运行已取消")
            self.storage.update_node_run(
                node_run_id, status="cancelled", completed_at=datetime.now(UTC).isoformat(),
                error="运行已取消",
            )
            raise
        except WaitingApproval:
            raise
        except Exception as exc:
            self.storage.complete_attempt(attempt_id, "failed", error=str(exc))
            self.storage.update_node_run(
                node_run_id, status="failed", completed_at=datetime.now(UTC).isoformat(), error=str(exc),
            )
            await self.emit(
                run_id, node_run_id, "node.failed",
                {"nodeId": node.id, "attempt": attempt, "error": str(exc)},
            )
            raise

    async def _cooperative_delay(self, run_id: str) -> None:
        for _ in range(5):
            if run_id in self.cancelled:
                raise RunCancelled
            await asyncio.sleep(0.09)

    def _run_node(self, run_id: str, node: ExecutionNode, input_artifact_ids: list[str], attempt: int) -> dict:
        fail_attempts = int(node.config.get("fail_attempts", 0))
        if node.config.get("fail") or attempt <= fail_attempts:
            raise RuntimeError(str(node.config.get("failure_message", "模拟节点失败")))
        if node.type == "mock.source":
            text = str(node.config.get("text", "一个尚未写下的故事。"))
            return {"text": text, "operation": "source"}
        if node.type == "mock.rewrite":
            parent = self.storage.get_artifact(input_artifact_ids[0])
            if not parent:
                raise RuntimeError(f"节点 {node.id} 缺少输入产物")
            instruction = str(node.config.get("instruction", "增强画面感"))
            return {
                "text": f"{parent.content['text']}\n\n[白盒改写：{instruction}]",
                "operation": "rewrite",
                "instruction": instruction,
            }
        if node.type == "flow.split":
            parent = self.storage.get_artifact(input_artifact_ids[0])
            if not parent:
                raise RuntimeError("Split 缺少文本输入")
            text = str(parent.content.get("text", ""))
            mode = str(node.config.get("mode", "paragraph"))
            if mode == "chapter":
                import re
                parts = [part for part in re.split(r"(?=^第[^\n]{1,40}[章节卷回].*$)", text, flags=re.MULTILINE) if part.strip()]
            elif mode == "heading":
                import re
                parts = [part for part in re.split(r"(?=^#{1,6}\s+)", text, flags=re.MULTILINE) if part.strip()]
            elif mode == "fixed":
                size = max(1, int(node.config.get("chunk_size", 12000)))
                parts = [text[index:index + size] for index in range(0, len(text), size)]
            else:
                parts = [part for part in text.split("\n\n") if part.strip()]
            return {"items": [{"index": index, "text": part} for index, part in enumerate(parts)], "mode": mode}
        if node.type == "workflow.input":
            if input_artifact_ids:
                parent = self.storage.get_artifact(input_artifact_ids[0])
                if not parent:
                    raise RuntimeError("Workflow Input 引用的 Artifact 不存在")
                return {**parent.content, "name": str(node.config.get("name", "input")), "operation": "workflow_input_bridge"}
            return {"text": str(node.config.get("default", "")), "name": str(node.config.get("name", "input")), "operation": "workflow_input"}
        if node.type == "reference.book_source":
            book = self.storage.get_reference_book(str(node.config.get("reference_book_id", "")))
            run = self.storage.get_run(run_id)
            project_id = run.snapshot.run_context.get("project_id") if run else None
            if not book or book.content_hash != node.config.get("content_hash"):
                raise RuntimeError("拆书参考书不存在或哈希不一致")
            if book.project_id != project_id:
                raise RuntimeError("拆书参考书不属于当前项目")
            return {"text": book.normalized_content, "reference_book_id": book.id, "content_hash": book.content_hash, "operation": "reference_book_source"}
        if node.type == "workflow.output":
            parent = self.storage.get_artifact(input_artifact_ids[0])
            if not parent: raise RuntimeError("Workflow Output 缺少输入")
            return {**parent.content, "output_name": str(node.config.get("name", "output"))}
        if node.type == "flow.join":
            parents = [self.storage.get_artifact(item) for item in input_artifact_ids]
            if len(parents) == 1 and parents[0] and isinstance(parents[0].content.get("items"), list):
                items = parents[0].content["items"]
                return {"items": items, "text": str(node.config.get("separator", "\n\n")).join(str(item.get("text", item)) for item in items), "operation": "join_list"}
            if len(parents) != 2 or any(item is None for item in parents):
                raise RuntimeError("Join 需要两个输入产物或一个列表")
            return {"text": str(node.config.get("separator", "\n\n")).join(str(parent.content.get("text", "")) for parent in parents), "operation": "join"}

    async def _run_map_node(
        self, run_id: str, node_run_id: str, node: ExecutionNode, input_artifact_ids: list[str]
    ) -> tuple[dict, str, list[str]]:
        parents = [self.storage.get_artifact(item) for item in input_artifact_ids]
        if len(parents) != 1 or not parents[0] or not isinstance(parents[0].content.get("items"), list):
            raise RuntimeError("Map 需要一个 List Artifact 输入")
        body = node.config.get("body_graph_snapshot")
        if not body:
            raise RuntimeError("Map Body 尚未冻结")
        body_nodes = {item["id"]: ExecutionNode.model_validate(item) for item in body["nodes"]}
        body_output_ids = [item for item in body["target_node_ids"] if item in body_nodes]
        if len(body_output_ids) != 1:
            raise RuntimeError("Map Body 必须有唯一输出目标")
        items = parents[0].content["items"]
        concurrency = max(1, min(8, int(node.config.get("concurrency", 1))))

        async def run_item(index: int, item) -> tuple[dict, str]:
            if run_id in self.cancelled:
                raise RunCancelled
            prefix = f"{node.id}[{index:04d}]"
            existing = [row for row in self.storage.get_run(run_id).node_runs if row.node_id.startswith(f"{prefix}/")]
            if existing and all(row.status == "succeeded" for row in existing):
                output_row = next((row for row in existing if row.node_id.endswith("/" + body_output_ids[0])), None)
                output_artifact = self.storage.get_artifact(output_row.output_artifact_id) if output_row and output_row.output_artifact_id else None
                if output_artifact:
                    return {"index": index, "text": output_artifact.content.get("text", ""), "artifact_id": output_artifact.id}, output_artifact.id
            id_map = {node_id: f"{prefix}/{node_id}" for node_id in body_nodes}
            completed: dict[str, object] = {}
            dynamic_nodes: dict[str, ExecutionNode] = {}
            for original_id, body_node in body_nodes.items():
                config = dict(body_node.config)
                if body_node.type == "workflow.input":
                    config["default"] = str(item.get("text", item) if isinstance(item, dict) else item)
                links = {port: id_map[source] for port, source in body_node.input_links.items()}
                dynamic_nodes[id_map[original_id]] = body_node.model_copy(
                    update={"id": id_map[original_id], "dependencies": [id_map[parent] for parent in body_node.dependencies], "input_links": links, "config": config}
                )
                self.storage.ensure_dynamic_node_run(
                    str(uuid4()), run_id, id_map[original_id], body_node.type,
                    {"item_index": index, "item": item},
                )
            # Use the just-created rows by their stable prefixed domain IDs.
            run_rows = self.storage.get_run(run_id).node_runs
            row_by_id = {row.node_id: row for row in run_rows}
            pending = set(dynamic_nodes)
            while pending:
                ready = [dynamic_nodes[item_id] for item_id in pending if all(parent in completed for parent in dynamic_nodes[item_id].dependencies)]
                if not ready:
                    raise RuntimeError("Map Body 执行图没有可运行节点")
                for child in ready:
                    artifact = await self._execute_node(run_id, row_by_id[child.id].id, child, completed)
                    completed[child.id] = self.storage.get_run(run_id).node_runs[[row.node_id for row in self.storage.get_run(run_id).node_runs].index(child.id)]
                    pending.remove(child.id)
            output_node_id = id_map[body_output_ids[0]]
            output_row = next(row for row in self.storage.get_run(run_id).node_runs if row.node_id == output_node_id)
            output_artifact = self.storage.get_artifact(output_row.output_artifact_id) if output_row.output_artifact_id else None
            if not output_artifact:
                raise RuntimeError("Map Body 没有输出产物")
            return {"index": index, "text": output_artifact.content.get("text", ""), "artifact_id": output_artifact.id}, output_artifact.id

        semaphore = asyncio.Semaphore(concurrency)

        async def limited(index: int, item) -> tuple[dict, str]:
            async with semaphore:
                return await run_item(index, item)

        pairs = await asyncio.gather(*(limited(index, item) for index, item in enumerate(items)), return_exceptions=True)
        failures = [pair for pair in pairs if isinstance(pair, Exception)]
        if failures:
            raise RuntimeError(f"Map 条目执行失败: {failures[0]}")
        pairs = [pair for pair in pairs if not isinstance(pair, Exception)]
        results = [pair[0] for pair in pairs]
        output_artifact_ids = [pair[1] for pair in pairs]
        return {"items": results, "count": len(results), "operation": "map"}, "core.List@1", output_artifact_ids

    def _run_writing_tool(self, node: ExecutionNode, input_artifact_ids: list[str]) -> tuple[dict, str]:
        parents = [self.storage.get_artifact(item) for item in input_artifact_ids]
        by_type = {item.schema_type: item for item in parents if item}
        if node.type == "writing.revision_diff":
            draft = by_type.get("writing.Draft@1")
            revision_artifact = by_type.get("writing.Revision@1")
            if not draft or not revision_artifact:
                raise RuntimeError("文本 Diff 需要 Draft 与 Revision 输入")
            revision = Revision.model_validate(revision_artifact.content)
            old_lines = draft.content["text"].splitlines()
            new_lines = revision.text.splitlines()
            diff_lines = list(difflib.unified_diff(
                old_lines, new_lines, fromfile="draft", tofile="revision", lineterm=""
            ))
            diff = TextDiff(
                unified_diff="\n".join(diff_lines),
                added_lines=sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")),
                removed_lines=sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---")),
                changed_finding_ids=[item.finding_id for item in revision.changes],
            )
            return diff.model_dump(mode="json"), "writing.TextDiff@1"
        review_artifact = by_type.get("writing.ReviewSet@1")
        decision_artifact = by_type.get("writing.DecisionSet@1")
        revision_artifact = by_type.get("writing.Revision@1")
        if not review_artifact or not decision_artifact or not revision_artifact:
            raise RuntimeError("质量门需要 ReviewSet、DecisionSet 与 Revision 输入")
        review = ReviewSet.model_validate(review_artifact.content)
        decisions = DecisionSet.model_validate(decision_artifact.content)
        revision = Revision.model_validate(revision_artifact.content)
        decisions.validate_references(review)
        draft_parent = next(
            (
                self.storage.get_artifact(parent_id)
                for parent_id in revision_artifact.parent_artifact_ids
                if self.storage.get_artifact(parent_id)
                and self.storage.get_artifact(parent_id).schema_type == "writing.Draft@1"
            ),
            None,
        )
        if draft_parent:
            revision.validate_against(draft_parent.content["text"], decisions)
        decision_map = {item.finding_id: item for item in decisions.decisions}
        changed_ids = {item.finding_id for item in revision.changes}
        unresolved = [
            item.id for item in review.findings
            if item.severity == "critical"
            and decision_map[item.id].verdict in {"accept", "modify"}
            and item.id not in changed_ids
        ]
        checks = [
            {"id": "decision_coverage", "passed": len(decisions.decisions) == len(review.findings)},
            {"id": "revision_attribution", "passed": not unresolved},
            {"id": "nonempty_revision", "passed": bool(revision.text.strip())},
        ]
        report = QualityReport(
            passed=all(item["passed"] for item in checks), checks=checks,
            unresolved_critical_findings=unresolved,
            summary="裁决与修订闭环通过" if not unresolved else "仍有严重意见未完成修订",
        )
        return report.model_dump(mode="json"), "writing.QualityReport@1"

    def _run_archive_tool(self, node: ExecutionNode, input_artifact_ids: list[str]) -> tuple[dict, str]:
        parents = [self.storage.get_artifact(item) for item in input_artifact_ids]
        by_type = {item.schema_type: item for item in parents if item}
        revision_artifact = by_type.get("writing.Revision@1")
        approval_artifact = by_type.get("core.Approval@1")
        if not revision_artifact or not approval_artifact:
            raise RuntimeError("归档节点需要 Revision 与 Approval 输入")
        if approval_artifact.content.get("status") != "approved":
            raise RuntimeError("只有人工批准后才能归档")
        if node.type == "writing.state_proposal":
            content = {
                "status": "proposed",
                "source_revision_artifact_id": revision_artifact.id,
                "operations": [
                    {
                        "id": f"OP{index}",
                        "category": "state",
                        "relative_name": "chapter-observations.json",
                        "pointer": "/observations",
                        "operation": "append",
                        "value": {
                            "type": "chapter_observation",
                            "summary": change["description"],
                            "finding_id": change["finding_id"],
                        },
                        "reason": "从已批准章节修订中提取观察",
                        "finding_id": change["finding_id"],
                    }
                    for index, change in enumerate(
                        revision_artifact.content.get("changes", []), start=1
                    )
                ],
                "summary": "根据已批准章节生成结构化状态变更提案，尚未应用",
            }
            return content, "writing.StatePatch@1"
        relative_path = str(node.config.get("chapter_path") or "demo/manuscript/chapter-0001.md")
        if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise RuntimeError("章节归档路径必须是项目内相对路径")
        target = self.project_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        text = revision_artifact.content["text"]
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
        if node.config.get("project_id") and node.config.get("chapter_number"):
            self.storage.advance_project_chapter(
                str(node.config["project_id"]), int(node.config["chapter_number"])
            )
        return {
            "path": relative_path,
            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "source_revision_artifact_id": revision_artifact.id,
            "archived_at": datetime.now(UTC).isoformat(),
        }, "writing.ArchivedChapter@1"

    async def _run_llm_node(
        self,
        run_id: str,
        node_run_id: str,
        attempt_id: str,
        node: ExecutionNode,
        input_artifact_ids: list[str],
    ) -> tuple[dict, str, list[str]]:
        parents = [self.storage.get_artifact(item) for item in input_artifact_ids]
        if any(item is None for item in parents):
            raise RuntimeError(f"节点 {node.id} 缺少输入产物")
        by_type = {item.schema_type: item for item in parents}
        model = str(node.config["model"])
        connection = node.config["connection_snapshot"]
        provider = self.provider_resolver(connection) if self.provider_resolver else self.deepseek
        instruction = str(node.config.get("instruction", ""))
        if node.type in {"writing.deepseek_draft", "writing.llm_draft"}:
            parent = by_type.get("writing.Draft@1")
            if not parent:
                raise RuntimeError("起草节点需要 Draft 输入")
            system_prompt = str(node.config.get(
                "system_prompt",
                "你是网络小说写手。严格遵守章节任务，直接输出正文，不解释创作过程。",
            ))
            user_content = f"章节任务：\n{parent.content['text']}\n\n写作要求：\n{instruction}"
        elif node.type == "writing.llm_review":
            draft = by_type.get("writing.Draft@1")
            if not draft:
                raise RuntimeError("独立审查节点需要 Draft 输入")
            system_prompt = (
                "你是独立小说审查员，不包庇写手。只输出 JSON 对象，不要 Markdown。"
                "格式：{\"findings\":[{\"id\":\"F1\",\"severity\":\"critical|major|minor\","
                "\"category\":\"类别\",\"quote\":\"原文逐字引文\",\"evidence\":\"问题证据\","
                "\"recommendation\":\"可执行建议\"}],\"summary\":\"总结\"}。"
                "没有问题时 findings 为空，但 summary 仍必须说明审查结论。"
            )
            user_content = f"待审草稿：\n{draft.content['text']}\n\n额外审查要求：\n{instruction}"
        elif node.type == "writing.llm_arbiter":
            draft = by_type.get("writing.Draft@1")
            review_artifact = by_type.get("writing.ReviewSet@1")
            if not draft or not review_artifact:
                raise RuntimeError("裁决节点需要 Draft 与 ReviewSet 输入")
            system_prompt = (
                "你是小说审查意见裁决者。逐条裁决全部 finding，只输出 JSON 对象，不要 Markdown。"
                "格式：{\"decisions\":[{\"finding_id\":\"F1\","
                "\"verdict\":\"accept|reject|modify\",\"reason\":\"裁决理由\","
                "\"revision_instruction\":\"接受或修改时的可执行修订指令，拒绝时可为空\"}],"
                "\"summary\":\"总结\"}。不能遗漏或发明 finding_id。"
            )
            user_content = (
                f"原始草稿：\n{draft.content['text']}\n\n独立审查：\n"
                f"{json.dumps(review_artifact.content, ensure_ascii=False)}\n\n额外裁决规则：\n{instruction}"
            )
        elif node.type == "writing.llm_revision":
            draft = by_type.get("writing.Draft@1")
            decision_artifact = by_type.get("writing.DecisionSet@1")
            if not draft or not decision_artifact:
                raise RuntimeError("定向修订节点需要 Draft 与 DecisionSet 输入")
            system_prompt = (
                "你是小说定向修订编辑。只执行 accept 或 modify 的裁决，绝不执行 reject。"
                "只输出 JSON 对象，不要 Markdown。格式：{\"text\":\"完整修订正文\","
                "\"changes\":[{\"finding_id\":\"F1\",\"description\":\"改了什么\","
                "\"before_quote\":\"旧稿逐字引文\",\"after_quote\":\"新稿逐字引文\"}],"
                "\"summary\":\"修订总结\"}。每条 accept/modify 必须且只能有一个 change。"
            )
            user_content = (
                f"旧稿：\n{draft.content['text']}\n\n裁决：\n"
                f"{json.dumps(decision_artifact.content, ensure_ascii=False)}\n\n额外修订要求：\n{instruction}"
            )
        elif node.type in {"writing.custom_prompt", "ai.prompt_call", "ai.agent_task"}:
            input_artifact = parents[0] if parents else None
            run = self.storage.get_run(run_id)
            context = run.snapshot.run_context if run else {}
            variables = {
                "input.text": str(input_artifact.content.get("text", "")) if input_artifact else "",
                "input.json": json.dumps(input_artifact.content, ensure_ascii=False) if input_artifact else "{}",
                "project.title": str(context.get("project_title", "")),
                "chapter.number": str(context.get("chapter_number", "")),
            }
            system_prompt = self._render_prompt_template(
                str(node.config.get("system_prompt", "你是一个可配置的写作助手。")), variables
            )
            user_content = self._render_prompt_template(
                str(node.config["user_prompt"]), variables
            )
        else:
            raise RuntimeError(f"不支持的 LLM 节点类型: {node.type}")
        skill_snapshots = node.config.get("skill_snapshots", [])
        context_skills = [item for item in skill_snapshots if item["execution_mode"] == "context"]
        subagent_skills = [item for item in skill_snapshots if item["execution_mode"] == "subagent"]
        if context_skills:
            system_prompt += "\n\n以下 Skill 指令必须同时遵守：\n" + "\n\n".join(
                f"<skill name=\"{item['name']}\" version=\"{item['version']}\">\n"
                f"参数：{json.dumps(item.get('parameters', {}), ensure_ascii=False)}\n"
                f"{item['instructions']}\n</skill>"
                for item in context_skills
            )
        skill_artifact_ids: list[str] = []
        if node.type == "ai.agent_task":
            capabilities = sorted({
                capability
                for skill in skill_snapshots
                for capability in skill.get("capabilities", [])
            })
            agent_instructions = "\n\n".join(
                f"<skill name=\"{skill['name']}\">\n"
                f"参数：{json.dumps(skill.get('parameters', {}), ensure_ascii=False)}\n"
                f"{skill['instructions']}\n</skill>"
                for skill in skill_snapshots
            )
            synthetic_skill = {
                "id": f"agent-task:{node.id}", "skill_id": f"agent-task:{node.id}",
                "name": node.id, "version": 1, "parameters": {},
                "capabilities": capabilities,
                "instructions": f"{system_prompt}\n\n{agent_instructions}".strip(),
            }
            artifact, text = await self._run_skill_subagent(
                run_id, node_run_id, attempt_id, node, input_artifact_ids,
                connection, provider, model, user_content, synthetic_skill,
            )
            return ({
                "text": text, "operation": "agent_task",
                "provider": connection["provider_identity"], "model": model,
                "round_artifact_id": artifact.id,
            }, "ai.AgentTaskResult@1", [artifact.id])
        subagent_results: list[tuple[dict, str]] = []
        for skill in subagent_skills:
            artifact, text = await self._run_skill_subagent(
                run_id, node_run_id, attempt_id, node, input_artifact_ids,
                connection, provider, model, user_content, skill,
            )
            skill_artifact_ids.append(artifact.id)
            subagent_results.append((skill, text))
        if subagent_results:
            user_content += "\n\n隔离 Skill 子代理结果（作为参考材料，仍由当前节点完成最终任务）：\n" + "\n\n".join(
                f"<subagent-result skill=\"{skill['name']}\">\n{text}\n</subagent-result>"
                for skill, text in subagent_results
            )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        request_payload = {
            "model": model,
            "messages": messages,
            "temperature": float(node.config.get("temperature", 0.8)),
            "max_tokens": int(node.config.get("max_tokens", 1200)),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if connection["provider_identity"] == "deepseek":
            request_payload["thinking"] = {
                "type": "enabled" if node.config.get("thinking", False) else "disabled"
            }
        call_id = str(uuid4())
        self.storage.create_provider_call(
            call_id, attempt_id, connection["provider_identity"], model, request_payload
        )

        async def on_delta(delta: str) -> None:
            if run_id in self.cancelled:
                raise RunCancelled
            self.broker.publish(
                run_id,
                {
                    "sequence": None,
                    "event_id": str(uuid4()),
                    "run_id": run_id,
                    "node_run_id": node_run_id,
                    "type": "provider.text.delta",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "payload": {"delta": delta},
                },
            )

        try:
            result = await provider.stream_chat(
                model=model,
                messages=messages,
                temperature=request_payload["temperature"],
                max_tokens=request_payload["max_tokens"],
                thinking=bool(node.config.get("thinking", False)),
                on_delta=on_delta,
            )
        except ProviderError as exc:
            self.storage.complete_provider_call(call_id, status="failed", error=exc.as_dict())
            raise
        except RunCancelled:
            self.storage.complete_provider_call(
                call_id, status="cancelled", error={"message": "用户取消，远端结果可能未知"}
            )
            raise
        except asyncio.CancelledError:
            self.storage.complete_provider_call(
                call_id, status="interrupted", error={"message": "进程中断，远端结果可能未知"}
            )
            raise
        except Exception as exc:
            self.storage.complete_provider_call(
                call_id, status="failed", error={"message": str(exc)}
            )
            raise

        self.storage.complete_provider_call(
            call_id,
            status="succeeded",
            request_id=result.request_id,
            response_payload=result.response_payload,
            usage=result.usage,
            finish_reason=result.finish_reason,
        )
        await self.emit(
            run_id,
            node_run_id,
            "provider.completed",
            {
                "provider": connection["provider_identity"],
                "model": result.model,
                "requestId": result.request_id,
                "finishReason": result.finish_reason,
                "usage": result.usage.model_dump(),
            },
        )
        if node.id == "report":
            try:
                report = BookAnalysisReport.model_validate(self._extract_json_object(result.text))
                report.markdown = result.text
                return report.model_dump(mode="json"), "reference.BookAnalysisReport@1", skill_artifact_ids
            except (ValueError, TypeError):
                pass
        if node.type in {"writing.deepseek_draft", "writing.llm_draft", "writing.custom_prompt", "ai.prompt_call"}:
            return ({
                "text": result.text,
                "operation": "llm_draft",
                "provider": connection["provider_identity"],
                "model": result.model,
            }, "ai.PromptResult@1" if node.type == "ai.prompt_call" else "writing.Draft@1", skill_artifact_ids)
        parsed = self._extract_json_object(result.text)
        if node.type == "writing.llm_review":
            review = ReviewSet.model_validate(parsed)
            return review.model_dump(mode="json"), "writing.ReviewSet@1", skill_artifact_ids
        if node.type == "writing.llm_arbiter":
            decisions = DecisionSet.model_validate(parsed)
            review = ReviewSet.model_validate(by_type["writing.ReviewSet@1"].content)
            decisions.validate_references(review)
            return decisions.model_dump(mode="json"), "writing.DecisionSet@1", skill_artifact_ids
        revision = Revision.model_validate(parsed)
        decisions = DecisionSet.model_validate(by_type["writing.DecisionSet@1"].content)
        revision.validate_against(by_type["writing.Draft@1"].content["text"], decisions)
        return revision.model_dump(mode="json"), "writing.Revision@1", skill_artifact_ids

    @staticmethod
    def _render_prompt_template(template: str, variables: dict[str, str]) -> str:
        import re

        unknown = sorted(set(re.findall(r"{{\s*([^{}]+?)\s*}}", template)) - set(variables))
        if unknown:
            raise ValueError(f"自定义 Prompt 包含未知变量: {unknown}")
        rendered = template
        for name, value in variables.items():
            rendered = re.sub(r"{{\s*" + re.escape(name) + r"\s*}}", lambda _: value, rendered)
        return rendered

    async def _run_skill_subagent(
        self,
        run_id: str,
        node_run_id: str,
        attempt_id: str,
        node: ExecutionNode,
        input_artifact_ids: list[str],
        connection: dict,
        provider,
        model: str,
        parent_task: str,
        skill: dict,
    ) -> tuple[Artifact, str]:
        capabilities = skill.get("capabilities", [])
        tool_protocol = ""
        if capabilities:
            tool_protocol = (
                "\n\n你可以请求以下受限工具：" + ", ".join(capabilities) + "。"
                "需要工具时只能输出单个 JSON 对象："
                '{"tool_call":{"name":"能力名","arguments":{...}}}。'
                "收到工具结果后继续；完成时输出最终自然语言结果，不要再包装 tool_call。"
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是隔离的 Skill 子代理。只执行下面 Skill 的专业任务，返回给主代理可用的分析或材料。"
                    "不要声称调用了未提供的工具或更深层子代理。"
                    f"{tool_protocol}\n\n"
                    f"<skill name=\"{skill['name']}\" version=\"{skill['version']}\">\n"
                    f"参数：{json.dumps(skill.get('parameters', {}), ensure_ascii=False)}\n"
                    f"{skill['instructions']}\n</skill>"
                ),
            },
            {"role": "user", "content": f"父节点任务与输入：\n{parent_task}"},
        ]
        tool_artifact_ids: list[str] = []
        result = None
        for round_index in range(5):
            request_payload = {
                "model": model, "messages": messages,
                "temperature": float(node.config.get("temperature", 0.7)),
                "max_tokens": min(int(node.config.get("max_tokens", 1800)), 2000),
                "stream": True, "stream_options": {"include_usage": True},
            }
            call_id = str(uuid4())
            self.storage.create_provider_call(
                call_id, attempt_id, connection["provider_identity"], model, request_payload
            )

            async def on_delta(delta: str) -> None:
                if run_id in self.cancelled:
                    raise RunCancelled
                self.broker.publish(run_id, {
                    "sequence": None, "event_id": str(uuid4()), "run_id": run_id,
                    "node_run_id": node_run_id, "type": "skill.subagent.delta",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "payload": {"skillId": skill["skill_id"], "round": round_index, "delta": delta},
                })

            try:
                result = await provider.stream_chat(
                    model=model, messages=messages,
                    temperature=request_payload["temperature"],
                    max_tokens=request_payload["max_tokens"], thinking=False,
                    on_delta=on_delta,
                )
            except ProviderError as exc:
                self.storage.complete_provider_call(call_id, status="failed", error=exc.as_dict())
                raise
            except RunCancelled:
                self.storage.complete_provider_call(call_id, status="cancelled", error={"message": "用户取消 Skill 子代理"})
                raise
            except asyncio.CancelledError:
                self.storage.complete_provider_call(call_id, status="interrupted", error={"message": "Skill 子代理进程中断"})
                raise
            except Exception as exc:
                self.storage.complete_provider_call(call_id, status="failed", error={"message": str(exc)})
                raise
            self.storage.complete_provider_call(
                call_id, status="succeeded", request_id=result.request_id,
                response_payload=result.response_payload, usage=result.usage,
                finish_reason=result.finish_reason,
            )
            tool_call = self._parse_skill_tool_call(result.text)
            if not tool_call:
                break
            if round_index >= 4:
                raise RuntimeError("Skill 子代理超过 4 次工具调用限制")
            if tool_call.name not in capabilities:
                raise RuntimeError(f"Skill 未声明工具能力: {tool_call.name}")
            tool_result = self._execute_skill_tool(run_id, tool_call)
            content = {
                "skill_id": skill["skill_id"], "skill_version_id": skill["id"],
                "tool_name": tool_call.name, "arguments": tool_call.arguments,
                "result": tool_result,
            }
            encoded = json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
            tool_artifact = Artifact(
                id=str(uuid4()), run_id=run_id, node_run_id=node_run_id,
                schema_type="skill.ToolResult@1", content=content,
                content_hash=hashlib.sha256(encoded).hexdigest(),
                parent_artifact_ids=input_artifact_ids, created_at=datetime.now(UTC),
            )
            self.storage.save_artifact(tool_artifact)
            tool_artifact_ids.append(tool_artifact.id)
            await self.emit(
                run_id, node_run_id, "skill.tool.completed",
                {"skillId": skill["skill_id"], "tool": tool_call.name, "artifactId": tool_artifact.id},
            )
            messages.extend([
                {"role": "assistant", "content": result.text},
                {"role": "user", "content": "工具结果：\n" + json.dumps(tool_result, ensure_ascii=False)},
            ])
        if result is None:
            raise RuntimeError("Skill 子代理未返回结果")
        content = {
            "skill_id": skill["skill_id"], "skill_version_id": skill["id"],
            "name": skill["name"], "text": result.text,
            "provider": connection["provider_identity"], "model": model,
        }
        encoded = json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
        artifact = Artifact(
            id=str(uuid4()), run_id=run_id, node_run_id=node_run_id,
            schema_type="skill.SubagentResult@1", content=content,
            content_hash=hashlib.sha256(encoded).hexdigest(),
            parent_artifact_ids=[*input_artifact_ids, *tool_artifact_ids],
            created_at=datetime.now(UTC),
        )
        self.storage.save_artifact(artifact)
        await self.emit(
            run_id, node_run_id, "skill.subagent.completed",
            {"skillId": skill["skill_id"], "version": skill["version"], "artifactId": artifact.id},
        )
        return artifact, result.text

    @staticmethod
    def _parse_skill_tool_call(text: str) -> SkillToolCall | None:
        stripped = text.strip()
        if not stripped.startswith("{") and not stripped.startswith("```"):
            return None
        try:
            value = WorkflowEngine._extract_json_object(stripped)
        except ValueError:
            return None
        if "tool_call" not in value:
            return None
        return SkillToolCall.model_validate(value["tool_call"])

    def _execute_skill_tool(self, run_id: str, tool_call: SkillToolCall) -> dict:
        run = self.storage.get_run(run_id)
        context = run.snapshot.run_context if run else {}
        slug = context.get("project_slug")
        if not slug:
            raise RuntimeError("Skill 工具缺少项目上下文")
        project_root = (self.project_root / slug).resolve()
        if tool_call.name == "project.assets.read":
            category = str(tool_call.arguments.get("category", ""))
            relative_path = str(tool_call.arguments.get("path", ""))
            if category not in {"world", "characters", "outline", "state"}:
                raise RuntimeError("project.assets.read 不允许该资产类别")
            target = (project_root / category / relative_path).resolve()
            category_root = (project_root / category).resolve()
            if (
                not target.is_relative_to(category_root) or not target.is_file()
                or target.is_symlink() or target.stat().st_size > 64 * 1024
            ):
                raise RuntimeError("Skill 资产读取目标不存在、越界或超过 64 KB")
            content = target.read_text(encoding="utf-8")
            return {
                "relative_path": target.relative_to(project_root).as_posix(),
                "content": content,
                "content_hash": hashlib.sha256(content.encode()).hexdigest(),
            }
        chapter_number = int(tool_call.arguments.get("chapter_number", 0))
        if chapter_number < 1:
            raise RuntimeError("project.chapters.read 需要有效 chapter_number")
        target = (project_root / "manuscript" / f"chapter-{chapter_number:04d}.md").resolve()
        manuscript_root = (project_root / "manuscript").resolve()
        if (
            not target.is_relative_to(manuscript_root) or not target.is_file()
            or target.is_symlink() or target.stat().st_size > 256 * 1024
        ):
            raise RuntimeError("Skill 章节读取目标不存在、越界或超过 256 KB")
        content = target.read_text(encoding="utf-8")
        return {
            "chapter_number": chapter_number,
            "relative_path": target.relative_to(project_root).as_posix(),
            "content": content,
            "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        }

    @staticmethod
    def _extract_json_object(text: str) -> dict:
        stripped = text.strip()
        if stripped.startswith("```"):
            first_newline = stripped.find("\n")
            last_fence = stripped.rfind("```")
            if first_newline != -1 and last_fence > first_newline:
                stripped = stripped[first_newline + 1:last_fence].strip()
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"模型结构化输出不是有效 JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("模型结构化输出必须是 JSON 对象")
        return value

    def _cache_key(self, node: ExecutionNode, input_artifact_ids: list[str]) -> str:
        definition = get_node_definition(node.type)
        parent_hashes = [self.storage.get_artifact(item).content_hash for item in input_artifact_ids]
        payload = {
            "node_type": node.type,
            "node_version": definition.version if definition else "unknown",
            "config": node.config,
            "parent_hashes": parent_hashes,
        }
        if is_model_node_type(node.type):
            payload["provider_endpoint"] = node.config["connection_snapshot"]["base_url"]
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def cancel(self, run_id: str) -> None:
        self.cancelled.add(run_id)

    async def retry(self, node_run_id: str) -> str:
        node_run = self.storage.get_node_run(node_run_id)
        if not node_run:
            raise ValueError("节点运行不存在")
        run = self.storage.get_run(node_run.run_id)
        if not run:
            raise ValueError("运行不存在")
        descendants = {node_run.node_id}
        if "[" in node_run.node_id:
            item_prefix = node_run.node_id.split("/", 1)[0]
            descendants = {row.node_id for row in run.node_runs if row.node_id.startswith(f"{item_prefix}/")}
            map_node_id = item_prefix.split("[", 1)[0]
            descendants.add(map_node_id)
        changed = True
        while changed:
            changed = False
            for node in run.snapshot.nodes:
                if node.id not in descendants and any(parent in descendants for parent in node.dependencies):
                    descendants.add(node.id)
                    changed = True
        self.cancelled.discard(run.id)
        self.storage.reset_node_runs(run.id, descendants)
        await self.emit(
            run.id, node_run_id, "node.retry.requested",
            {"nodeId": node_run.node_id, "resetNodeIds": sorted(descendants)},
        )
        self.start(run.id)
        return run.id

    async def retry_map_item(self, node_run_id: str) -> str:
        item_run = self.storage.get_node_run(node_run_id)
        if not item_run or "[" not in item_run.node_id:
            raise ValueError("Map 条目运行不存在")
        run = self.storage.get_run(item_run.run_id)
        if not run:
            raise ValueError("运行不存在")
        item_prefix = item_run.node_id.split("/", 1)[0]
        map_id = item_prefix.split("[", 1)[0]
        map_node = next((node for node in run.snapshot.nodes if node.id == map_id), None)
        map_row = next((row for row in run.node_runs if row.node_id == map_id), None)
        if not map_node or not map_row:
            raise ValueError("Map 节点不存在")
        target_ids = {row.node_id for row in run.node_runs if row.node_id.startswith(f"{item_prefix}/")}
        target_ids.add(map_id)
        self.storage.reset_node_runs(run.id, target_ids)
        await self.emit(run.id, node_run_id, "map.item.retry.requested", {"itemId": item_prefix})
        completed = {
            row.node_id: row for row in self.storage.get_run(run.id).node_runs
            if row.status == "succeeded"
        }
        await self._execute_node(run.id, map_row.id, map_node, completed)
        self.storage.update_run(run.id, "succeeded")
        await self.emit(run.id, map_row.id, "map.item.retry.succeeded", {"itemId": item_prefix})
        return run.id
