import time
import json
import stat
import base64
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from whitebox.main import DEFAULT_WORKFLOW, create_app
from whitebox.compiler import compile_workflow
from whitebox.models import ModelProfileCreate, ProviderUsage
from whitebox.providers import DeepSeekProvider, ProviderResult
from whitebox.storage import Storage


def test_runtime_info_reports_version_and_data_boundaries(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    secrets = tmp_path / "secrets.json"
    projects = tmp_path / "projects"
    app = create_app(database, DeepSeekProvider(api_key="test"), secrets, projects)
    with TestClient(app) as client:
        info = client.get("/api/runtime-info")

    assert info.status_code == 200
    assert info.json()["version"] == "0.4.5"
    assert info.json()["mode"] == "development"
    assert info.json()["database_path"] == str(database)
    assert info.json()["secrets_path"] == str(secrets)
    assert info.json()["projects_path"] == str(projects)
    assert info.json()["instance_token_valid"] is False
    assert "instance_token" not in info.json()


def test_runtime_info_validates_launcher_instance_token_without_disclosing_it(tmp_path, monkeypatch) -> None:
    token = "a" * 64
    monkeypatch.setenv("WHITEBOX_INSTANCE_TOKEN", token)
    app = create_app(tmp_path / "runtime-token.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        rejected = client.get("/api/runtime-info", headers={"X-Whitebox-Instance-Token": "b" * 64})
        info = client.get("/api/runtime-info", headers={"X-Whitebox-Instance-Token": token})

    assert rejected.json()["instance_token_valid"] is False
    assert info.status_code == 200
    assert info.json()["instance_token_valid"] is True
    assert "instance_token" not in info.json()


def test_project_creation_persists_author_brief_as_versioned_asset(tmp_path) -> None:
    project_root = tmp_path / "brief-projects"
    app = create_app(tmp_path / "brief.db", DeepSeekProvider(api_key="test"), project_root=project_root)
    with TestClient(app) as client:
        project = client.post("/api/projects", json={
            "title": "简报书", "slug": "brief-book", "genre": "悬疑", "brief": "一名失忆剑客在旧戏楼寻找自己的名字。",
        }).json()
        assets = client.get(f"/api/projects/{project['id']}/assets?category=outline").json()
        intent = next(item for item in assets if item["relative_path"] == "outline/author_intent.md")
        content = client.get(f"/api/projects/{project['id']}/assets/{intent['id']}").json()
    assert "悬疑" in content["content"]
    assert "失忆剑客" in content["content"]


def test_project_export_contains_readable_assets_without_secrets(tmp_path) -> None:
    project_root = tmp_path / "export-projects"
    app = create_app(tmp_path / "export.db", DeepSeekProvider(api_key="test-secret"), project_root=project_root)
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "导出书", "slug": "export-book", "brief": "导出简报"}).json()
        bundle = client.get(f"/api/projects/{project['id']}/export")
    assert bundle.status_code == 200
    assert bundle.json()["format"] == "whitebox.project-bundle"
    assert any(item["path"] == "outline/author_intent.md" for item in bundle.json()["files"])
    assert "test-secret" not in bundle.text


def test_project_bundle_round_trip_and_path_validation(tmp_path) -> None:
    project_root = tmp_path / "bundle-projects"
    app = create_app(tmp_path / "bundle.db", DeepSeekProvider(api_key="test"), project_root=project_root)
    with TestClient(app) as client:
        source = client.post("/api/projects", json={"title": "源项目", "slug": "bundle-source", "brief": "可移植简报"}).json()
        bundle = client.get(f"/api/projects/{source['id']}/export").json()
        imported = client.post("/api/project-bundles/import", json={"title": "导入项目", "slug": "bundle-target", "bundle": bundle})
        malicious = {**bundle, "files": [{"path": "../secret.txt", "content": "x"}]}
        rejected = client.post("/api/project-bundles/import", json={"title": "坏项目", "slug": "bad-bundle", "bundle": malicious})
    assert imported.status_code == 201
    assert imported.json()["production_canvas"]["project_id"] == imported.json()["project"]["id"]
    assert (project_root / "bundle-target" / "outline" / "author_intent.md").is_file()
    assert rejected.status_code == 422
    assert not (project_root / "bad-bundle").exists()


