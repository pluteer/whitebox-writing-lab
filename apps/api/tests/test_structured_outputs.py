import pytest
from pydantic import ValidationError

from whitebox.engine import WorkflowEngine
from whitebox.models import BookAnalysisReport, DecisionSet, ReviewSet, Revision


def test_review_set_requires_unique_evidence_ids() -> None:
    finding = {
        "id": "F1", "severity": "major", "category": "逻辑",
        "quote": "原文", "evidence": "证据", "recommendation": "建议",
    }
    with pytest.raises(ValidationError, match="ID 必须唯一"):
        ReviewSet.model_validate({"findings": [finding, finding], "summary": "总结"})


def test_book_analysis_report_has_stable_categories_and_evidence_fields() -> None:
    report = BookAnalysisReport.model_validate({"summary": "总结", "characters": [{"title": "主角", "evidence": "第一章"}], "risks": []})
    assert report.characters[0]["evidence"] == "第一章"
    assert report.risks == []


def test_decision_set_must_cover_every_finding() -> None:
    review = ReviewSet.model_validate({
        "findings": [
            {"id": "F1", "severity": "major", "category": "逻辑", "quote": "A", "evidence": "E", "recommendation": "R"},
            {"id": "F2", "severity": "minor", "category": "文风", "quote": "B", "evidence": "E", "recommendation": "R"},
        ],
        "summary": "两项意见",
    })
    decisions = DecisionSet.model_validate({
        "decisions": [{
            "finding_id": "F1", "verdict": "accept", "reason": "合理",
            "revision_instruction": "修改 A",
        }],
        "summary": "只裁决了一项",
    })
    with pytest.raises(ValueError, match="引用不完整"):
        decisions.validate_references(review)


def test_json_extraction_accepts_fenced_object_but_rejects_arrays() -> None:
    assert WorkflowEngine._extract_json_object("```json\n{\"summary\":\"ok\"}\n```") == {"summary": "ok"}
    with pytest.raises(ValueError, match="JSON 对象"):
        WorkflowEngine._extract_json_object("[]")


def test_revision_must_follow_accepted_and_rejected_decisions() -> None:
    decisions = DecisionSet.model_validate({
        "decisions": [
            {"finding_id": "F1", "verdict": "accept", "reason": "改", "revision_instruction": "改 A"},
            {"finding_id": "F2", "verdict": "reject", "reason": "不改", "revision_instruction": ""},
        ],
        "summary": "裁决",
    })
    valid = Revision.model_validate({
        "text": "A 已修改，B 保持。",
        "changes": [{
            "finding_id": "F1", "description": "修改 A",
            "before_quote": "旧 A", "after_quote": "A 已修改",
        }],
        "summary": "修订",
    })
    assert valid.validate_against("旧 A，B 保持。", decisions) == []

    invalid = Revision.model_validate({
        **valid.model_dump(),
        "changes": [
            *valid.model_dump()["changes"],
            {"finding_id": "F2", "description": "越权", "before_quote": "B", "after_quote": "B 保持"},
        ],
    })
    with pytest.raises((ValueError, ValidationError), match="越权"):
        invalid.validate_against("旧 A，B 保持。", decisions)

    bad_quote = Revision.model_validate({
        **valid.model_dump(),
        "changes": [{
            "finding_id": "F1", "description": "修改 A",
            "before_quote": "模型编造的旧文", "after_quote": "模型编造的新文",
        }],
    })
    assert bad_quote.validate_against("旧 A，B 保持。", decisions) == [
        "修订 F1 的原文引文不存在", "修订 F1 的新文引文不存在",
    ]


def test_custom_prompt_template_renders_known_variables_and_rejects_unknown() -> None:
    rendered = WorkflowEngine._render_prompt_template(
        "{{project.title}} 第 {{ chapter.number }} 章：{{input.text}}",
        {
            "project.title": "雨夜", "chapter.number": "3",
            "input.text": "正文", "input.json": "{}",
        },
    )
    assert rendered == "雨夜 第 3 章：正文"
    with pytest.raises(ValueError, match="未知变量"):
        WorkflowEngine._render_prompt_template(
            "{{secrets.api_key}}", {"input.text": "", "input.json": "{}"}
        )
