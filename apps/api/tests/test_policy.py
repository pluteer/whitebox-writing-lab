from whitebox.main import DEFAULT_WORKFLOW
from whitebox.models import ModelProfile, ProviderConnection, WorkflowDocument
from whitebox.policy import record_model_assignments


def profile(profile_id: str, connection_id: str, family: str) -> ModelProfile:
    return ModelProfile.model_validate({
        "id": profile_id, "name": profile_id, "connection_id": connection_id,
        "model": family + "-model", "model_family": family, "temperature": 0.5,
        "max_tokens": 1000, "thinking": False, "is_default": False, "version": 1,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    })


def connection(connection_id: str, provider: str, trust_group: str) -> ProviderConnection:
    return ProviderConnection.model_validate({
        "id": connection_id, "name": connection_id, "protocol": "openai-compatible",
        "base_url": f"https://{connection_id}.example.com", "provider_identity": provider,
        "trust_group": trust_group, "is_local": False, "trust_confirmed": True,
        "has_api_key": True, "key_hint": "...test",
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    })


def workflow_with_roles(assignments: dict[str, str]) -> WorkflowDocument:
    data = DEFAULT_WORKFLOW.model_dump()
    data["nodes"] = []
    data["edges"] = []
    for index, (role, profile_id) in enumerate(assignments.items()):
        node_type = {
            "writer": "writing.llm_draft",
            "reviewer": "writing.llm_review",
            "arbiter": "writing.llm_arbiter",
        }[role]
        data["nodes"].append({
            "id": role, "type": node_type, "position": {"x": index * 100, "y": 0},
            "config": {"profile_id": profile_id, "agent_role": role, "instruction": role},
        })
    return WorkflowDocument.model_validate(data)


def test_three_selected_models_are_recorded_without_judgment() -> None:
    profiles = {
        "writer-brain": profile("writer-brain", "writer-api", "family-a"),
        "reviewer-brain": profile("reviewer-brain", "reviewer-api", "family-b"),
        "arbiter-brain": profile("arbiter-brain", "arbiter-api", "family-c"),
    }
    connections = {
        "writer-api": connection("writer-api", "provider-a", "group-a"),
        "reviewer-api": connection("reviewer-api", "provider-b", "group-b"),
        "arbiter-api": connection("arbiter-api", "provider-c", "group-c"),
    }

    report = record_model_assignments(
        workflow_with_roles({"writer": "writer-brain", "reviewer": "reviewer-brain", "arbiter": "arbiter-brain"}),
        profiles, connections,
    )

    assert set(report["assignments"]) == {"writer", "reviewer", "arbiter"}
    assert report["assignments"]["reviewer"]["provider_identity"] == "provider-b"
    assert report["unassigned_roles"] == []


def test_same_trust_group_is_recorded_but_not_judged() -> None:
    profiles = {
        "writer-brain": profile("writer-brain", "api-a", "family-a"),
        "reviewer-brain": profile("reviewer-brain", "api-b", "family-b"),
    }
    connections = {
        "api-a": connection("api-a", "reseller-a", "same-upstream"),
        "api-b": connection("api-b", "reseller-b", "same-upstream"),
    }

    report = record_model_assignments(
        workflow_with_roles({"writer": "writer-brain", "reviewer": "reviewer-brain"}),
        profiles, connections,
    )

    assert report["assignments"]["writer"]["trust_group"] == "same-upstream"
    assert report["assignments"]["reviewer"]["trust_group"] == "same-upstream"
    assert "issues" not in report


def test_duplicate_role_keeps_first_assignment_without_blocking() -> None:
    profiles = {
        "brain-a": profile("brain-a", "api-a", "family-a"),
        "brain-b": profile("brain-b", "api-b", "family-b"),
    }
    connections = {
        "api-a": connection("api-a", "provider-a", "group-a"),
        "api-b": connection("api-b", "provider-b", "group-b"),
    }
    workflow = workflow_with_roles({"writer": "brain-a"})
    duplicate = workflow.nodes[0].model_copy(deep=True)
    duplicate.id = "writer-copy"
    duplicate.config["profile_id"] = "brain-b"
    workflow.nodes.append(duplicate)

    report = record_model_assignments(workflow, profiles, connections)

    assert report["assignments"]["writer"]["profile_id"] == "brain-a"
    assert "issues" not in report