def test_auto_director_candidates_confirm_into_checkpointed_project(tmp_path) -> None:
    project_root = tmp_path / "director-projects"
    app = create_app(tmp_path / "director.db", DeepSeekProvider(api_key="test"), project_root=project_root)
    with TestClient(app) as client:
        generated = client.post("/api/director/candidates", json={"inspiration": "失忆剑客在戏楼醒来", "genre": "悬疑", "target_chapters": 60})
        candidate = generated.json()["candidates"][0]
        confirmed = client.post("/api/director/confirm", json={"title": "戏楼无名客", "slug": "director-book", "candidate": candidate})
        invalid = client.post("/api/director/confirm", json={"title": "坏候选", "slug": "bad-director", "candidate": {"id": "fake"}})
    assert generated.status_code == 200
    assert confirmed.status_code == 201
    assert (project_root / "director-book" / "outline" / "author_intent.md").is_file()
    state = json.loads((project_root / "director-book" / "state" / "director-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "confirmed"
    assert state["candidate"]["target_chapters"] == 60
    assert invalid.status_code == 422
    assert not (project_root / "bad-director").exists()


def test_run_history_can_be_filtered_by_project(tmp_path) -> None:
    app = create_app(tmp_path / "run-history.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        response = client.get("/api/runs?project_id=demo-project")
    assert response.status_code == 200
    assert response.json() == []


def test_project_delete_removes_owned_runs_and_files(tmp_path) -> None:
    project_root = tmp_path / "delete-projects"
    app = create_app(tmp_path / "delete-project.db", FakeDeepSeekProvider(), project_root=project_root)
    workflow = {"id": "delete-source", "name": "delete", "revision": 1, "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "x"}}], "edges": []}
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "待删除", "slug": "delete-me", "brief": "测试"}).json()
        run_id = client.post("/api/runs", json={"workflow": workflow, "project_id": project["id"]}).json()["runId"]
        wait_for_status(client, run_id, {"succeeded"})
        response = client.delete(f"/api/projects/{project['id']}")
        missing_run = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 204
    assert missing_run.status_code == 404
    assert not (project_root / "delete-me").exists()


class FakeDeepSeekProvider:
    provider = "deepseek"
    base_url = "https://api.deepseek.com"

    async def stream_chat(self, *, model, messages, temperature, max_tokens, thinking, on_delta):
        system = messages[0]["content"]
        if "独立小说审查员" in system:
            text = json.dumps({
                "findings": [{
                    "id": "F1", "severity": "major", "category": "连续性",
                    "quote": "忘了自己的名字", "evidence": "任务未解释失忆边界",
                    "recommendation": "补充可验证的失忆表现",
                }],
                "summary": "发现一项需要裁决的问题",
            }, ensure_ascii=False)
        elif "裁决者" in system:
            text = json.dumps({
                "decisions": [{
                    "finding_id": "F1", "verdict": "accept", "reason": "证据充分",
                    "revision_instruction": "补充失忆边界的可见表现",
                }],
                "summary": "接受一项意见",
            }, ensure_ascii=False)
        elif "定向修订编辑" in system:
            text = json.dumps({
                "text": "戏楼的雨沿着残瓦坠落。剑客睁开眼时，只记得剑法，却忘了自己的名字。",
                "changes": [{"finding_id": "F1", "description": "明确失忆边界", "before_quote": "忘了自己的名字", "after_quote": "只记得剑法，却忘了自己的名字"}],
                "summary": "按裁决完成一项修订",
            }, ensure_ascii=False)
        else:
            text = "戏楼的雨沿着残瓦坠落。剑客睁开眼时，已经忘了自己的名字。"
        await on_delta(text[:12])
        await on_delta(text[12:])
        return ProviderResult(
            text=text,
            model=model,
            request_id="fake-request-1",
            finish_reason="stop",
            usage=ProviderUsage(prompt_tokens=30, completion_tokens=24, total_tokens=54),
            request_payload={
                "model": model, "messages": messages, "temperature": temperature,
                "max_tokens": max_tokens, "stream": True,
            },
            response_payload={"chunks": [{"id": "fake-request-1"}]},
        )


class ToolCallingFakeProvider(FakeDeepSeekProvider):
    async def stream_chat(self, *, model, messages, temperature, max_tokens, thinking, on_delta):
        system = messages[0]["content"]
        if "隔离的 Skill 子代理" in system:
            if any(
                message["role"] == "user" and message["content"].startswith("工具结果：")
                for message in messages
            ):
                text = "已读取项目设定并完成分析。"
            else:
                text = json.dumps({
                    "tool_call": {
                        "name": "project.assets.read",
                        "arguments": {"category": "world", "path": "lore.md"},
                    }
                }, ensure_ascii=False)
            await on_delta(text)
            return ProviderResult(
                text=text, model=model, request_id="tool-fake", finish_reason="stop",
                usage=ProviderUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                request_payload={}, response_payload={"chunks": []},
            )
        return await super().stream_chat(
            model=model, messages=messages, temperature=temperature,
            max_tokens=max_tokens, thinking=thinking, on_delta=on_delta,
        )


def make_test_app(database):
    return create_app(database, FakeDeepSeekProvider())


def wait_for_status(client: TestClient, run_id: str, statuses: set[str], timeout: float = 15) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        if run["status"] == "waiting_approval" and "waiting_approval" not in statuses:
            approval = next(
                item for item in client.get("/api/approvals").json()
                if item["run_id"] == run_id
            )
            client.post(f"/api/approvals/{approval['id']}/decide", json={
                "decision": "approved", "actor": "test", "note": "自动批准测试流程",
            })
        time.sleep(0.05)
    raise AssertionError(f"运行 {run_id} 未进入预期状态 {statuses}")


def test_run_persists_snapshot_events_and_artifacts(tmp_path) -> None:
    app = make_test_app(tmp_path / "test.db")
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")})
        assert response.status_code == 202
        run_id = response.json()["runId"]

        run = wait_for_status(client, run_id, {"succeeded"})

        assert run["status"] == "succeeded"
        assert len(run["node_runs"]) == 10
        artifact_id = next(
            item["output_artifact_id"] for item in run["node_runs"] if item["node_id"] == "quality"
        )
        artifact = client.get(f"/api/artifacts/{artifact_id}").json()
        assert artifact["parent_artifact_ids"]
        assert artifact["schema_type"] == "writing.QualityReport@1"
        assert artifact["content"]["passed"] is True

        draft_run = next(item for item in run["node_runs"] if item["node_id"] == "draft")
        draft_attempt = client.get(f"/api/node-runs/{draft_run['id']}/attempts").json()[0]
        provider_call = client.get(
            f"/api/attempts/{draft_attempt['id']}/provider-calls"
        ).json()[0]
        assert provider_call["provider"] == "deepseek"
        assert provider_call["usage"]["total_tokens"] == 54
        assert "authorization" not in provider_call["request_payload"]
        assert "test-secret" not in str(provider_call)

        events = app.state.storage.list_events(run_id)
        assert events[0].type == "run.created"
        assert events[-1].type == "run.succeeded"
        assert [event.sequence for event in events] == sorted(event.sequence for event in events)

        replay = client.get(f"/api/runs/{run_id}/events?after={events[0].sequence}")
        assert replay.status_code == 200
        assert replay.json()[0]["sequence"] == events[1].sequence


def test_node_definitions_are_serializable_manifests(tmp_path) -> None:
    app = make_test_app(tmp_path / "definitions.db")
    with TestClient(app) as client:
        definitions = client.get("/api/node-definitions").json()

    assert {item["type"] for item in definitions} == {
        "mock.source", "mock.rewrite", "writing.deepseek_draft"
        , "writing.llm_draft", "writing.llm_review", "writing.llm_arbiter"
        , "writing.llm_revision", "writing.revision_diff", "writing.quality_gate"
        , "core.approval", "writing.chapter_archive", "writing.state_proposal"
        , "writing.custom_prompt", "ai.prompt_call", "ai.agent_task", "reference.book_source"
        , "workflow.input", "workflow.output", "flow.split", "flow.join", "flow.map"
    }
    rewrite = next(item for item in definitions if item["type"] == "mock.rewrite")
    assert rewrite["inputs"]["draft"]["type"] == "writing.Draft@1"
    assert rewrite["execution"]["cache"] == "content-addressed"


def test_prompt_call_debug_run_is_isolated_from_source_workflow(tmp_path) -> None:
    app = make_test_app(tmp_path / "node-debug.db")
    workflow = {
        "id": "debuggable", "name": "调试流程", "revision": 1,
        "nodes": [{
            "id": "prompt", "type": "ai.prompt_call", "position": {"x": 0, "y": 0},
            "config": {
                "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
                "temperature": 0.4, "system_prompt": "你是测试助手。",
                "user_prompt": "原始生产 Prompt",
            },
        }],
        "edges": [],
    }
    with TestClient(app) as client:
        assert client.put("/api/workflows/debuggable", json=workflow).status_code == 200
        response = client.post("/api/node-debug-runs", json={
            "workflow_id": "debuggable", "node_id": "prompt",
            "project_id": "demo-project", "chapter_number": 3,
            "message": "只在调试中补充这一句",
        })
        run = wait_for_status(client, response.json()["runId"], {"succeeded"})
        source = client.get("/api/workflows/debuggable").json()
        node_run = run["node_runs"][0]
        attempt = client.get(f"/api/node-runs/{node_run['id']}/attempts").json()[0]
        call = client.get(f"/api/attempts/{attempt['id']}/provider-calls").json()[0]
        artifact = client.get(f"/api/artifacts/{node_run['output_artifact_id']}").json()

    assert run["workflow_id"] == "debug:debuggable:prompt"
    assert source["nodes"][0]["config"]["user_prompt"] == "原始生产 Prompt"
    assert "只在调试中补充这一句" in call["request_payload"]["messages"][1]["content"]
    assert artifact["schema_type"] == "ai.PromptResult@1"


def test_project_prompt_override_is_used_at_runtime(tmp_path) -> None:
    app = make_test_app(tmp_path / "prompt-runtime.db")
    workflow = {
        "id": "prompt-runtime", "name": "Prompt runtime", "revision": 1,
        "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "任务"}}, {
            "id": "call", "type": "ai.prompt_call", "position": {"x": 300, "y": 0},
            "config": {"connection_id": "deepseek-official", "model": "deepseek-v4-flash", "user_prompt": "{{input.text}}", "prompt_id": "chapter.writer.system", "system_prompt": "原始系统"},
        }], "edges": [{"id": "edge", "source": "source", "target": "call", "source_port": "draft", "target_port": "input"}],
    }
    with TestClient(app) as client:
        client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "项目系统覆盖"})
        run_id = client.post("/api/runs", json={"workflow": workflow, "project_id": "demo-project"}).json()["runId"]
        run = wait_for_status(client, run_id, {"succeeded"})
        node_run = next(item for item in run["node_runs"] if item["node_id"] == "call")
        attempt = client.get(f"/api/node-runs/{node_run['id']}/attempts").json()[0]
        call = client.get(f"/api/attempts/{attempt['id']}/provider-calls").json()[0]
    assert call["request_payload"]["messages"][0]["content"] == "项目系统覆盖"
    assert call["request_payload"]["prompt_snapshot"]["project_override_revision"] == 1


def test_artifact_project_filter_prevents_cross_project_reads(tmp_path) -> None:
    app = make_test_app(tmp_path / "artifact-isolation.db")
    workflow = {"id": "isolated-source", "name": "isolated", "revision": 1, "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "private"}}], "edges": []}
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "隔离项目", "slug": "isolated-project"}).json()
        run_id = client.post("/api/runs", json={"workflow": workflow, "project_id": project["id"]}).json()["runId"]
        run = wait_for_status(client, run_id, {"succeeded"})
        artifact_id = run["node_runs"][0]["output_artifact_id"]
        denied = client.get(f"/api/artifacts/{artifact_id}?project_id=demo-project")
        allowed = client.get(f"/api/artifacts/{artifact_id}?project_id={project['id']}")
    assert denied.status_code == 404
    assert allowed.status_code == 200


def test_run_comparison_is_project_scoped(tmp_path) -> None:
    app = make_test_app(tmp_path / "run-compare.db")
    workflow = {"id": "compare-source", "name": "compare", "revision": 1, "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "x"}}], "edges": []}
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "对比项目", "slug": "compare-project"}).json()
        first = client.post("/api/runs", json={"workflow": workflow, "project_id": project["id"]}).json()["runId"]
        second = client.post("/api/runs", json={"workflow": workflow, "project_id": project["id"]}).json()["runId"]
        wait_for_status(client, first, {"succeeded"})
        wait_for_status(client, second, {"succeeded"})
        comparison = client.get(f"/api/run-comparisons?left_id={first}&right_id={second}&project_id={project['id']}")
        denied = client.get(f"/api/run-comparisons?left_id={first}&right_id={second}&project_id=demo-project")
    assert comparison.status_code == 200
    assert comparison.json()["same_graph"] is True
    assert denied.status_code == 404


def test_run_chapter_draft_saves_versioned_author_workspace(tmp_path) -> None:
    project_root = tmp_path / "draft-projects"
    app = create_app(tmp_path / "draft-workspace.db", FakeDeepSeekProvider(), project_root=project_root)
    workflow = {"id": "draft-source", "name": "draft", "revision": 1, "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "x"}}], "edges": []}
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "编辑稿", "slug": "draft-book"}).json()
        run_id = client.post("/api/runs", json={"workflow": workflow, "project_id": project["id"], "chapter_number": 3}).json()["runId"]
        wait_for_status(client, run_id, {"succeeded"})
        first = client.post(f"/api/runs/{run_id}/chapter-draft", json={"content": "作者第一版"})
        second = client.post(f"/api/runs/{run_id}/chapter-draft", json={"content": "作者第二版", "expected_hash": first.json()["content_hash"]})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["version"] == 2
    assert (project_root / "draft-book" / "outline" / "chapter-drafts" / "chapter-0003.md").read_text(encoding="utf-8") == "作者第二版"


def test_failed_run_can_resume_from_first_failed_node(tmp_path) -> None:
    app = make_test_app(tmp_path / "resume.db")
    workflow = {"id": "resume-flow", "name": "resume", "revision": 1, "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "x", "fail_attempts": 1}}], "edges": []}
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"workflow": workflow, "project_id": "demo-project"}).json()["runId"]
        wait_for_status(client, run_id, {"failed"})
        resumed = client.post(f"/api/runs/{run_id}/resume")
        succeeded = wait_for_status(client, run_id, {"succeeded"})
        conflict = client.post(f"/api/runs/{run_id}/resume")
    assert resumed.status_code == 202
    assert resumed.json()["resumedNodeId"] == "source"
    assert succeeded["status"] == "succeeded"
    assert conflict.status_code == 409


