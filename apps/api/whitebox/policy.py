from __future__ import annotations

from .models import ModelProfile, ProviderConnection, WorkflowDocument


REQUIRED_AGENT_ROLES = ("writer", "reviewer", "arbiter")
NODE_ROLES = {
    "writing.deepseek_draft": "writer",
    "writing.llm_draft": "writer",
    "writing.llm_review": "reviewer",
    "writing.llm_arbiter": "arbiter",
}


def record_model_assignments(
    workflow: WorkflowDocument,
    profiles: dict[str, ModelProfile],
    connections: dict[str, ProviderConnection],
) -> dict:
    assignments: dict[str, dict] = {}
    for node in workflow.nodes:
        role = NODE_ROLES.get(node.type)
        profile_id = node.config.get("profile_id")
        if role not in REQUIRED_AGENT_ROLES:
            continue
        if role in assignments:
            continue
        profile = profiles.get(str(profile_id)) if profile_id else None
        connection_id = str(node.config.get("connection_id") or (profile.connection_id if profile else ""))
        model = str(node.config.get("model") or (profile.model if profile else ""))
        connection = connections.get(connection_id)
        if not connection or not model:
            continue
        assignments[role] = {
            "node_id": node.id,
            "profile_id": profile.id if profile else None,
            "profile_name": profile.name if profile else None,
            "connection_id": connection.id,
            "connection_name": connection.name,
            "provider_identity": connection.provider_identity,
            "trust_group": connection.trust_group,
            "model": model,
            "model_family": str(
                node.config.get("model_family")
                or (profile.model_family if profile else "unknown")
            ),
        }

    return {
        "assignments": assignments,
        "unassigned_roles": [role for role in REQUIRED_AGENT_ROLES if role not in assignments],
    }
