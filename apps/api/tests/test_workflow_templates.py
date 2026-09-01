from fastapi.testclient import TestClient

from whitebox.main import DEFAULT_WORKFLOW, create_app
from whitebox.providers import DeepSeekProvider
from whitebox.official_prompts import OFFICIAL_PROMPT_PACK_ID, OFFICIAL_PROMPT_PACK_REVISION


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


def test_official_prompt_manifest_is_versioned(tmp_path) -> None:
    app = create_app(tmp_path / "prompt-manifest.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        response = client.get("/api/official-prompts")

    assert response.status_code == 200
    body = response.json()
    assert body["pack_id"] == OFFICIAL_PROMPT_PACK_ID
    assert body["pack_revision"] == OFFICIAL_PROMPT_PACK_REVISION
    assert "chapter.writer.system" in body["prompts"]
    assert "book.setup.generate" in body["prompts"]


def test_official_prompt_can_be_read_by_stable_id(tmp_path) -> None:
    app = create_app(tmp_path / "prompt-detail.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        response = client.get("/api/official-prompts/chapter.writer.system")

    assert response.status_code == 200
    assert response.json()["pack_id"] == OFFICIAL_PROMPT_PACK_ID
    assert "章节任务" in response.json()["content"]


def test_stage_prompt_ids_are_stable_in_official_workflows(tmp_path) -> None:
    app = create_app(tmp_path / "stage-prompts.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflows = {item["id"]: item for item in client.get("/api/workflows").json()}
    setup = workflows["official-book-setup"]
    configs = [node["config"] for node in setup["nodes"] if node["id"] in {"generate", "refine"}]
    assert {config["prompt_pack"] for config in configs} == {OFFICIAL_PROMPT_PACK_ID}
    assert {config["prompt_id"] for config in configs} == {"book.setup.generate", "book.setup.refine"}


def test_stage_prompt_details_are_available_for_audit(tmp_path) -> None:
    app = create_app(tmp_path / "stage-prompt-detail.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        response = client.get("/api/official-prompts/world.generate")
    assert response.status_code == 200
    assert "世界规则" in response.json()["content"]


def test_unknown_official_prompt_returns_not_found(tmp_path) -> None:
    app = create_app(tmp_path / "prompt-missing.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        response = client.get("/api/official-prompts/does-not-exist")
    assert response.status_code == 404


def test_prompt_override_is_versioned_and_conflicts_are_rejected(tmp_path) -> None:
    app = create_app(tmp_path / "prompt-override.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        first = client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "项目写手规则"})
        second = client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "第二版", "expected_revision": 1})
        conflict = client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "冲突版", "expected_revision": 1})

    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert second.status_code == 200
    assert second.json()["revision"] == 2
    assert conflict.status_code == 409


def test_prompt_override_diff_reports_official_and_project_versions(tmp_path) -> None:
    app = create_app(tmp_path / "prompt-diff.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "项目规则"})
        diff = client.get("/api/projects/demo-project/prompt-overrides/chapter.writer.system/diff")

    assert diff.status_code == 200
    assert diff.json()["overridden"] is True
    assert diff.json()["project_revision"] == 1
    assert diff.json()["same"] is False
    assert "项目规则" in diff.json()["unified_diff"]


def test_prompt_override_can_be_deleted_with_revision_guard(tmp_path) -> None:
    app = create_app(tmp_path / "prompt-delete.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        created = client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "项目规则"}).json()
        conflict = client.delete(f"/api/projects/demo-project/prompt-overrides/chapter.writer.system?expected_revision=2")
        deleted = client.delete(f"/api/projects/demo-project/prompt-overrides/chapter.writer.system?expected_revision={created['revision']}")
        current = client.get("/api/projects/demo-project/prompt-overrides/chapter.writer.system").json()
    assert conflict.status_code == 409
    assert deleted.status_code == 200
    assert current["revision"] == 0


def test_prompt_override_history_is_immutable_and_restorable(tmp_path) -> None:
    app = create_app(tmp_path / "prompt-history.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "第一版"})
        client.put("/api/projects/demo-project/prompt-overrides/chapter.writer.system", json={"content": "第二版", "expected_revision": 1})
        versions = client.get("/api/projects/demo-project/prompt-overrides/chapter.writer.system/versions").json()
        restored = client.post("/api/projects/demo-project/prompt-overrides/chapter.writer.system/versions/1/restore")
    assert [item["revision"] for item in versions] == [2, 1]
    assert restored.status_code == 200
    assert restored.json()["revision"] == 3
    assert restored.json()["content"] == "第一版"


def test_only_unreferenced_non_official_workflow_can_be_deleted(tmp_path) -> None:
    app = create_app(tmp_path / "workflow-delete.db", DeepSeekProvider(api_key="test"))
    workflow = {"id": "deletable", "name": "可删除", "revision": 1, "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "x"}}], "edges": []}
    with TestClient(app) as client:
        client.put("/api/workflows/deletable", json=workflow)
        deleted = client.delete("/api/workflows/deletable")
        official = client.delete("/api/workflows/starter")
        missing = client.get("/api/workflows/deletable")
    assert deleted.status_code == 204
    assert official.status_code == 403
    assert missing.status_code == 404


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