def test_agent_task_keeps_tool_and_round_evidence(tmp_path) -> None:
    app = create_app(tmp_path / "agent-task.db", ToolCallingFakeProvider())
    with TestClient(app) as client:
        client.post("/api/projects/demo-project/assets/save", json={
            "category": "world", "relative_name": "lore.md", "content": "城门只在月蚀时开启。",
            "expected_hash": None, "actor": "author", "note": "Agent 测试",
        })
        skill = client.post("/api/skills/import", json={
            "source": "---\nname: agent-lore\ndescription: 读取设定\nmetadata:\n  whitebox-capabilities:\n    - project.assets.read\n---\n读取 lore.md 后完成任务。",
            "execution_mode": "subagent",
        }).json()
        workflow = {
            "id": "agent-flow", "name": "Agent 流程", "revision": 1,
            "nodes": [{
                "id": "agent", "type": "ai.agent_task", "position": {"x": 0, "y": 0},
                "config": {
                    "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
                    "temperature": 0.2, "system_prompt": "检查世界设定。",
                    "user_prompt": "给出写作建议。",
                    "skill_bindings": [{"skill_id": skill["id"], "parameters": {}}],
                },
            }], "edges": [],
        }
        run_id = client.post("/api/runs", json={"workflow": workflow}).json()["runId"]
        run = wait_for_status(client, run_id, {"succeeded"})
        node_run = run["node_runs"][0]
        attempt = client.get(f"/api/node-runs/{node_run['id']}/attempts").json()[0]
        calls = client.get(f"/api/attempts/{attempt['id']}/provider-calls").json()
        result = client.get(f"/api/artifacts/{node_run['output_artifact_id']}").json()
        agent_evidence = client.get(f"/api/artifacts/{result['content']['round_artifact_id']}").json()
        parents = [client.get(f"/api/artifacts/{item}").json() for item in agent_evidence["parent_artifact_ids"]]

    assert len(calls) == 2
    assert result["schema_type"] == "ai.AgentTaskResult@1"
    assert any(item["schema_type"] == "skill.ToolResult@1" for item in parents)


def test_map_expands_body_nodes_into_same_run_with_artifact_evidence(tmp_path) -> None:
    app = make_test_app(tmp_path / "map.db")
    body = {
        "id": "map-body", "name": "Map Body", "revision": 1,
        "nodes": [
            {"id": "input", "type": "workflow.input", "position": {"x": 0, "y": 0}, "config": {"name": "item", "default": ""}},
            {"id": "call", "type": "ai.prompt_call", "position": {"x": 300, "y": 0}, "config": {
                "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
                "temperature": 0.2, "system_prompt": "分析单项。", "user_prompt": "分析：{{input.text}}",
            }},
            {"id": "output", "type": "workflow.output", "position": {"x": 600, "y": 0}, "config": {"name": "result"}},
        ],
        "edges": [
            {"id": "input-call", "source": "input", "target": "call", "source_port": "value", "target_port": "input"},
            {"id": "call-output", "source": "call", "target": "output", "source_port": "text", "target_port": "value"},
        ],
    }
    parent = {
        "id": "map-parent", "name": "Map Parent", "revision": 1,
        "nodes": [
            {"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "甲\n\n乙"}},
            {"id": "split", "type": "flow.split", "position": {"x": 300, "y": 0}, "config": {"mode": "paragraph"}},
            {"id": "map", "type": "flow.map", "position": {"x": 600, "y": 0}, "config": {"body_workflow_id": "map-body"}},
        ],
        "edges": [
            {"id": "source-split", "source": "source", "target": "split", "source_port": "draft", "target_port": "text"},
            {"id": "split-map", "source": "split", "target": "map", "source_port": "items", "target_port": "items"},
        ],
    }
    with TestClient(app) as client:
        assert client.put("/api/workflows/map-body", json=body).status_code == 200
        response = client.post("/api/runs", json={"workflow": parent}).json()
        run = wait_for_status(client, response["runId"], {"succeeded"})
        dynamic = [item for item in run["node_runs"] if item["node_id"].startswith("map[")]
        assert all(item["input_snapshot"] for item in dynamic)
        calls = []
        for item in dynamic:
            attempts = client.get(f"/api/node-runs/{item['id']}/attempts").json()
            calls.extend(client.get(f"/api/attempts/{attempts[0]['id']}/provider-calls").json())
        map_run = next(item for item in run["node_runs"] if item["node_id"] == "map")
        map_artifact = client.get(f"/api/artifacts/{map_run['output_artifact_id']}").json()
        split_run = next(item for item in run["node_runs"] if item["node_id"] == "split")
        split_artifact = client.get(f"/api/artifacts/{split_run['output_artifact_id']}").json()

    assert len(dynamic) == 6
    assert len(calls) == 2
    assert split_artifact["schema_type"] == "core.List@1"
    assert map_artifact["schema_type"] == "core.List@1"
    assert len(map_artifact["parent_artifact_ids"]) >= 3


def test_map_rejects_invalid_concurrency(tmp_path) -> None:
    app = make_test_app(tmp_path / "map-concurrency.db")
    body = {
        "id": "map-body", "name": "Map Body", "revision": 1,
        "nodes": [
            {"id": "input", "type": "workflow.input", "position": {"x": 0, "y": 0}, "config": {"name": "item"}},
            {"id": "output", "type": "workflow.output", "position": {"x": 300, "y": 0}, "config": {"name": "result"}},
        ], "edges": [{"id": "edge", "source": "input", "target": "output", "source_port": "value", "target_port": "value"}],
    }
    parent = {
        "id": "map-parent", "name": "Map Parent", "revision": 1,
        "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "x"}}, {"id": "map", "type": "flow.map", "position": {"x": 300, "y": 0}, "config": {"body_workflow_id": "map-body", "concurrency": 9}}],
        "edges": [{"id": "edge", "source": "source", "target": "map", "source_port": "draft", "target_port": "items"}],
    }
    with TestClient(app) as client:
        client.put("/api/workflows/map-body", json=body)
        response = client.post("/api/runs", json={"workflow": parent})
    assert response.status_code == 422
    assert "并发数" in response.text


def test_map_item_retry_requires_dynamic_failed_node(tmp_path) -> None:
    app = make_test_app(tmp_path / "map-item-retry.db")
    with TestClient(app) as client:
        response = client.post("/api/map-items/does-not-exist/retry")
    assert response.status_code == 404


def test_map_run_summary_requires_map_node_run(tmp_path) -> None:
    app = make_test_app(tmp_path / "map-summary.db")
    with TestClient(app) as client:
        response = client.get("/api/map-runs/does-not-exist/summary")
    assert response.status_code == 404


def test_map_item_retry_preserves_successful_sibling(tmp_path) -> None:
    app = make_test_app(tmp_path / "map-item-retry-e2e.db")
    body = {"id": "retry-body", "name": "Retry Body", "revision": 1, "nodes": [
        {"id": "input", "type": "workflow.input", "position": {"x": 0, "y": 0}, "config": {"name": "item"}},
        {"id": "call", "type": "ai.prompt_call", "position": {"x": 300, "y": 0}, "config": {"connection_id": "deepseek-official", "model": "deepseek-v4-flash", "temperature": 0.2, "system_prompt": "分析单项", "user_prompt": "分析 {{input.text}}", "fail_if_text": "甲", "fail_attempts": 1}},
        {"id": "output", "type": "workflow.output", "position": {"x": 600, "y": 0}, "config": {"name": "result"}},
    ], "edges": [{"id": "input-call", "source": "input", "target": "call", "source_port": "value", "target_port": "input"}, {"id": "call-output", "source": "call", "target": "output", "source_port": "text", "target_port": "value"}]}
    parent = {"id": "retry-parent", "name": "Retry Parent", "revision": 1, "nodes": [
        {"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "甲\n\n乙"}},
        {"id": "split", "type": "flow.split", "position": {"x": 300, "y": 0}, "config": {"mode": "paragraph"}},
        {"id": "map", "type": "flow.map", "position": {"x": 600, "y": 0}, "config": {"body_workflow_id": "retry-body", "concurrency": 2}},
    ], "edges": [{"id": "source-split", "source": "source", "target": "split", "source_port": "draft", "target_port": "text"}, {"id": "split-map", "source": "split", "target": "map", "source_port": "items", "target_port": "items"}]}
    with TestClient(app) as client:
        assert client.put("/api/workflows/retry-body", json=body).status_code == 200
        run_id = client.post("/api/runs", json={"workflow": parent}).json()["runId"]
        failed = wait_for_status(client, run_id, {"failed"})
        dynamic = [row for row in failed["node_runs"] if row["node_id"].endswith("/call")]
        assert len(dynamic) == 2
        target = next(row for row in dynamic if row["status"] == "failed")
        sibling = next(row for row in dynamic if row["status"] == "succeeded")
        assert client.post(f"/api/map-items/{target['id']}/retry").status_code == 202
        after = client.get(f"/api/runs/{run_id}").json()
        map_row = next(row for row in after["node_runs"] if row["node_id"] == "map")
        map_artifact = client.get(f"/api/artifacts/{map_row['output_artifact_id']}").json()
    assert after["status"] == "succeeded"
    assert next(row for row in after["node_runs"] if row["id"] == target["id"])["attempt"] == 2
    assert next(row for row in after["node_runs"] if row["id"] == sibling["id"])["attempt"] == 1
    assert [item["index"] for item in map_artifact["content"]["items"]] == [0, 1]


def test_failed_node_can_retry_with_append_only_attempts(tmp_path) -> None:
    app = make_test_app(tmp_path / "retry.db")
    workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
    next(item for item in workflow.nodes if item.id == "brief").config["fail_attempts"] = 1

    with TestClient(app) as client:
        response = client.post("/api/runs", json={"workflow": workflow.model_dump(mode="json")})
        run_id = response.json()["runId"]
        failed = wait_for_status(client, run_id, {"failed"})
        rewrite = next(item for item in failed["node_runs"] if item["node_id"] == "brief")

        attempts = client.get(f"/api/node-runs/{rewrite['id']}/attempts").json()
        assert [(item["attempt"], item["status"]) for item in attempts] == [(1, "failed")]

        retry = client.post(f"/api/node-runs/{rewrite['id']}/retry")
        assert retry.status_code == 202
        succeeded = wait_for_status(client, run_id, {"succeeded"})
        rewrite = next(item for item in succeeded["node_runs"] if item["node_id"] == "brief")
        attempts = client.get(f"/api/node-runs/{rewrite['id']}/attempts").json()
        assert [(item["attempt"], item["status"]) for item in attempts] == [
            (1, "failed"), (2, "succeeded")
        ]


def test_identical_run_reuses_content_cache_with_new_artifact(tmp_path) -> None:
    app = make_test_app(tmp_path / "cache.db")
    with TestClient(app) as client:
        first_id = client.post(
            "/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")}
        ).json()["runId"]
        first = wait_for_status(client, first_id, {"succeeded"})

        second_id = client.post(
            "/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")}
        ).json()["runId"]
        second = wait_for_status(client, second_id, {"succeeded"})
        events = client.get(f"/api/runs/{second_id}/events").json()

        assert len([event for event in events if event["type"] == "node.cached"]) == 7
        first_rewrite = next(item for item in first["node_runs"] if item["node_id"] == "quality")
        second_rewrite = next(item for item in second["node_runs"] if item["node_id"] == "quality")
        assert first_rewrite["output_artifact_id"] != second_rewrite["output_artifact_id"]
        second_attempts = client.get(
            f"/api/node-runs/{second_rewrite['id']}/attempts"
        ).json()
        assert second_attempts[0]["status"] == "cached"
        assert second_attempts[0]["cached_from_artifact_id"]


