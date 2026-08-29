from fastapi.testclient import TestClient

from whitebox.main import create_app
from whitebox.providers import DeepSeekProvider
from whitebox.providers import ProviderResult
from whitebox.models import ProviderUsage
from whitebox.references import normalize_reference_text, split_reference_text


def test_reference_normalization_and_chunking_are_deterministic() -> None:
    source = "\ufeff第一章\r\n\r\n甲。\r\n\r\n第二章\r\n\r\n乙。"
    normalized = normalize_reference_text(source)
    assert normalized == "第一章\n\n甲。\n\n第二章\n\n乙。"
    chunks = split_reference_text(normalized, 6)
    assert "".join(chunks) == normalized
    assert split_reference_text(normalized, 6) == chunks


def test_reference_book_import_creates_project_workflow_and_stage(tmp_path) -> None:
    app = create_app(tmp_path / "reference.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        result = client.post("/api/projects/demo-project/reference-books/import", json={
            "filename": "sample.md", "content": "# 第一章\n\n主角醒来。\n\n# 第二章\n\n雨落下。",
            "chunk_size": 1000, "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
        })
        body = result.json()
        books = client.get("/api/projects/demo-project/reference-books").json()
        workflow = client.get(f"/api/workflows/{body['workflow']['id']}").json()
        canvas = client.get("/api/projects/demo-project/production-canvas").json()

    assert result.status_code == 201
    assert body["reference_book"]["chunk_count"] == 1
    assert len(books) == 1
    assert "normalized_content" not in books[0]
    assert "normalized_content" not in body["reference_book"]
    assert [node["type"] for node in workflow["nodes"]] == [
        "reference.book_source", "flow.split", "flow.map", "flow.join", "ai.prompt_call", "workflow.output",
    ]
    assert any(stage["id"] == body["stage"]["id"] and stage["workflow_id"] == workflow["id"] for stage in canvas["stages"])


def test_imported_reference_workflow_runs_map_and_report(tmp_path) -> None:
    class FakeProvider(DeepSeekProvider):
        async def stream_chat(self, *, model, messages, temperature, max_tokens, thinking, on_delta):
            text = "分块分析：主角在雨夜醒来。"
            if "综合以下" in messages[-1]["content"]:
                text = "# 拆书报告\n\n故事从失忆与秘密展开。"
            await on_delta(text)
            return ProviderResult(
                text=text, model=model, request_id="reference-test", finish_reason="stop",
                usage=ProviderUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18),
                request_payload={}, response_payload={},
            )

    app = create_app(tmp_path / "reference-run.db", FakeProvider())
    with TestClient(app) as client:
        imported = client.post("/api/projects/demo-project/reference-books/import", json={
            "filename": "book.txt", "content": "第一章\n\n雨夜里，主角醒来。\n\n第二章\n\n秘密出现。",
            "chunk_size": 1000, "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
        }).json()
        run_id = client.post("/api/runs", json={
            "workflow": imported["workflow"], "project_id": "demo-project", "chapter_number": 1,
        }).json()["runId"]
        deadline = 20
        import time
        while deadline > 0:
            run = client.get(f"/api/runs/{run_id}").json()
            if run["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.1)
            deadline -= 0.1
        assert run["status"] == "succeeded"
        report_run = next(item for item in run["node_runs"] if item["node_id"] == "report")
        report = client.get(f"/api/artifacts/{report_run['output_artifact_id']}").json()

    assert report["schema_type"] == "ai.PromptResult@1"
    assert "拆书报告" in report["content"]["text"]


def test_duplicate_reference_import_reuses_existing_stage(tmp_path) -> None:
    app = create_app(tmp_path / "reference-dedupe.db", DeepSeekProvider(api_key="test"))
    payload = {
        "filename": "book.md", "content": "# 第一章\n\n同一份素材。",
        "chunk_size": 1000, "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
    }
    with TestClient(app) as client:
        first = client.post("/api/projects/demo-project/reference-books/import", json=payload).json()
        second = client.post("/api/projects/demo-project/reference-books/import", json=payload).json()
        books = client.get("/api/projects/demo-project/reference-books").json()
        canvas = client.get("/api/projects/demo-project/production-canvas").json()

    assert first["reference_book"]["id"] == second["reference_book"]["id"]
    assert first["workflow"]["id"] == second["workflow"]["id"]
    assert len(books) == 1
    assert sum(stage["workflow_id"] == first["workflow"]["id"] for stage in canvas["stages"]) == 1


def test_reference_import_rejects_unsafe_filename_and_nul_content(tmp_path) -> None:
    app = create_app(tmp_path / "reference-input-validation.db", DeepSeekProvider(api_key="test"))
    base = {"content": "有效内容", "chunk_size": 1000, "connection_id": "deepseek-official", "model": "deepseek-v4-flash"}
    with TestClient(app) as client:
        unsafe = client.post("/api/projects/demo-project/reference-books/import", json={**base, "filename": "../book.txt"})
        nul = client.post("/api/projects/demo-project/reference-books/import", json={**base, "filename": "book.txt", "content": "坏\u0000内容"})

    assert unsafe.status_code == 422
    assert nul.status_code == 422
