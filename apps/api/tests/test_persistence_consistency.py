from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from whitebox.main import create_app
from whitebox.models import Artifact, ExecutionGraph, ExecutionNode, ProviderUsage
from whitebox.providers import DeepSeekProvider


def test_concurrent_asset_create_has_one_winner_and_one_version(tmp_path) -> None:
    app = create_app(
        tmp_path / "asset-race.db",
        DeepSeekProvider(api_key="test"),
        project_root=tmp_path / "projects",
    )
    with TestClient(app) as client:
        project_id = client.get("/api/projects").json()[0]["id"]

        def save(content: str):
            return client.post(
                f"/api/projects/{project_id}/assets/save",
                json={
                    "category": "world",
                    "relative_name": "race.md",
                    "content": content,
                    "expected_hash": None,
                },
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(save, ("first", "second")))

        assert sorted(response.status_code for response in responses) == [200, 409]
        asset = client.get(
            f"/api/projects/{project_id}/assets?category=world"
        ).json()[0]
        versions = client.get(
            f"/api/projects/{project_id}/assets/{asset['id']}/versions"
        ).json()

    assert len(versions) == 1
    assert versions[0]["content"] in {"first", "second"}


def test_workflow_and_canvas_reject_stale_revisions(tmp_path) -> None:
    app = create_app(tmp_path / "revisions.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflow = client.post("/api/workflows/blank", json={"name": "并发编辑"}).json()
        workflow_url = f"/api/workflows/{workflow['id']}"
        updated = {**workflow, "revision": workflow["revision"] + 1, "name": "winner"}
        assert client.put(workflow_url, json=updated).status_code == 200
        stale = client.put(
            workflow_url,
            params={"expected_revision": workflow["revision"]},
            json={**updated, "revision": updated["revision"] + 1, "name": "stale"},
        )

        canvas = client.get("/api/projects/demo-project/production-canvas").json()
        expected_canvas_revision = canvas["revision"]
        canvas["revision"] += 1
        canvas["edges"] = []
        first = client.put(
            "/api/projects/demo-project/production-canvas",
            params={"expected_revision": expected_canvas_revision}, json=canvas,
        )
        second = client.put(
            "/api/projects/demo-project/production-canvas",
            params={"expected_revision": expected_canvas_revision}, json=canvas,
        )

    assert stale.status_code == 409
    assert first.status_code == 200
    assert first.json()["revision"] == canvas["revision"]
    assert second.status_code == 409


def test_official_workflow_cannot_be_overwritten(tmp_path) -> None:
    app = create_app(tmp_path / "official-readonly.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflow = client.get("/api/workflows/starter").json()
        response = client.put(
            "/api/workflows/starter",
            json={**workflow, "revision": workflow["revision"] + 1, "name": "不应保存"},
        )

    assert response.status_code == 403


def test_canvas_requires_existing_published_revision(tmp_path) -> None:
    app = create_app(tmp_path / "pinned-validation.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        canvas = client.get("/api/projects/demo-project/production-canvas").json()
        canvas["stages"][0]["workflow_revision"] = 999999
        response = client.put(
            "/api/projects/demo-project/production-canvas", json=canvas
        )

    assert response.status_code == 422
    assert "发布版本不存在" in response.text


def test_run_filters_and_attempt_calls_enforce_matching_project(tmp_path) -> None:
    app = create_app(tmp_path / "project-scope.db", DeepSeekProvider(api_key="test"))
    storage = app.state.storage
    with TestClient(app) as client:
        workflow = {
            "id": "scope-source",
            "name": "scope",
            "revision": 1,
            "nodes": [{
                "id": "source",
                "type": "mock.source",
                "position": {"x": 0, "y": 0},
                "config": {"text": "private"},
            }],
            "edges": [],
        }
        project = client.post(
            "/api/projects", json={"title": "scope", "slug": "scope"}
        ).json()
        run_id = client.post(
            "/api/runs", json={"workflow": workflow, "project_id": project["id"]}
        ).json()["runId"]
        run = storage.get_run(run_id)
        node_run_id = run.node_runs[0].id

        assert client.get(
            f"/api/runs/{run_id}", params={"project_id": "demo-project"}
        ).status_code == 404
        assert client.get(
            f"/api/runs/{run_id}", params={"project_id": project["id"]}
        ).status_code == 200
        assert client.get(f"/api/node-runs/{node_run_id}/attempts").status_code == 200
        assert client.get(
            f"/api/node-runs/{node_run_id}/attempts",
            params={"project_id": "demo-project"},
        ).status_code == 404
        assert client.get(
            f"/api/node-runs/{node_run_id}/attempts",
            params={"project_id": project["id"]},
        ).status_code == 200


def test_provider_audit_payloads_are_bounded(tmp_path) -> None:
    app = create_app(tmp_path / "payload.db", DeepSeekProvider(api_key="test"))
    storage = app.state.storage
    with TestClient(app):
        try:
            storage.create_provider_call(
                "call", "missing-attempt", "test", "test", {"data": "x" * (8 * 1024 * 1024)}
            )
        except ValueError as exc:
            assert "超过 8 MB" in str(exc)
        else:
            raise AssertionError("oversized provider request was accepted")

        try:
            storage.complete_provider_call(
                "missing-call",
                status="succeeded",
                response_payload={"data": "x" * (8 * 1024 * 1024)},
                usage=ProviderUsage(),
            )
        except ValueError as exc:
            assert "超过 8 MB" in str(exc)
        else:
            raise AssertionError("oversized provider response was accepted")


def test_state_patch_failure_restores_all_files_versions_and_claim(tmp_path, monkeypatch) -> None:
    projects = tmp_path / "state-projects"
    app = create_app(
        tmp_path / "state-rollback.db",
        DeepSeekProvider(api_key="test"),
        project_root=projects,
    )
    storage = app.state.storage
    with TestClient(app, raise_server_exceptions=False) as client:
        project = client.get("/api/projects").json()[0]
        initial = {}
        for category, name in (("world", "rules.json"), ("characters", "hero.json")):
            response = client.post(
                f"/api/projects/{project['id']}/assets/save",
                json={
                    "category": category,
                    "relative_name": name,
                    "content": '{"value":"old"}\n',
                    "expected_hash": None,
                },
            )
            initial[f"{category}/{name}"] = response.json()["content_hash"]

        graph = ExecutionGraph(
            workflow_id="patch-test",
            workflow_revision=1,
            nodes=[ExecutionNode(
                id="proposal", type="mock.source", config={}, dependencies=[]
            )],
            target_node_ids=["proposal"],
            graph_hash="test",
            run_context={"project_id": project["id"]},
        )
        run_id = str(uuid4())
        node_run_id = str(uuid4())
        storage.create_run(run_id, graph, {"proposal": node_run_id})
        patch = {
            "status": "proposed",
            "source_revision_artifact_id": "source",
            "operations": [
                {"id": "one", "category": "world", "relative_name": "rules.json", "pointer": "/value", "operation": "set", "value": "new", "reason": "test"},
                {"id": "two", "category": "characters", "relative_name": "hero.json", "pointer": "/value", "operation": "set", "value": "new", "reason": "test"},
            ],
            "summary": "rollback",
        }
        artifact = Artifact(
            id=str(uuid4()), run_id=run_id, node_run_id=node_run_id,
            schema_type="writing.StatePatch@1", content=patch,
            content_hash=hashlib.sha256(json.dumps(patch).encode()).hexdigest(),
            parent_artifact_ids=[], created_at=datetime.now(UTC),
        )
        storage.save_artifact(artifact)
        original_create = storage.create_asset_version
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                original_create(*args, **kwargs)
                raise RuntimeError("simulated version failure")
            return original_create(*args, **kwargs)

        monkeypatch.setattr(storage, "create_asset_version", fail_second)
        response = client.post(
            f"/api/projects/{project['id']}/state-proposals/{artifact.id}/apply",
            json={"expected_hashes": initial},
        )

        assert response.status_code == 500
        assert not storage.state_patch_was_applied(project["id"], artifact.id)
        assert storage.list_asset_versions(project["id"], "world/rules.json")[0].version == 1
        assert json.loads((projects / "demo/world/rules.json").read_text())["value"] == "old"
        assert json.loads((projects / "demo/characters/hero.json").read_text())["value"] == "old"