def test_running_workflow_can_be_cancelled(tmp_path) -> None:
    app = make_test_app(tmp_path / "cancel.db")
    with TestClient(app) as client:
        run_id = client.post(
            "/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")}
        ).json()["runId"]
        response = client.post(f"/api/runs/{run_id}/cancel")
        assert response.status_code == 202

        cancelled = wait_for_status(client, run_id, {"cancelled"})
        assert all(item["output_artifact_id"] is None for item in cancelled["node_runs"])
        assert client.get(f"/api/runs/{run_id}/events").json()[-1]["type"] == "run.cancelled"
        deadline = time.monotonic() + 2
        while run_id in app.state.engine.tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        assert run_id not in app.state.engine.tasks
        assert run_id not in app.state.engine.cancelled


def test_event_broker_queue_is_bounded_and_drops_oldest() -> None:
    from whitebox.engine import EventBroker

    broker = EventBroker(queue_size=2)
    queue = broker.subscribe("run")
    broker.publish("run", {"value": 1})
    broker.publish("run", {"value": 2})
    broker.publish("run", {"value": 3})

    assert queue.maxsize == 2
    assert queue.get_nowait() == {"value": 2}
    assert queue.get_nowait() == {"value": 3}
    broker.unsubscribe("run", queue)
    assert "run" not in broker._subscribers


def test_prompt_cache_isolated_by_project_chapter_and_override(tmp_path) -> None:
    app = make_test_app(tmp_path / "prompt-cache-isolation.db")
    workflow = {
        "id": "prompt-cache", "name": "cache", "revision": 1,
        "nodes": [{
            "id": "call", "type": "ai.prompt_call", "position": {"x": 0, "y": 0},
            "config": {
                "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
                "system_prompt": "Project {{project.title}}", "user_prompt": "Chapter {{chapter.number}}",
                "prompt_id": "chapter.writer.system",
            },
        }], "edges": [],
    }
    with TestClient(app) as client:
        other = client.post("/api/projects", json={"title": "Other", "slug": "other"}).json()

        def run(project_id: str, chapter: int) -> list[dict]:
            run_id = client.post("/api/runs", json={
                "workflow": workflow, "project_id": project_id, "chapter_number": chapter,
            }).json()["runId"]
            wait_for_status(client, run_id, {"succeeded"})
            return client.get(f"/api/runs/{run_id}/events").json()

        assert not any(event["type"] == "node.cached" for event in run("demo-project", 1))
        assert any(event["type"] == "node.cached" for event in run("demo-project", 1))
        assert not any(event["type"] == "node.cached" for event in run("demo-project", 2))
        assert not any(event["type"] == "node.cached" for event in run(other["id"], 1))
        saved = client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "override"})
        assert saved.status_code == 200
        assert not any(event["type"] == "node.cached" for event in run("demo-project", 1))


def test_plain_run_honors_side_effect_permission(tmp_path) -> None:
    app = make_test_app(tmp_path / "run-side-effect.db")
    request = {"workflow": DEFAULT_WORKFLOW.model_dump(mode="json"), "allow_side_effects": False}
    with TestClient(app) as client:
        blocked = client.post("/api/runs", json=request)

    assert blocked.status_code == 409
    assert "archive" in blocked.text


def test_run_overrides_archive_path_with_current_project_context(tmp_path) -> None:
    app = make_test_app(tmp_path / "archive-context.db")
    workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
    archive = next(node for node in workflow.nodes if node.id == "archive")
    archive.config["chapter_path"] = "other-project/manuscript/stolen.md"
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "Safe", "slug": "safe"}).json()
        response = client.post("/api/runs", json={
            "workflow": workflow.model_dump(mode="json"), "project_id": project["id"],
            "chapter_number": 7, "allow_side_effects": True,
        })
        run = client.get(f"/api/runs/{response.json()['runId']}").json()

    frozen = next(node for node in run["snapshot"]["nodes"] if node["id"] == "archive")
    assert frozen["config"]["chapter_path"] == "safe/manuscript/chapter-0007.md"
    assert frozen["config"]["project_id"] == project["id"]


def test_new_app_instance_recovers_interrupted_node_attempt(tmp_path) -> None:
    database = tmp_path / "recovery.db"
    storage = Storage(database)
    storage.initialize()
    storage.ensure_demo_project()
    storage.ensure_default_connection()
    storage.ensure_default_model_profile()
    storage.ensure_writing_pipeline_profiles()
    profiles = {item.id: item for item in storage.list_model_profiles()}
    connections = {item.id: item for item in storage.list_provider_connections()}
    models = {(item.connection_id, item.model_id): item for item in storage.list_provider_models()}
    graph = compile_workflow(
        DEFAULT_WORKFLOW, model_profiles=profiles, provider_connections=connections,
        provider_models=models,
    ).execution_graph
    assert graph is not None
    graph.run_context = {
        "project_id": "demo-project", "project_title": "示例小说",
        "project_slug": "demo", "chapter_number": 1,
        "archive_path": "demo/manuscript/chapter-0001.md",
    }
    run_id = str(uuid4())
    node_run_ids = {node.id: str(uuid4()) for node in graph.nodes}
    storage.create_run(run_id, graph, node_run_ids)
    storage.update_run(run_id, "running")

    brief_id = node_run_ids["brief"]
    storage.update_node_run(brief_id, status="running", attempt=1)
    interrupted_attempt_id = str(uuid4())
    storage.create_attempt(interrupted_attempt_id, brief_id, 1, [])

    app = make_test_app(database)
    with TestClient(app) as client:
        recovered = wait_for_status(client, run_id, {"succeeded"})
        brief = next(item for item in recovered["node_runs"] if item["node_id"] == "brief")
        attempts = client.get(f"/api/node-runs/{brief['id']}/attempts").json()

    assert attempts[0]["status"] == "interrupted"
    assert attempts[1]["attempt"] == 2
    assert attempts[1]["status"] in {"succeeded", "cached"}
    assert any(event["type"] == "run.recovery.prepared" for event in client.get(f"/api/runs/{run_id}/events").json())


def test_legacy_node_run_migration_adds_input_snapshot(tmp_path) -> None:
    import sqlite3

    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TABLE node_runs ("
            "id TEXT PRIMARY KEY, run_id TEXT NOT NULL, node_id TEXT NOT NULL, "
            "node_type TEXT NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0, "
            "input_artifact_ids TEXT NOT NULL DEFAULT '[]', output_artifact_id TEXT, "
            "started_at TEXT, completed_at TEXT, error TEXT, UNIQUE(run_id, node_id))"
        )

    storage = Storage(database)
    storage.initialize()

    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(node_runs)")}
    assert "input_snapshot" in columns


def test_webui_provider_config_is_local_masked_and_actionable(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer saved-test-secret"
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [
                {"id": "deepseek-v4-pro", "owned_by": "deepseek", "object": "model"},
                {"id": "deepseek-v4-flash", "owned_by": "deepseek", "object": "model"},
            ]})
        if request.url.path == "/user/balance":
            return httpx.Response(200, json={
                "is_available": True,
                "balance_infos": [{
                    "currency": "CNY", "total_balance": "12.34",
                    "granted_balance": "2.00", "topped_up_balance": "10.34",
                }],
            })
        raise AssertionError(request.url.path)

    provider = DeepSeekProvider(transport=httpx.MockTransport(handler))
    secrets_path = tmp_path / "provider-secrets.json"
    app = create_app(tmp_path / "provider-config.db", provider, secrets_path)

    with TestClient(app) as client:
        saved = client.put("/api/providers/deepseek/config", json={
            "api_key": "saved-test-secret",
            "base_url": "https://api.deepseek.com",
            "default_model": "deepseek-v4-flash",
        })
        assert saved.status_code == 200
        status_payload = saved.json()
        assert status_payload["configured"] is True
        assert status_payload["keyHint"] == "...cret"
        assert "saved-test-secret" not in saved.text

        tested = client.post("/api/providers/deepseek/test")
        assert tested.status_code == 200
        assert tested.json()["modelCount"] == 2
        status_payload = client.get("/api/providers/deepseek/status").json()
        assert [item["id"] for item in status_payload["models"]] == [
            "deepseek-v4-flash", "deepseek-v4-pro"
        ]

        balance = client.get("/api/providers/deepseek/balance")
        assert balance.json()["balance_infos"][0]["total_balance"] == "12.34"

        cleared = client.delete("/api/providers/deepseek/key")
        assert cleared.json()["configured"] is False

    stored = json.loads(secrets_path.read_text(encoding="utf-8"))
    assert "api_key" not in stored["deepseek"]
    assert stat.S_IMODE(secrets_path.stat().st_mode) == 0o600


