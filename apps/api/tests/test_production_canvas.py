from fastapi.testclient import TestClient

from whitebox.main import create_app
from whitebox.providers import DeepSeekProvider
from whitebox.models import Position, ProductionCanvas, ProductionStage, WorkflowDocument, WorkflowNode, WorkflowParameter
from whitebox.production import compose_production_canvas


def test_projects_get_isolated_default_production_canvases(tmp_path) -> None:
    app = create_app(tmp_path / "production.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        first = client.post("/api/projects", json={"title": "第一本", "slug": "first"}).json()
        second = client.post("/api/projects", json={"title": "第二本", "slug": "second"}).json()
        first_canvas = client.get(f"/api/projects/{first['id']}/production-canvas").json()
        second_canvas = client.get(f"/api/projects/{second['id']}/production-canvas").json()
        workflow_ids = {item["id"] for item in client.get("/api/workflows").json()}

    assert first_canvas["project_id"] == first["id"]
    assert second_canvas["project_id"] == second["id"]
    assert len(first_canvas["stages"]) == 8
    assert next(item for item in first_canvas["stages"] if item["id"] == "chapter")["workflow_id"] == "starter"
    assert next(item for item in first_canvas["stages"] if item["id"] == "analysis")["workflow_id"] is None
    assert all(item["workflow_id"] for item in first_canvas["stages"] if item["id"] != "analysis")
    assert workflow_ids >= {
        "official-book-setup", "official-world-building", "official-character-design",
        "official-story-planning", "official-outline-planning",
        "official-post-chapter-update", "starter",
    }


def test_existing_canvas_recovers_missing_official_stages(tmp_path) -> None:
    app = create_app(tmp_path / "production-repair.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "恢复测试", "slug": "repair"}).json()
        canvas = client.get(f"/api/projects/{project['id']}/production-canvas").json()
        canvas["stages"] = [stage for stage in canvas["stages"] if stage["id"] not in {"setup", "world"}]
        canvas["edges"] = []
        assert client.put(f"/api/projects/{project['id']}/production-canvas", json=canvas).status_code == 200
        repaired = client.get(f"/api/projects/{project['id']}/production-canvas").json()

    assert {stage["id"] for stage in repaired["stages"]} >= {"setup", "world", "chapter", "analysis"}
    assert any(edge["id"] == "setup-world" for edge in repaired["edges"])


def test_component_parameters_are_applied_to_composed_node() -> None:
    workflow = WorkflowDocument.model_validate({
        "id": "parameterized", "name": "Parameterized", "revision": 2,
        "parameters": [{"id": "tone", "title": "Tone", "type": "string", "default": "calm", "target_node_id": "source", "target_config_key": "text"}],
        "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "default"}}], "edges": [],
    })
    canvas = ProductionCanvas(project_id="p", stages=[ProductionStage(id="stage", title="Stage", description="", position=Position(x=0, y=0), workflow_id="parameterized", parameter_values={"tone": "bright"})], edges=[])

    composed = compose_production_canvas(canvas, {"parameterized": workflow}, "p")

    assert composed.nodes[0].config["text"] == "bright"


def test_production_stage_binding_and_status(tmp_path) -> None:
    app = create_app(tmp_path / "production-status.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"title": "测试书", "slug": "status"}).json()
        update = client.patch(
            f"/api/projects/{project['id']}/production-stages/world",
            json={"workflow_id": "starter"},
        )
        status = client.get(f"/api/projects/{project['id']}/production-status").json()
        missing = client.patch(
            f"/api/projects/{project['id']}/production-stages/world",
            json={"workflow_id": "missing"},
        )

    assert update.status_code == 200
    world = next(item for item in status if item["stage_id"] == "world")
    assert world["configured"] is True
    assert world["node_count"] == 10
    assert world["official_workflow_id"] == "official-world-building"
    assert missing.status_code == 422


def test_production_status_does_not_leak_shared_workflow_runs_between_projects(tmp_path) -> None:
    import time

    def wait_for_success(client, run_id: str) -> None:
        for _ in range(300):
            status = client.get(f"/api/runs/{run_id}").json()["status"]
            if status == "succeeded":
                return
            time.sleep(0.05)
        raise AssertionError("run did not reach approval")

    app = create_app(tmp_path / "production-isolation.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        first = client.post("/api/projects", json={"title": "甲书", "slug": "book-a"}).json()
        second = client.post("/api/projects", json={"title": "乙书", "slug": "book-b"}).json()
        workflow = {"id": "shared-source", "name": "Shared source", "revision": 1, "nodes": [{"id": "source", "type": "mock.source", "position": {"x": 0, "y": 0}, "config": {"text": "独立项目"}}], "edges": []}
        assert client.put("/api/workflows/shared-source", json=workflow).status_code == 200
        for project in (first, second):
            assert client.patch(f"/api/projects/{project['id']}/production-stages/world", json={"workflow_id": "shared-source"}).status_code == 200
        first_run = client.post("/api/runs", json={"workflow": workflow, "project_id": first["id"]}).json()["runId"]
        second_run = client.post("/api/runs", json={"workflow": workflow, "project_id": second["id"]}).json()["runId"]
        wait_for_success(client, first_run)
        wait_for_success(client, second_run)
        first_status = client.get(f"/api/projects/{first['id']}/production-status").json()
        second_status = client.get(f"/api/projects/{second['id']}/production-status").json()

    assert next(item for item in first_status if item["stage_id"] == "world")["latest_run_id"] == first_run
    assert next(item for item in second_status if item["stage_id"] == "world")["latest_run_id"] == second_run


def test_official_stage_workflows_compile_as_whitebox_prompt_chains(tmp_path) -> None:
    app = create_app(tmp_path / "official-stages.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflows = {
            item["id"]: item for item in client.get("/api/workflows").json()
        }
        for workflow_id in (
            "official-book-setup", "official-world-building", "official-character-design",
            "official-story-planning", "official-outline-planning",
            "official-post-chapter-update",
        ):
            workflow = workflows[workflow_id]
            validation = client.post("/api/workflows/validate", json=workflow)
            assert validation.status_code == 200
            assert validation.json()["valid"] is True
            assert [node["type"] for node in workflow["nodes"]] == [
                "workflow.input", "ai.prompt_call", "ai.prompt_call", "workflow.output",
            ]


def test_user_can_create_and_remove_project_private_workflow_component(tmp_path) -> None:
    app = create_app(tmp_path / "custom-component.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        created = client.post("/api/projects/demo-project/production-stages", json={
            "title": "我的拆书流程", "description": "项目私有流程",
            "create_blank_workflow": True,
        })
        body = created.json()
        workflow = body["workflow"]
        validation = client.post("/api/workflows/validate", json=workflow).json()
        canvas = client.get("/api/projects/demo-project/production-canvas").json()
        removed = client.delete(
            f"/api/projects/demo-project/production-stages/{body['stage']['id']}"
        )
        canvas_after = client.get("/api/projects/demo-project/production-canvas").json()

    assert created.status_code == 201
    assert body["stage"]["type"] == "workflow_component"
    assert body["stage"]["workflow_id"].startswith("project:demo-project:")
    assert [node["type"] for node in workflow["nodes"]] == ["workflow.input", "workflow.output"]
    assert validation["valid"] is True
    assert any(item["id"] == body["stage"]["id"] for item in canvas["stages"])
    assert removed.status_code == 204
    assert not any(item["id"] == body["stage"]["id"] for item in canvas_after["stages"])


def test_blank_workflow_endpoint_creates_input_output_body(tmp_path) -> None:
    app = create_app(tmp_path / "blank-workflow.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        response = client.post("/api/workflows/blank", json={"name": "Map Body 自定义"})
        workflow = response.json()
        validation = client.post("/api/workflows/validate", json=workflow).json()

    assert response.status_code == 201
    assert workflow["id"].startswith("user:")
    assert [node["type"] for node in workflow["nodes"]] == ["workflow.input", "workflow.output"]
    assert validation["valid"] is True


def test_standalone_blank_workflow_has_no_nodes(tmp_path) -> None:
    app = create_app(tmp_path / "empty-workflow.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        response = client.post("/api/workflows/blank", json={
            "name": "ComfyUI 空白工作流", "with_boundary_nodes": False,
        })

    assert response.status_code == 201
    assert response.json()["nodes"] == []
    assert response.json()["edges"] == []


def test_production_canvas_rejects_unknown_or_mismatched_exposed_ports(tmp_path) -> None:
    app = create_app(tmp_path / "component-ports.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        canvas = client.get("/api/projects/demo-project/production-canvas").json()
        canvas["edges"].append({"id": "bad", "source": "setup", "target": "world", "source_port": "missing", "target_port": "input"})
        response = client.put("/api/projects/demo-project/production-canvas", json=canvas)

    assert response.status_code == 422
    assert "暴露端口不存在" in response.text


def test_production_canvas_derives_boundary_port_names_from_workflow(tmp_path) -> None:
    app = create_app(tmp_path / "component-port-names.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflow = {
            "id": "named-boundary", "name": "命名边界", "revision": 1,
            "nodes": [
                {"id": "input", "type": "workflow.input", "position": {"x": 0, "y": 0}, "config": {"name": "原始小说", "default": ""}},
                {"id": "output", "type": "workflow.output", "position": {"x": 300, "y": 0}, "config": {"name": "拆书报告"}},
            ], "edges": [{"id": "edge", "source": "input", "target": "output", "source_port": "value", "target_port": "value"}],
        }
        client.put("/api/workflows/named-boundary", json=workflow)
        stage = client.post("/api/projects/demo-project/production-stages", json={"title": "命名组件", "workflow_id": "named-boundary"}).json()["stage"]
        canvas = client.get("/api/projects/demo-project/production-canvas").json()
        stage = next(item for item in canvas["stages"] if item["id"] == stage["id"])

    assert [port["name"] for port in stage["input_ports"]] == ["原始小说"]
    assert [port["name"] for port in stage["output_ports"]] == ["拆书报告"]


def test_production_run_composes_bound_component_workflows(tmp_path) -> None:
    import time

    app = create_app(tmp_path / "production-run.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        workflow = {
            "id": "component-chain", "name": "组件链", "revision": 1,
            "nodes": [
                {"id": "input", "type": "workflow.input", "position": {"x": 0, "y": 0}, "config": {"name": "input", "default": "上游任务"}},
                {"id": "output", "type": "workflow.output", "position": {"x": 300, "y": 0}, "config": {"name": "output"}},
            ], "edges": [{"id": "edge", "source": "input", "target": "output", "source_port": "value", "target_port": "value"}],
        }
        client.put("/api/workflows/component-chain", json=workflow)
        canvas = client.get("/api/projects/demo-project/production-canvas").json()
        for stage in canvas["stages"]:
            if stage["id"] in {"setup", "analysis"}:
                stage["workflow_id"] = "component-chain"
            else:
                stage["workflow_id"] = None
        canvas["edges"] = [{"id": "setup-analysis", "source": "setup", "target": "analysis", "source_port": "output", "target_port": "input"}]
        assert client.put("/api/projects/demo-project/production-canvas", json=canvas).status_code == 200
        preflight = client.post("/api/production-runs/preflight", json={"project_id": "demo-project", "chapter_number": 1}).json()
        response = client.post("/api/production-runs", json={"project_id": "demo-project", "chapter_number": 1})
        run_id = response.json()["runId"]
        for _ in range(100):
            run = client.get(f"/api/runs/{run_id}").json()
            if run["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)
        input_runs = [item for item in run["node_runs"] if item["node_id"].endswith("/input")]
        artifacts = [client.get(f"/api/artifacts/{item['output_artifact_id']}").json() for item in input_runs]
        statuses = client.get("/api/projects/demo-project/production-status").json()

    assert response.status_code == 202
    assert preflight["valid"] is True
    assert preflight["components"][0]["title"] == "新书立项"
    assert run["status"] == "succeeded"
    assert len(input_runs) == 2
    assert artifacts[0]["content"]["text"] == artifacts[1]["content"]["text"]
    setup_status = next(item for item in statuses if item["stage_id"] == "setup")
    assert setup_status["latest_run_id"] == run_id
    assert setup_status["progress_total"] == 2
    assert setup_status["progress_completed"] == 2


def test_production_preflight_requires_explicit_side_effect_permission(tmp_path) -> None:
    app = create_app(tmp_path / "production-side-effects.db", DeepSeekProvider(api_key="test"))
    with TestClient(app) as client:
        preflight = client.post("/api/production-runs/preflight", json={
            "project_id": "demo-project", "chapter_number": 1,
        })
        blocked = client.post("/api/production-runs", json={
            "project_id": "demo-project", "chapter_number": 1,
        })
        allowed = client.post("/api/production-runs/preflight", json={
            "project_id": "demo-project", "chapter_number": 1,
            "allow_side_effects": True,
        })

    assert preflight.status_code == 200
    assert preflight.json()["side_effects"] >= 1
    assert preflight.json()["valid"] is False
    assert blocked.status_code == 409
    assert allowed.json()["valid"] is True
