from fastapi.testclient import TestClient

from whitebox.main import create_app
from whitebox.providers import DeepSeekProvider


def test_publishing_workflow_creates_immutable_revision(tmp_path) -> None:
    app = create_app(tmp_path / "versions.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflow = client.post("/api/workflows/blank", json={"name": "版本测试"}).json()
        workflow_url = f"/api/workflows/{workflow['id']}"
        published = client.post(f"{workflow_url}/publish", json={"note": "初始版本"})
        versions = client.get(f"{workflow_url}/versions")
        client.put(workflow_url, json={**workflow, "revision": workflow["revision"] + 1})
        latest = client.post(f"{workflow_url}/publish", json={"note": "第二版"})

    assert published.status_code == 201
    assert versions.status_code == 200
    assert versions.json()[0]["revision"] == workflow["revision"]
    assert latest.status_code == 201
    assert latest.json()["revision"] == workflow["revision"] + 1
    assert len(versions.json()) == 1


def test_component_can_pin_a_published_workflow_revision(tmp_path) -> None:
    app = create_app(tmp_path / "pinned.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflow = client.get("/api/workflows/starter").json()
        published = client.post("/api/workflows/starter/publish", json={"note": "锁定测试"}).json()
        project = client.post("/api/projects", json={"title": "锁定版本", "slug": "pinned"}).json()
        updated = {**workflow, "revision": workflow["revision"] + 1, "name": "草稿已变化"}
        assert client.put("/api/workflows/starter", json=updated).status_code == 403
        pinned = client.patch(f"/api/projects/{project['id']}/production-stages/setup", json={
            "workflow_id": "starter", "workflow_revision": published["revision"],
        }).json()
        canvas = client.get(f"/api/projects/{project['id']}/production-canvas").json()

    setup = next(item for item in canvas["stages"] if item["id"] == "setup")
    assert pinned["workflow_revision"] == published["revision"]
    assert setup["workflow_revision"] == published["revision"]


def test_workflow_version_diff_and_restore_create_new_draft(tmp_path) -> None:
    app = create_app(tmp_path / "version-restore.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflow = client.post("/api/workflows/blank", json={"name": "恢复测试"}).json()
        workflow_url = f"/api/workflows/{workflow['id']}"
        published = client.post(f"{workflow_url}/publish", json={"note": "可恢复"}).json()
        changed = {**workflow, "revision": workflow["revision"] + 1, "name": "临时草稿"}
        client.put(workflow_url, json=changed)
        diff = client.get(f"{workflow_url}/versions/{published['revision']}/diff")
        restored = client.post(f"{workflow_url}/restore", json={"revision": published["revision"]})

    assert diff.status_code == 200
    assert "临时草稿" in diff.json()["unified_diff"]
    assert restored.status_code == 200
    assert restored.json()["name"] == workflow["name"]
    assert restored.json()["revision"] > changed["revision"]
