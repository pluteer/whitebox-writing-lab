from __future__ import annotations

import re

import yaml


SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SUPPORTED_CAPABILITIES = {"project.assets.read", "project.chapters.read"}
SUPPORTED_PARAMETER_TYPES = {"string", "number", "integer", "boolean"}
SENSITIVE_PARAMETER_NAMES = {
    "apikey", "authorization", "secret", "token", "baseurl", "password", "bearer",
}


def parse_skill_markdown(source: str) -> tuple[dict, str]:
    normalized = source.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError("SKILL.md 必须以 YAML frontmatter 开头")
    end = normalized.find("\n---\n", 4)
    if end == -1:
        raise ValueError("SKILL.md frontmatter 未闭合")
    try:
        metadata = yaml.safe_load(normalized[4:end]) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"SKILL.md frontmatter 无效: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter 必须是对象")
    name = str(metadata.get("name", ""))
    description = str(metadata.get("description", "")).strip()
    if not SKILL_NAME.fullmatch(name):
        raise ValueError("Skill name 必须是小写连字符格式")
    if not description:
        raise ValueError("Skill description 不能为空")
    instructions = normalized[end + 5:].strip()
    if not instructions:
        raise ValueError("Skill 指令正文不能为空")
    skill_metadata = metadata.get("metadata") or {}
    if skill_metadata and not isinstance(skill_metadata, dict):
        raise ValueError("Skill metadata 必须是对象")
    capabilities = metadata.get("capabilities", skill_metadata.get("whitebox-capabilities", []))
    if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
        raise ValueError("Skill capabilities 必须是字符串数组")
    unsupported = sorted(set(capabilities) - SUPPORTED_CAPABILITIES)
    if unsupported:
        raise ValueError(f"Skill 声明了不支持的能力: {unsupported}")
    metadata["whitebox_capabilities"] = list(dict.fromkeys(capabilities))
    parameters = metadata.get("parameters", skill_metadata.get("whitebox-parameters", {}))
    if not isinstance(parameters, dict):
        raise ValueError("Skill parameters 必须是对象")
    normalized_parameters = {}
    for key, definition in parameters.items():
        if not re.fullmatch(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$", str(key)):
            raise ValueError(f"Skill 参数名无效: {key}")
        normalized_key = "".join(character for character in str(key).lower() if character.isalnum())
        if normalized_key in SENSITIVE_PARAMETER_NAMES:
            raise ValueError(f"Skill 参数禁止用于敏感信息: {key}")
        if not isinstance(definition, dict):
            raise ValueError(f"Skill 参数 {key} 定义必须是对象")
        parameter_type = definition.get("type")
        if parameter_type not in SUPPORTED_PARAMETER_TYPES:
            raise ValueError(f"Skill 参数 {key} 类型不支持: {parameter_type}")
        enum = definition.get("enum")
        if enum is not None and (
            not isinstance(enum, list) or not enum or any(
                not isinstance(item, (str, int, float, bool)) for item in enum
            )
        ):
            raise ValueError(f"Skill 参数 {key} enum 无效")
        normalized = {
            "type": parameter_type,
            "title": str(definition.get("title", key)),
            "description": str(definition.get("description", "")),
            "required": bool(definition.get("required", False)),
        }
        for field in ("default", "enum", "minimum", "maximum"):
            if field in definition:
                normalized[field] = definition[field]
        normalized_parameters[str(key)] = normalized
    metadata["whitebox_parameters"] = normalized_parameters
    return metadata, instructions


def resolve_skill_parameters(schema: dict, provided: dict) -> dict:
    if not isinstance(provided, dict):
        raise ValueError("Skill parameters 必须是对象")
    unknown = set(provided) - set(schema)
    if unknown:
        raise ValueError(f"Skill 包含未知参数: {sorted(unknown)}")
    resolved = {}
    for name, definition in schema.items():
        if name in provided:
            value = provided[name]
        elif "default" in definition:
            value = definition["default"]
        elif definition.get("required"):
            raise ValueError(f"Skill 缺少必填参数: {name}")
        else:
            continue
        expected = definition["type"]
        valid = (
            (expected == "string" and isinstance(value, str))
            or (expected == "boolean" and isinstance(value, bool))
            or (expected == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
        )
        if not valid:
            raise ValueError(f"Skill 参数 {name} 类型应为 {expected}")
        if "enum" in definition and value not in definition["enum"]:
            raise ValueError(f"Skill 参数 {name} 不在允许值中")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in definition and value < definition["minimum"]:
                raise ValueError(f"Skill 参数 {name} 小于最小值")
            if "maximum" in definition and value > definition["maximum"]:
                raise ValueError(f"Skill 参数 {name} 大于最大值")
        resolved[name] = value
    return resolved