def test_node_model_and_temperature_are_frozen_per_run(tmp_path) -> None:
    app = make_test_app(tmp_path / "node-model.db")
    with TestClient(app) as client:
        workflow = client.get("/api/workflows/starter").json()
        draft = next(item for item in workflow["nodes"] if item["id"] == "draft")
        assert draft["config"]["connection_id"] == "deepseek-official"
        assert draft["config"]["model"] == "deepseek-v4-flash"
        assert draft["config"]["temperature"] == 0.8

        first_id = client.post("/api/runs", json={"workflow": workflow}).json()["runId"]
        first = wait_for_status(client, first_id, {"succeeded"})
        first_snapshot = next(item for item in first["snapshot"]["nodes"] if item["id"] == "draft")
        assert first_snapshot["config"]["model"] == "deepseek-v4-flash"
        assert first_snapshot["config"]["temperature"] == 0.8

        draft["config"]["model"] = "deepseek-v4-pro"
        draft["config"]["temperature"] = 0.4

        first_after_update = client.get(f"/api/runs/{first_id}").json()
        frozen = next(item for item in first_after_update["snapshot"]["nodes"] if item["id"] == "draft")
        assert frozen["config"]["model"] == "deepseek-v4-flash"
        assert frozen["config"]["temperature"] == 0.8

        second_id = client.post("/api/runs", json={"workflow": workflow}).json()["runId"]
        second = wait_for_status(client, second_id, {"succeeded"})
        refreshed = next(item for item in second["snapshot"]["nodes"] if item["id"] == "draft")
        assert refreshed["config"]["model"] == "deepseek-v4-pro"
        assert refreshed["config"]["temperature"] == 0.4


def test_unused_non_default_profile_can_be_deleted(tmp_path) -> None:
    app = make_test_app(tmp_path / "profile-delete.db")
    with TestClient(app) as client:
        created = client.post("/api/model-profiles", json={
            "name": "临时配置", "provider": "deepseek", "model": "deepseek-v4-flash",
            "temperature": 1, "max_tokens": 500, "thinking": False, "is_default": False,
        })
        assert created.status_code == 201
        profile_id = created.json()["id"]
        assert client.delete(f"/api/model-profiles/{profile_id}").status_code == 204
        assert all(item["id"] != profile_id for item in client.get("/api/model-profiles").json())


def test_official_deepseek_connection_rejects_untrusted_key_destinations(tmp_path) -> None:
    app = make_test_app(tmp_path / "trusted-origin.db")
    with TestClient(app) as client:
        for base_url in [
            "http://api.deepseek.com",
            "https://evil.example",
            "https://127.0.0.1:9000",
            "https://api.deepseek.com.evil.example",
            "https://api.deepseek.com/beta",
        ]:
            response = client.put("/api/providers/deepseek/config", json={
                "api_key": "test-secret", "base_url": base_url,
                "default_model": "deepseek-v4-flash",
            })
            assert response.status_code == 422


def test_only_default_profile_cannot_be_demoted(tmp_path) -> None:
    app = make_test_app(tmp_path / "default-invariant.db")
    with TestClient(app) as client:
        profile = client.get("/api/model-profiles").json()[0]
        response = client.put(f"/api/model-profiles/{profile['id']}", json={
            "name": profile["name"], "provider": "deepseek", "model": profile["model"],
            "temperature": profile["temperature"], "max_tokens": profile["max_tokens"],
            "thinking": profile["thinking"], "is_default": False,
        })
        assert response.status_code == 409
        assert sum(item["is_default"] for item in client.get("/api/model-profiles").json()) == 1


def test_startup_repairs_missing_default_profile(tmp_path) -> None:
    database = tmp_path / "repair-default.db"
    storage = Storage(database)
    storage.initialize()
    storage.create_model_profile("one", ModelProfileCreate(
        name="One", model="deepseek-v4-flash", is_default=False
    ))
    with storage._connect() as db:
        db.execute("DROP INDEX IF EXISTS idx_one_default_model_profile")
        db.execute("UPDATE model_profiles SET is_default=0")

    app = make_test_app(database)
    with TestClient(app) as client:
        profiles = client.get("/api/model-profiles").json()
        assert sum(item["is_default"] for item in profiles) == 1


def test_custom_provider_connection_supports_trusted_https_and_local_http(tmp_path) -> None:
    app = make_test_app(tmp_path / "connections.db")
    with TestClient(app) as client:
        public = client.post("/api/provider-connections", json={
            "name": "厂商 B", "protocol": "openai-compatible",
            "base_url": "https://api.vendor-b.example/v1", "provider_identity": "vendor-b",
            "trust_group": "vendor-b-official", "is_local": False,
            "trust_confirmed": True, "api_key": "vendor-b-secret",
        })
        assert public.status_code == 201
        assert public.json()["has_api_key"] is True
        assert "vendor-b-secret" not in public.text

        local = client.post("/api/provider-connections", json={
            "name": "本地 vLLM", "protocol": "openai-compatible",
            "base_url": "http://127.0.0.1:8002/v1", "provider_identity": "local-vllm",
            "trust_group": "local-machine", "is_local": True, "trust_confirmed": True,
        })
        assert local.status_code == 201

        rejected = client.post("/api/provider-connections", json={
            "name": "不可信 HTTP", "protocol": "openai-compatible",
            "base_url": "http://public.example/v1", "provider_identity": "unknown",
            "trust_group": "unknown", "is_local": False, "trust_confirmed": True,
        })
        assert rejected.status_code == 422


def test_same_source_models_never_block_user_selected_run(tmp_path) -> None:
    app = create_app(tmp_path / "user-choice.db", FakeDeepSeekProvider())
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")})
        assert response.status_code == 202
        run = wait_for_status(client, response.json()["runId"], {"succeeded"})

    assert run["snapshot"]["policy_report"]["assignments"]["writer"]["model"]


def test_global_model_catalog_persists_per_connection(tmp_path) -> None:
    database = tmp_path / "model-catalog.db"
    app = make_test_app(database)
    with TestClient(app) as client:
        connection = client.post("/api/provider-connections", json={
            "name": "本地模型", "protocol": "openai-compatible",
            "base_url": "http://127.0.0.1:8002/v1", "provider_identity": "local-vllm",
            "trust_group": "local-machine", "is_local": True, "trust_confirmed": True,
        }).json()
        model = client.post("/api/provider-models", json={
            "connection_id": connection["id"], "model_id": "qwen3-32b",
            "name": "Qwen3 32B", "family": "qwen3", "reasoning": True,
            "tool_call": True, "context_window": 131072, "max_output": 8192,
        })
        assert model.status_code == 201

    restarted = make_test_app(database)
    with TestClient(restarted) as client:
        models = client.get(f"/api/provider-models?connection_id={connection['id']}").json()

    assert len(models) == 1
    assert models[0]["model_id"] == "qwen3-32b"
    assert models[0]["family"] == "qwen3"
    assert models[0]["source"] == "manual"


def test_brain_profile_can_switch_to_any_model_in_global_catalog(tmp_path) -> None:
    app = make_test_app(tmp_path / "global-switch.db")
    with TestClient(app) as client:
        connection = client.post("/api/provider-connections", json={
            "name": "厂商 B", "protocol": "openai-compatible",
            "base_url": "https://vendor-b.example/v1", "provider_identity": "vendor-b",
            "trust_group": "vendor-b-official", "is_local": False,
            "trust_confirmed": True, "api_key": "vendor-secret",
        }).json()
        client.post("/api/provider-models", json={
            "connection_id": connection["id"], "model_id": "review-pro",
            "name": "Review Pro", "family": "vendor-b-v3", "reasoning": True,
            "tool_call": False, "context_window": 100000, "max_output": 8000,
        })
        profile = client.get("/api/model-profiles").json()[0]
        switched = client.put(f"/api/model-profiles/{profile['id']}", json={
            "name": profile["name"], "connection_id": connection["id"],
            "model": "review-pro", "model_family": "forged-family",
            "temperature": 0.3, "max_tokens": 1600, "thinking": True, "is_default": True,
        })

    assert switched.status_code == 200
    assert switched.json()["connection_id"] == connection["id"]
    assert switched.json()["model"] == "review-pro"
    assert switched.json()["model_family"] == "vendor-b-v3"


