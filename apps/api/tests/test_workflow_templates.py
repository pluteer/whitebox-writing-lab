from fastapi.testclient import TestClient

from whitebox.main import DEFAULT_WORKFLOW, create_app
from whitebox.providers import DeepSeekProvider


def mappings_for(bundle: dict) -> dict:
    return {
        slot["id"]: {
            "connection_id": "deepseek-official",
            "model": "deepseek-v4-flash",
        }
        for slot in bundle["model_slots"]
    }


def test_workflow_template_export_is_portable_and_creates_copy(tmp_path) -> None:
    app = create_app(tmp_path / "workflow-template.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        exported = client.post("/api/workflow-templates/export", json={
            "workflow": DEFAULT_WORKFLOW.model_dump(mode="json"),
            "name": "写审裁修模板", "description": "完整流程",
        })
        assert exported.status_code == 200
        bundle = exported.json()
        assert {slot["id"] for slot in bundle["model_slots"]} == {
            "writer_model", "reviewer_model", "arbiter_model", "editor_model"
        }
        for node in bundle["nodes"]:
            if node["model_slot"]:
                assert "connection_id" not in node["config"]
                assert "model" not in node["config"]
        original = client.get("/api/workflows/starter").json()
        preview = client.post("/api/workflow-templates/import", json={
            "bundle": bundle, "model_mappings": mappings_for(bundle), "create": False,
        }).json()
        assert preview["can_create"] is True
        created = client.post("/api/workflow-templates/import", json={
            "bundle": bundle, "model_mappings": mappings_for(bundle), "create": True,
            "workflow_name": "我的流程副本",
        })
        assert created.status_code == 200
        document = created.json()["workflow"]
        workflows = client.get("/api/workflows").json()
        original_after = client.get("/api/workflows/starter").json()

    assert document["id"] != "starter"
    assert document["name"] == "我的流程副本"
    assert len(document["nodes"]) == len(DEFAULT_WORKFLOW.nodes)
    assert {item["id"] for item in workflows} >= {"starter", document["id"]}
    assert original_after == original


def test_workflow_template_missing_skill_requires_bundle_first(tmp_path) -> None:
    source = create_app(tmp_path / "workflow-skill-source.db", DeepSeekProvider(api_key="test"))
    with TestClient(source) as client:
        skill = client.post("/api/skills/import", json={
            "source": "---\nname: template-skill\ndescription: 模板技能\n---\n执行技能。",
            "execution_mode": "context",
        }).json()
        workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
        next(item for item in workflow.nodes if item.id == "draft").config["skill_bindings"] = [
            {"skill_id": skill["id"], "parameters": {}}
        ]
        bundle = client.post("/api/workflow-templates/export", json={
            "workflow": workflow.model_dump(mode="json"), "name": "含技能模板",
        }).json()

    target = create_app(tmp_path / "workflow-skill-target.db", DeepSeekProvider(api_key="test"))
    with TestClient(target) as client:
        preview = client.post("/api/workflow-templates/import", json={
            "bundle": bundle, "model_mappings": mappings_for(bundle), "create": False,
        }).json()
        create = client.post("/api/workflow-templates/import", json={
            "bundle": bundle, "model_mappings": mappings_for(bundle), "create": True,
        })

    assert preview["missing_skills"] == ["template-skill"]
    assert preview["can_create"] is False
    assert create.status_code == 409


def test_workflow_template_rejects_local_binding_fields(tmp_path) -> None:
    app = create_app(tmp_path / "workflow-bad.db", DeepSeekProvider(api_key="test"))
    bundle = {
        "format": "whitebox.workflow-template", "version": 1,
        "name": "bad", "description": "", "model_slots": [],
        "required_skills": [], "run_parameters": {}, "edges": [],
        "nodes": [{
            "id": "n", "type": "mock.source", "position": {"x": 0, "y": 0},
            "config": {"connection_id": "local-id"}, "model_slot": None,
        }],
    }
    with TestClient(app) as client:
        response = client.post("/api/workflow-templates/import", json={
            "bundle": bundle, "model_mappings": {}, "create": False,
        })
    assert response.status_code == 422
    assert "本机绑定字段" in response.text
