"""Versioned prompt assets for the built-in writing workflows.

Prompt text lives outside the HTTP application module so it can be reviewed,
tested, and eventually exposed as a user-editable prompt pack.
"""

OFFICIAL_PROMPT_PACK_ID = "whitebox.official.writing"
OFFICIAL_PROMPT_PACK_REVISION = 1

CHAPTER_WRITER_SYSTEM = (
    "你是长篇网络小说写手。你只根据输入的章节任务写正文，不替作者改设定，不提前消费后续大纲。"
    "先在脑中完成目标、阻力、选择、代价和章尾钩子的检查，再直接输出小说正文。禁止输出分析、提纲、解释或标题。"
)
CHAPTER_WRITER_INSTRUCTION = (
    "写成约 600 字的悬疑小说开篇。必须保留任务中的全部事实；用具体行动、对话和感官细节承载信息；"
    "本章聚焦一个主要冲突；配角拥有自己的诉求和反制；结尾留下一个具体、可追踪的悬念。"
)
CHAPTER_REVIEW_INSTRUCTION = (
    "重点检查连续性、人物动机、信息边界、情节因果、场景推进、伏笔状态、文风和章尾钩子。"
    "每条意见必须引用原文，说明证据、影响和可执行修复；没有证据的问题不要提出。"
)
CHAPTER_ARBITER_INSTRUCTION = (
    "以作品设定、当前章节目标和可执行性为准。逐条判断意见是否有证据、是否影响本章目标、"
    "是否会破坏人物或伏笔。拒绝空泛建议；接受或修改的意见必须给出局部、可执行的修订指令。"
)
CHAPTER_REVISER_INSTRUCTION = (
    "只执行裁决为 accept 或 modify 的意见。保持未被裁决涉及的段落、事实、人物动机和叙事视角不变；"
    "不得借修订开新支线、提前回收伏笔或整章重写。每一项改动都必须能对应一个 finding_id。"
)

OFFICIAL_PROMPTS = {
    "chapter.writer.system": CHAPTER_WRITER_SYSTEM,
    "chapter.writer.instruction": CHAPTER_WRITER_INSTRUCTION,
    "chapter.reviewer.instruction": CHAPTER_REVIEW_INSTRUCTION,
    "chapter.arbiter.instruction": CHAPTER_ARBITER_INSTRUCTION,
    "chapter.reviser.instruction": CHAPTER_REVISER_INSTRUCTION,
}

# Stable identities for the book-level three-step prompt chains. The actual
# stage wording remains intentionally configurable in the workflow document.
OFFICIAL_STAGE_PROMPT_IDS = {
    "book_setup": ("book.setup.generate", "book.setup.refine"),
    "world_building": ("world.generate", "world.refine"),
    "character_design": ("characters.generate", "characters.refine"),
    "story_planning": ("story.generate", "story.refine"),
    "outline_planning": ("outline.generate", "outline.refine"),
    "post_chapter_update": ("state.generate", "state.refine"),
}

OFFICIAL_STAGE_PROMPT_TEXT = {
    "book.setup.generate": "根据用户提供的创作简报生成书级立项案，覆盖定位、读者承诺、核心冲突、叙事策略、边界和待确认项。",
    "book.setup.refine": "校验立项案的具体性、一致性和作者确认边界；保留明确决定，把不确定内容列为待确认。",
    "world.generate": "生成会影响剧情的世界规则，并为每条规则写明剧情用途、限制、代价、例外和可验证表现。",
    "world.refine": "检查世界规则之间的冲突、万能设定和无法落地的空泛描述，输出冲突与待作者决定项。",
    "characters.generate": "生成主要角色档案，覆盖目标、恐惧、误区、底线、秘密、关系张力、能力限制和语言特征。",
    "characters.refine": "检查角色同质化、动机空泛、能力无代价和关系跳跃，整理为可通过行动观察的角色设定。",
    "story.generate": "用因果、选择和代价组织主线，输出核心问题、阶段目标、转折因果、失败代价和结局承诺。",
    "story.refine": "检查因果断裂、重复升级、被动主角和结局承诺缺失，输出风险和待裁决项。",
    "outline.generate": "将故事规划拆成卷目标和近期章节任务，每章明确目标、阻力、转折、状态变化、伏笔和章尾钩子。",
    "outline.refine": "检查章节功能重复、信息提前泄露和缺乏状态推进，保留可直接执行的章节任务。",
    "state.generate": "从已批准章节提取人物、时间线、地点、伏笔、秘密和叙事债务的明确状态变化，并附证据。",
    "state.refine": "删除无证据推断，合并重复项，区分事实、候选变化和人工确认边界，不声称已经写入资产。",
}


def official_prompt_manifest() -> dict:
    """Return a serializable manifest without exposing mutable application state."""
    return {
        "id": OFFICIAL_PROMPT_PACK_ID,
        "revision": OFFICIAL_PROMPT_PACK_REVISION,
        "prompts": sorted((*OFFICIAL_PROMPTS, *(prompt_id for pair in OFFICIAL_STAGE_PROMPT_IDS.values() for prompt_id in pair))),
        "editable_prompts": sorted(OFFICIAL_PROMPTS),
    }


def official_prompt_details() -> dict[str, dict[str, str]]:
    details = {
        prompt_id: {"id": prompt_id, "revision": str(OFFICIAL_PROMPT_PACK_REVISION), "content": content}
        for prompt_id, content in OFFICIAL_PROMPTS.items()
    }
    details.update({
        prompt_id: {"id": prompt_id, "revision": str(OFFICIAL_PROMPT_PACK_REVISION), "content": content}
        for prompt_id, content in OFFICIAL_STAGE_PROMPT_TEXT.items()
    })
    return details