def test_run_pauses_for_approval_and_archives_only_after_approval(tmp_path) -> None:
    project_root = tmp_path / "project"
    app = create_app(
        tmp_path / "approval.db", FakeDeepSeekProvider(), project_root=project_root
    )
    with TestClient(app) as client:
        run_id = client.post(
            "/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")}
        ).json()["runId"]
        waiting = wait_for_status(client, run_id, {"waiting_approval"}, timeout=15)
        target = project_root / "demo" / "manuscript" / "chapter-0001.md"
        assert not target.exists()
        approval = next(
            item for item in client.get("/api/approvals").json()
            if item["run_id"] == run_id
        )
        decision = client.post(f"/api/approvals/{approval['id']}/decide", json={
            "decision": "approved", "actor": "author", "note": "终稿与 Diff 已检查",
        })
        assert decision.status_code == 200
        succeeded = wait_for_status(client, run_id, {"succeeded"}, timeout=15)

    assert target.exists()
    assert "只记得剑法" in target.read_text(encoding="utf-8")
    archive_run = next(item for item in succeeded["node_runs"] if item["node_id"] == "archive")
    assert archive_run["status"] == "succeeded"


def test_approved_author_edit_is_rechecked_before_archive(tmp_path) -> None:
    project_root = tmp_path / "author-edit-project"
    app = create_app(
        tmp_path / "author-edit.db", FakeDeepSeekProvider(), project_root=project_root
    )
    with TestClient(app) as client:
        run_id = client.post(
            "/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")}
        ).json()["runId"]
        wait_for_status(client, run_id, {"waiting_approval"}, timeout=15)
        approval = next(item for item in client.get("/api/approvals").json() if item["run_id"] == run_id)
        decision = client.post(f"/api/approvals/{approval['id']}/decide", json={
            "decision": "approved", "actor": "author", "note": "作者校改终稿",
            "edited_content": "这是作者在审核工作台确认的最终正文。",
        })
        assert decision.json()["status"] == "rechecking"
        wait_for_status(client, run_id, {"waiting_approval"}, timeout=15)
        refreshed = client.get(f"/api/runs/{run_id}").json()
        reviewer = next(item for item in refreshed["node_runs"] if item["node_id"] == "reviewer")
        reviewer_attempts = client.get(f"/api/node-runs/{reviewer['id']}/attempts").json()
        recheck_input = client.get(f"/api/artifacts/{reviewer_attempts[-1]['input_artifact_ids'][0]}").json()
        second_approval = next(item for item in client.get("/api/approvals").json() if item["run_id"] == run_id)
        assert second_approval["id"] != approval["id"]
        assert recheck_input["content"]["text"] == "这是作者在审核工作台确认的最终正文。"
        client.post(f"/api/approvals/{second_approval['id']}/decide", json={
            "decision": "approved", "actor": "author", "note": "复审证据已确认",
        })
        succeeded = wait_for_status(client, run_id, {"succeeded"}, timeout=15)
        archive_run = next(item for item in succeeded["node_runs"] if item["node_id"] == "archive")

    target = project_root / "demo" / "manuscript" / "chapter-0001.md"
    assert decision.status_code == 200
    assert target.exists()
    assert archive_run["status"] == "succeeded"


def test_rejected_approval_requires_actionable_note(tmp_path) -> None:
    app = create_app(tmp_path / "rejection-note.db", FakeDeepSeekProvider())
    with TestClient(app) as client:
        run_id = client.post(
            "/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")}
        ).json()["runId"]
        wait_for_status(client, run_id, {"waiting_approval"}, timeout=15)
        approval = next(item for item in client.get("/api/approvals").json() if item["run_id"] == run_id)
        response = client.post(f"/api/approvals/{approval['id']}/decide", json={
            "decision": "rejected", "actor": "author", "note": "",
        })

    assert response.status_code == 422


def test_ten_chapter_author_review_regression(tmp_path) -> None:
    project_root = tmp_path / "shadow-cthulhu-project"
    app = create_app(
        tmp_path / "shadow-cthulhu.db", FakeDeepSeekProvider(), project_root=project_root
    )
    inspiration = (
        "《我的影子是克苏鲁》：诡异、克苏鲁、幕后流、迪化。主角穿越到蒸汽朋克异世界，"
        "影子被上古邪神寄生；邪神想夺舍，却被更疯的主角反向 PUA，成为外置大脑和打手；"
        "世人误以为主角是隐秘伟大存在，邪神只是他的宠物。"
    )
    workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
    next(node for node in workflow.nodes if node.id == "brief").config["text"] = inspiration

    with TestClient(app) as client:
        project = client.post("/api/projects", json={
            "title": "我的影子是克苏鲁", "slug": "shadow-cthulhu",
            "brief": inspiration, "genre": "诡异 / 克苏鲁 / 幕后流 / 迪化",
        }).json()
        for chapter in range(1, 11):
            run_id = client.post("/api/runs", json={
                "workflow": workflow.model_dump(mode="json"),
                "project_id": project["id"], "chapter_number": chapter,
            }).json()["runId"]
            wait_for_status(client, run_id, {"waiting_approval"}, timeout=15)
            approval = next(item for item in client.get("/api/approvals").json() if item["run_id"] == run_id)
            response = client.post(f"/api/approvals/{approval['id']}/decide", json={
                "decision": "approved", "actor": "author",
                "note": f"第 {chapter} 章人工审阅完成",
            })
            assert response.status_code == 200
            wait_for_status(client, run_id, {"succeeded"}, timeout=15)

        refreshed = next(item for item in client.get("/api/projects").json() if item["id"] == project["id"])

    manuscript = project_root / "shadow-cthulhu" / "manuscript"
    assert refreshed["current_chapter"] == 11
    assert len(list(manuscript.glob("chapter-*.md"))) == 10
    for chapter in range(1, 11):
        assert (manuscript / f"chapter-{chapter:04d}.md").read_text(encoding="utf-8").strip()


def test_rejected_approval_reworks_selected_node_before_archive(tmp_path) -> None:
    project_root = tmp_path / "rejected-project"
    app = create_app(
        tmp_path / "rejected.db", FakeDeepSeekProvider(), project_root=project_root
    )
    with TestClient(app) as client:
        run_id = client.post(
            "/api/runs", json={"workflow": DEFAULT_WORKFLOW.model_dump(mode="json")}
        ).json()["runId"]
        wait_for_status(client, run_id, {"waiting_approval"}, timeout=15)
        approval = next(item for item in client.get("/api/approvals").json() if item["run_id"] == run_id)
        response = client.post(f"/api/approvals/{approval['id']}/decide", json={
            "decision": "rejected", "actor": "author", "note": "加强主角动机后重做",
            "rework_from": "reviser",
        })
        assert response.json()["status"] == "reworking"
        reworked = wait_for_status(client, run_id, {"waiting_approval"}, timeout=15)

    assert not (project_root / "demo" / "manuscript" / "chapter-0001.md").exists()
    assert next(item for item in reworked["node_runs"] if item["node_id"] == "archive")["status"] == "pending"
    reviser = next(item for item in reworked["snapshot"]["nodes"] if item["id"] == "revision")
    assert "加强主角动机后重做" in reviser["config"]["instruction"]


def test_projects_isolate_chapter_paths_and_advance_number(tmp_path) -> None:
    project_root = tmp_path / "books"
    app = create_app(
        tmp_path / "projects.db", FakeDeepSeekProvider(), project_root=project_root
    )
    with TestClient(app) as client:
        project = client.post("/api/projects", json={
            "title": "雨夜剑客", "slug": "rain-swordsman",
        }).json()
        run_id = client.post("/api/runs", json={
            "workflow": DEFAULT_WORKFLOW.model_dump(mode="json"),
            "project_id": project["id"], "chapter_number": 12,
        }).json()["runId"]
        run = wait_for_status(client, run_id, {"succeeded"}, timeout=20)
        projects = client.get("/api/projects").json()

    target = project_root / "rain-swordsman" / "manuscript" / "chapter-0012.md"
    assert target.exists()
    assert run["snapshot"]["run_context"]["project_title"] == "雨夜剑客"
    assert run["snapshot"]["run_context"]["chapter_number"] == 12
    assert next(item for item in projects if item["id"] == project["id"])["current_chapter"] == 13


def test_project_slug_rejects_path_escape(tmp_path) -> None:
    app = make_test_app(tmp_path / "project-security.db")
    with TestClient(app) as client:
        response = client.post("/api/projects", json={
            "title": "越界", "slug": "../escape",
        })
    assert response.status_code == 422


def test_project_assets_history_hash_and_path_isolation(tmp_path) -> None:
    project_root = tmp_path / "assets-books"
    app = create_app(
        tmp_path / "assets.db", FakeDeepSeekProvider(), project_root=project_root
    )
    with TestClient(app) as client:
        project = client.post("/api/projects", json={
            "title": "资产测试", "slug": "asset-book",
        }).json()
        run_id = client.post("/api/runs", json={
            "workflow": DEFAULT_WORKFLOW.model_dump(mode="json"),
            "project_id": project["id"], "chapter_number": 2,
        }).json()["runId"]
        wait_for_status(client, run_id, {"succeeded"}, timeout=20)

        assets = client.get(
            f"/api/projects/{project['id']}/assets?category=manuscript"
        ).json()
        assert len(assets) == 1
        content = client.get(
            f"/api/projects/{project['id']}/assets/{assets[0]['id']}"
        ).json()
        assert "只记得剑法" in content["content"]

        history = client.get(f"/api/projects/{project['id']}/chapters").json()
        assert history[0]["chapter_number"] == 2
        assert history[0]["file_matches_archive"] is True

        target = project_root / "asset-book" / "manuscript" / "chapter-0002.md"
        target.write_text("人工修改", encoding="utf-8")
        changed = client.get(f"/api/projects/{project['id']}/chapters").json()
        assert changed[0]["file_matches_archive"] is False

        proposals = client.get(
            f"/api/projects/{project['id']}/state-proposals"
        ).json()
        assert proposals[0]["schema_type"] == "writing.StatePatch@1"

        traversal = base64.urlsafe_b64encode(b"manuscript/../../provider-secrets.json").decode().rstrip("=")
        assert client.get(
            f"/api/projects/{project['id']}/assets/{traversal}"
        ).status_code == 404


