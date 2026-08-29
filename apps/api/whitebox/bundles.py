from __future__ import annotations

import hashlib
import json

from .models import SkillBundle, WorkflowTemplateBundle


FORBIDDEN_KEYS = {
    "apikey", "authorization", "secret", "token", "baseurl",
    "password", "bearer",
}


def canonical_bundle_payload(bundle: SkillBundle) -> dict:
    payload = bundle.model_dump(mode="json", exclude={"content_hash"})
    payload["skills"] = sorted(payload["skills"], key=lambda item: item["name"])
    payload["node_templates"] = sorted(payload["node_templates"], key=lambda item: item["name"])
    for template in payload["node_templates"]:
        template["node_types"] = sorted(template["node_types"])
        template["skills"] = sorted(template["skills"], key=lambda item: item["skill_name"])
    return payload


def bundle_hash(bundle: SkillBundle) -> str:
    encoded = json.dumps(
        canonical_bundle_payload(bundle), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _assert_payload_has_no_secrets(payload: dict, label: str) -> None:
    def visit(value, path: str = "bundle"):
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = "".join(character for character in key.lower() if character.isalnum())
                if normalized_key in FORBIDDEN_KEYS:
                    raise ValueError(f"{label} 禁止包含敏感字段: {path}.{key}")
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
    visit(payload, label)


def assert_bundle_has_no_secrets(bundle: SkillBundle) -> None:
    _assert_payload_has_no_secrets(canonical_bundle_payload(bundle), "Bundle")


def canonical_workflow_template_payload(bundle: WorkflowTemplateBundle) -> dict:
    payload = bundle.model_dump(mode="json", exclude={"content_hash"})
    payload["nodes"] = sorted(payload["nodes"], key=lambda item: item["id"])
    for node in payload["nodes"]:
        if isinstance(node["config"].get("skill_bindings"), list):
            node["config"]["skill_bindings"] = sorted(
                node["config"]["skill_bindings"],
                key=lambda item: item.get("skill_name", ""),
            )
    payload["edges"] = sorted(payload["edges"], key=lambda item: item["id"])
    payload["model_slots"] = sorted(payload["model_slots"], key=lambda item: item["id"])
    payload["groups"] = sorted(payload["groups"], key=lambda item: item["id"])
    payload["notes"] = sorted(payload["notes"], key=lambda item: item["id"])
    payload["frames"] = sorted(payload["frames"], key=lambda item: item["id"])
    payload["required_skills"] = sorted(set(payload["required_skills"]))
    return payload


def workflow_template_hash(bundle: WorkflowTemplateBundle) -> str:
    return hashlib.sha256(json.dumps(
        canonical_workflow_template_payload(bundle), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def assert_workflow_template_portable(bundle: WorkflowTemplateBundle) -> None:
    payload = canonical_workflow_template_payload(bundle)
    _assert_payload_has_no_secrets(payload, "Workflow Template")
    forbidden = {
        "connectionid", "model", "apikey", "authorization", "baseurl",
        "keyhint", "connectionsnapshot", "modelsnapshot", "profilesnapshot",
        "skillsnapshots", "profileid",
    }
    for node in payload["nodes"]:
        config = node["config"]
        for key in config:
            normalized = "".join(character for character in key.lower() if character.isalnum())
            if normalized in forbidden:
                raise ValueError(f"Workflow Template 节点包含本机绑定字段: {node['id']}.{key}")
