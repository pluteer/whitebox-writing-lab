from whitebox.skills import parse_skill_markdown, resolve_skill_parameters


def test_parse_standard_skill_markdown() -> None:
    metadata, instructions = parse_skill_markdown(
        "---\nname: continuity-check\ndescription: 检查设定连续性\nmetadata:\n  author: test\n---\n\n# 连续性\n逐项检查时间线。\n"
    )
    assert metadata["name"] == "continuity-check"
    assert metadata["metadata"]["author"] == "test"
    assert "逐项检查时间线" in instructions


def test_parse_skill_capabilities() -> None:
    metadata, _ = parse_skill_markdown(
        "---\nname: lore-reader\ndescription: 读取设定\nmetadata:\n  whitebox-capabilities:\n    - project.assets.read\n    - project.chapters.read\n---\n读取资料后分析。"
    )
    assert metadata["whitebox_capabilities"] == [
        "project.assets.read", "project.chapters.read"
    ]


def test_reject_unsupported_skill_capability() -> None:
    try:
        parse_skill_markdown(
            "---\nname: shell-user\ndescription: 危险\ncapabilities:\n  - shell.exec\n---\n运行命令。"
        )
        raise AssertionError("expected failure")
    except ValueError as exc:
        assert "不支持的能力" in str(exc)


def test_parse_and_resolve_skill_parameters() -> None:
    metadata, _ = parse_skill_markdown(
        "---\nname: style-control\ndescription: 控制文风\nmetadata:\n  whitebox-parameters:\n    scope:\n      type: string\n      required: true\n    strictness:\n      type: number\n      minimum: 0\n      maximum: 1\n      default: 0.8\n    include_quotes:\n      type: boolean\n      default: true\n    severity:\n      type: string\n      enum: [major, all]\n      default: all\n---\n按参数执行。"
    )
    resolved = resolve_skill_parameters(
        metadata["whitebox_parameters"], {"scope": "人物"}
    )
    assert resolved == {
        "scope": "人物", "strictness": 0.8,
        "include_quotes": True, "severity": "all",
    }
    try:
        resolve_skill_parameters(metadata["whitebox_parameters"], {"scope": "人物", "strictness": 2})
        raise AssertionError("expected range failure")
    except ValueError as exc:
        assert "大于最大值" in str(exc)


def test_skill_requires_frontmatter_and_instructions() -> None:
    for source in ["# no frontmatter", "---\nname: Bad Name\ndescription: x\n---\nbody", "---\nname: ok\ndescription: x\n---\n"]:
        try:
            parse_skill_markdown(source)
            raise AssertionError("expected failure")
        except ValueError:
            pass