def test_asset_versions_use_optimistic_concurrency(tmp_path) -> None:
    app = make_test_app(tmp_path / "asset-version.db")
    with TestClient(app) as client:
        project = client.get("/api/projects").json()[0]
        first = client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "world", "relative_name": "lore.md", "content": "v1",
            "expected_hash": None, "actor": "author", "note": "创建",
        })
        assert first.status_code == 200
        first_hash = first.json()["content_hash"]
        second = client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "world", "relative_name": "lore.md", "content": "v2",
            "expected_hash": first_hash, "actor": "author", "note": "补充设定",
        })
        assert second.status_code == 200
        conflict = client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "world", "relative_name": "lore.md", "content": "stale",
            "expected_hash": first_hash, "actor": "author", "note": "过期保存",
        })
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "ASSET_CONFLICT"
        asset = client.get(
            f"/api/projects/{project['id']}/assets?category=world"
        ).json()[0]
        versions = client.get(
            f"/api/projects/{project['id']}/assets/{asset['id']}/versions"
        ).json()

    assert [item["version"] for item in versions] == [2, 1]
    assert versions[0]["content"] == "v2"


def test_state_patch_requires_human_apply_and_is_idempotent(tmp_path) -> None:
    project_root = tmp_path / "state-books"
    app = create_app(
        tmp_path / "state-apply.db", FakeDeepSeekProvider(), project_root=project_root
    )
    with TestClient(app) as client:
        project = client.get("/api/projects").json()[0]
        run_id = client.post("/api/runs", json={
            "workflow": DEFAULT_WORKFLOW.model_dump(mode="json"),
            "project_id": project["id"], "chapter_number": 1,
        }).json()["runId"]
        wait_for_status(client, run_id, {"succeeded"}, timeout=20)
        proposal = client.get(
            f"/api/projects/{project['id']}/state-proposals"
        ).json()[0]
        target = project_root / "demo" / "state" / "chapter-observations.json"
        assert not target.exists()
        preview = client.get(
            f"/api/projects/{project['id']}/state-proposals/{proposal['id']}/preview"
        ).json()
        applied = client.post(
            f"/api/projects/{project['id']}/state-proposals/{proposal['id']}/apply",
            json={"expected_hashes": preview["expected_hashes"], "actor": "author", "note": "确认应用"},
        )
        assert applied.status_code == 200
        assert target.exists()
        duplicate = client.post(
            f"/api/projects/{project['id']}/state-proposals/{proposal['id']}/apply",
            json={"expected_hashes": {}, "actor": "author", "note": "重复"},
        )
        assert duplicate.status_code == 409

    state = json.loads(target.read_text(encoding="utf-8"))
    assert state["observations"][0]["finding_id"] == "F1"


def test_asset_version_diff_and_non_destructive_rollback(tmp_path) -> None:
    app = make_test_app(tmp_path / "rollback.db")
    with TestClient(app) as client:
        project = client.get("/api/projects").json()[0]
        v1 = client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "outline", "relative_name": "plan.md",
            "content": "第一幕\n旧结局\n", "expected_hash": None,
            "actor": "author", "note": "初稿",
        }).json()
        v2 = client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "outline", "relative_name": "plan.md",
            "content": "第一幕\n新结局\n", "expected_hash": v1["content_hash"],
            "actor": "author", "note": "修改结局",
        }).json()
        diff = client.get(
            f"/api/projects/{project['id']}/asset-version-diff?from_id={v1['id']}&to_id={v2['id']}"
        ).json()
        assert "-旧结局" in diff["unified_diff"]
        assert "+新结局" in diff["unified_diff"]

        asset = client.get(
            f"/api/projects/{project['id']}/assets?category=outline"
        ).json()[0]
        rolled = client.post(
            f"/api/projects/{project['id']}/assets/{asset['id']}/rollback",
            json={
                "target_version_id": v1["id"], "expected_hash": v2["content_hash"],
                "actor": "author", "note": "恢复初稿",
            },
        ).json()
        versions = client.get(
            f"/api/projects/{project['id']}/assets/{asset['id']}/versions"
        ).json()
        content = client.get(
            f"/api/projects/{project['id']}/assets/{asset['id']}"
        ).json()["content"]

    assert rolled["version"] == 3
    assert [item["version"] for item in versions] == [3, 2, 1]
    assert content == "第一幕\n旧结局\n"


def test_asset_version_diff_rejects_different_assets(tmp_path) -> None:
    app = make_test_app(tmp_path / "bad-diff.db")
    with TestClient(app) as client:
        project = client.get("/api/projects").json()[0]
        first = client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "world", "relative_name": "a.md", "content": "a",
            "expected_hash": None, "actor": "author", "note": "",
        }).json()
        second = client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "world", "relative_name": "b.md", "content": "b",
            "expected_hash": None, "actor": "author", "note": "",
        }).json()
        response = client.get(
            f"/api/projects/{project['id']}/asset-version-diff?from_id={first['id']}&to_id={second['id']}"
        )
    assert response.status_code == 400


def test_structured_state_patch_previews_and_applies_multiple_json_targets(tmp_path) -> None:
    project_root = tmp_path / "structured-state"
    database = tmp_path / "structured-state.db"
    app = create_app(database, FakeDeepSeekProvider(), project_root=project_root)
    with TestClient(app) as client:
        project = client.get("/api/projects").json()[0]
        world_v1 = client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "world", "relative_name": "rules.json",
            "content": '{"magic":{"limit":3},"tags":["old"],"removeMe":1}\n',
            "expected_hash": None, "actor": "author", "note": "初始规则",
        }).json()
        client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "characters", "relative_name": "hero.json",
            "content": '{"status":"asleep"}\n', "expected_hash": None,
            "actor": "author", "note": "初始人物",
        })
        run_id = client.post("/api/runs", json={
            "workflow": DEFAULT_WORKFLOW.model_dump(mode="json"),
            "project_id": project["id"], "chapter_number": 3,
        }).json()["runId"]
        wait_for_status(client, run_id, {"succeeded"}, timeout=20)
        proposal = client.get(f"/api/projects/{project['id']}/state-proposals").json()[0]

        patch = {
            "status": "proposed",
            "source_revision_artifact_id": proposal["content"]["source_revision_artifact_id"],
            "operations": [
                {"id": "OP1", "category": "world", "relative_name": "rules.json", "pointer": "/magic/limit", "operation": "set", "value": 5, "reason": "力量升级"},
                {"id": "OP2", "category": "world", "relative_name": "rules.json", "pointer": "/tags", "operation": "append", "value": "new", "reason": "新增标签"},
                {"id": "OP3", "category": "world", "relative_name": "rules.json", "pointer": "/removeMe", "operation": "remove", "reason": "删除旧字段"},
                {"id": "OP4", "category": "characters", "relative_name": "hero.json", "pointer": "/status", "operation": "set", "value": "awake", "reason": "人物苏醒"},
            ],
            "summary": "字段级更新",
        }
        storage = app.state.storage
        with storage._connect() as db:
            db.execute(
                "UPDATE artifacts SET content=? WHERE id=?",
                (json.dumps(patch, ensure_ascii=False), proposal["id"]),
            )

        preview = client.get(
            f"/api/projects/{project['id']}/state-proposals/{proposal['id']}/preview"
        ).json()
        assert len(preview["operations"]) == 4
        assert preview["operations"][0]["old_value"] == 3
        assert preview["operations"][0]["new_value"] == 5
        applied = client.post(
            f"/api/projects/{project['id']}/state-proposals/{proposal['id']}/apply",
            json={"expected_hashes": preview["expected_hashes"], "actor": "author", "note": "确认字段更新"},
        )
        assert applied.status_code == 200
        assert len(applied.json()) == 2

    world = json.loads((project_root / "demo" / "world" / "rules.json").read_text())
    hero = json.loads((project_root / "demo" / "characters" / "hero.json").read_text())
    assert world == {"magic": {"limit": 5}, "tags": ["old", "new"]}
    assert hero["status"] == "awake"


def test_skill_import_versions_and_run_snapshot_freezing(tmp_path) -> None:
    app = make_test_app(tmp_path / "skills.db")
    source_v1 = "---\nname: prose-style\ndescription: 控制文风\n---\n\n使用短句。"
    source_v2 = "---\nname: prose-style\ndescription: 控制文风\n---\n\n使用有节奏的短句。"
    with TestClient(app) as client:
        skill_v1 = client.post("/api/skills/import", json={
            "source": source_v1, "execution_mode": "context",
        }).json()
        workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
        next(item for item in workflow.nodes if item.id == "draft").config["skill_ids"] = [skill_v1["id"]]
        run_id = client.post("/api/runs", json={
            "workflow": workflow.model_dump(mode="json")
        }).json()["runId"]
        run = wait_for_status(client, run_id, {"succeeded"})
        skill_v2 = client.post("/api/skills/import", json={
            "source": source_v2, "execution_mode": "context",
        }).json()

    assert skill_v2["id"] == skill_v1["id"]
    assert skill_v2["current_version"]["version"] == 2
    draft_snapshot = next(item for item in run["snapshot"]["nodes"] if item["id"] == "draft")
    assert draft_snapshot["config"]["skill_snapshots"][0]["version"] == 1
    assert draft_snapshot["config"]["skill_snapshots"][0]["instructions"] == "使用短句。"


def test_subagent_skill_creates_independent_evidence_and_provider_call(tmp_path) -> None:
    app = make_test_app(tmp_path / "subagent-skill.db")
    with TestClient(app) as client:
        skill = client.post("/api/skills/import", json={
            "source": "---\nname: research-helper\ndescription: 独立研究素材\n---\n\n先独立分析任务并给主代理建议。",
            "execution_mode": "subagent",
        }).json()
        workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
        next(item for item in workflow.nodes if item.id == "draft").config["skill_ids"] = [skill["id"]]
        run_id = client.post("/api/runs", json={
            "workflow": workflow.model_dump(mode="json")
        }).json()["runId"]
        run = wait_for_status(client, run_id, {"succeeded"})
        draft_run = next(item for item in run["node_runs"] if item["node_id"] == "draft")
        attempts = client.get(f"/api/node-runs/{draft_run['id']}/attempts").json()
        calls = client.get(f"/api/attempts/{attempts[0]['id']}/provider-calls").json()
        draft_artifact = client.get(f"/api/artifacts/{draft_run['output_artifact_id']}").json()
        parent_artifacts = [client.get(f"/api/artifacts/{item}").json() for item in draft_artifact["parent_artifact_ids"]]
        events = client.get(f"/api/runs/{run_id}/events").json()

    assert len(calls) == 2
    assert any(item["schema_type"] == "skill.SubagentResult@1" for item in parent_artifacts)
    assert any(item["type"] == "skill.subagent.completed" for item in events)


def test_subagent_skill_reads_declared_project_asset_with_tool_evidence(tmp_path) -> None:
    app = create_app(tmp_path / "skill-tools.db", ToolCallingFakeProvider())
    with TestClient(app) as client:
        project = client.get("/api/projects").json()[0]
        client.post(f"/api/projects/{project['id']}/assets/save", json={
            "category": "world", "relative_name": "lore.md", "content": "世界只能使用一次魔法。",
            "expected_hash": None, "actor": "author", "note": "测试设定",
        })
        skill = client.post("/api/skills/import", json={
            "source": "---\nname: lore-reader\ndescription: 读取世界设定\nmetadata:\n  whitebox-capabilities:\n    - project.assets.read\n---\n读取 lore.md 后给出写作建议。",
            "execution_mode": "subagent",
        }).json()
        workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
        next(item for item in workflow.nodes if item.id == "draft").config["skill_ids"] = [skill["id"]]
        run_id = client.post("/api/runs", json={
            "workflow": workflow.model_dump(mode="json"), "project_id": project["id"],
        }).json()["runId"]
        run = wait_for_status(client, run_id, {"succeeded"})
        draft_run = next(item for item in run["node_runs"] if item["node_id"] == "draft")
        draft = client.get(f"/api/artifacts/{draft_run['output_artifact_id']}").json()
        subagent = next(
            client.get(f"/api/artifacts/{artifact_id}").json()
            for artifact_id in draft["parent_artifact_ids"]
            if client.get(f"/api/artifacts/{artifact_id}").json()["schema_type"] == "skill.SubagentResult@1"
        )
        tool = next(
            client.get(f"/api/artifacts/{artifact_id}").json()
            for artifact_id in subagent["parent_artifact_ids"]
            if client.get(f"/api/artifacts/{artifact_id}").json()["schema_type"] == "skill.ToolResult@1"
        )
        events = client.get(f"/api/runs/{run_id}/events").json()

    assert "一次魔法" in tool["content"]["result"]["content"]
    assert tool["content"]["tool_name"] == "project.assets.read"
    assert any(item["type"] == "skill.tool.completed" for item in events)


def test_skill_with_tool_capability_requires_subagent_mode(tmp_path) -> None:
    app = make_test_app(tmp_path / "skill-mode.db")
    with TestClient(app) as client:
        response = client.post("/api/skills/import", json={
            "source": "---\nname: lore-reader\ndescription: 读取设定\ncapabilities:\n  - project.assets.read\n---\n读取设定。",
            "execution_mode": "context",
        })
    assert response.status_code == 422
    assert "子代理模式" in response.text


def test_skill_binding_parameters_are_defaulted_frozen_and_injected(tmp_path) -> None:
    app = make_test_app(tmp_path / "skill-parameters.db")
    with TestClient(app) as client:
        skill = client.post("/api/skills/import", json={
            "source": "---\nname: style-control\ndescription: 文风控制\nparameters:\n  scope:\n    type: string\n    required: true\n  strictness:\n    type: number\n    default: 0.8\n---\n根据参数控制文风。",
            "execution_mode": "context",
        }).json()
        workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
        next(item for item in workflow.nodes if item.id == "draft").config["skill_bindings"] = [
            {"skill_id": skill["id"], "parameters": {"scope": "人物对白"}}
        ]
        run_id = client.post("/api/runs", json={
            "workflow": workflow.model_dump(mode="json")
        }).json()["runId"]
        run = wait_for_status(client, run_id, {"succeeded"})
        draft_snapshot = next(item for item in run["snapshot"]["nodes"] if item["id"] == "draft")
        draft_run = next(item for item in run["node_runs"] if item["node_id"] == "draft")
        attempt = client.get(f"/api/node-runs/{draft_run['id']}/attempts").json()[0]
        call = client.get(f"/api/attempts/{attempt['id']}/provider-calls").json()[0]

    snapshot = draft_snapshot["config"]["skill_snapshots"][0]
    assert snapshot["parameters"] == {"scope": "人物对白", "strictness": 0.8}
    system_prompt = call["request_payload"]["messages"][0]["content"]
    assert '"scope": "人物对白"' in system_prompt
    assert '"strictness": 0.8' in system_prompt


def test_skill_bundle_export_import_preview_conflicts_and_template_resolution(tmp_path) -> None:
    source_app = make_test_app(tmp_path / "bundle-source.db")
    with TestClient(source_app) as client:
        first = client.post("/api/skills/import", json={
            "source": "---\nname: style-a\ndescription: 风格 A\nparameters:\n  strength:\n    type: number\n    default: 0.5\n---\n执行风格 A。",
            "execution_mode": "context",
        }).json()
        second = client.post("/api/skills/import", json={
            "source": "---\nname: helper-b\ndescription: 助手 B\n---\n执行助手 B。",
            "execution_mode": "subagent",
        }).json()
        template = client.post("/api/skill-templates", json={
            "name": "写手套件", "description": "写手默认 Skills",
            "node_types": ["writing.llm_draft"],
            "skills": [
                {"skill_name": "style-a", "parameters": {"strength": 0.7}},
                {"skill_name": "helper-b", "parameters": {}},
            ],
        }).json()
        bundle = client.post("/api/skill-bundles/export", json={
            "name": "共享套件", "description": "测试",
            "skill_ids": [second["id"], first["id"]],
            "template_ids": [template["id"]],
        }).json()
        assert [item["name"] for item in bundle["skills"]] == ["helper-b", "style-a"]
        preview = client.post("/api/skill-bundles/import", json={
            "bundle": bundle, "apply": False,
        }).json()
        assert all(item["action"] == "reuse" for item in preview["preview"]["skills"])

    target_app = make_test_app(tmp_path / "bundle-target.db")
    with TestClient(target_app) as client:
        preview = client.post("/api/skill-bundles/import", json={
            "bundle": bundle, "apply": False,
        }).json()
        assert all(item["action"] == "create" for item in preview["preview"]["skills"])
        applied = client.post("/api/skill-bundles/import", json={
            "bundle": bundle, "apply": True,
        })
        assert applied.status_code == 200
        skills = client.get("/api/skills").json()
        templates = client.get("/api/skill-templates").json()
        resolved = client.get(f"/api/skill-templates/{templates[0]['id']}/bindings").json()

    assert {item["name"] for item in skills} == {"style-a", "helper-b"}
    assert resolved["bindings"][0]["parameters"] == {"strength": 0.7}


def test_skill_bundle_rejects_secrets_and_bad_hash(tmp_path) -> None:
    app = make_test_app(tmp_path / "bundle-security.db")
    bundle = {
        "format": "whitebox.skill-bundle", "version": 1, "name": "bad",
        "description": "", "skills": [{
            "name": "bad-skill", "description": "bad", "execution_mode": "context",
            "instructions": "x", "metadata": {"apiKey": "secret"},
            "capabilities": [], "parameters_schema": {}, "content_hash": "x",
        }],
        "node_templates": [], "content_hash": "forged",
    }
    with TestClient(app) as client:
        response = client.post("/api/skill-bundles/import", json={
            "bundle": bundle, "apply": False,
        })
    assert response.status_code == 422
    assert "敏感字段" in response.text


def test_subflow_roundtrip_preserves_nodes_ports_and_internal_edges(tmp_path) -> None:
    app = make_test_app(tmp_path / "subflow.db")
    draft = next(node for node in DEFAULT_WORKFLOW.nodes if node.id == "draft")
    reviewer = next(node for node in DEFAULT_WORKFLOW.nodes if node.id == "reviewer")
    edge = next(edge for edge in DEFAULT_WORKFLOW.edges if edge.id == "draft-reviewer")
    with TestClient(app) as client:
        created = client.post("/api/subflows", json={
            "name": "写作与审查", "description": "可复用子流程",
            "nodes": [draft.model_dump(mode="json"), reviewer.model_dump(mode="json")],
            "edges": [edge.model_dump(mode="json")],
        })
        assert created.status_code == 201
        listed = client.get("/api/subflows").json()

    assert len(listed) == 1
    assert {node["id"] for node in listed[0]["nodes"]} == {"draft", "reviewer"}
    assert listed[0]["edges"][0]["source"] == "draft"
