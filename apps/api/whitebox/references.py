from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from uuid import uuid4

from .models import ReferenceBookRecord, WorkflowDocument


def normalize_reference_text(value: str) -> str:
    value = value.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in value:
        raise ValueError("拆书素材不能包含 NUL 字符")
    if not value.strip():
        raise ValueError("拆书素材不能为空")
    return value


def split_reference_text(value: str, chunk_size: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(value):
        end = min(start + chunk_size, len(value))
        if end < len(value):
            window_start = max(start + chunk_size // 2, end - 3000)
            matches = list(re.finditer(r"\n(?=#)|\n\n|\n|[。！？!?]", value[window_start:end]))
            if matches:
                end = window_start + matches[-1].end()
        chunks.append(value[start:end])
        start = end
    return chunks


def make_reference_book(project_id: str, request, workflow_id: str, content: str, book_id: str | None = None) -> ReferenceBookRecord:
    return ReferenceBookRecord(
        id=book_id or f"book-{uuid4()}", project_id=project_id, original_name=request.filename,
        byte_size=len(content.encode()), content_hash=hashlib.sha256(content.encode()).hexdigest(),
        normalized_content=content, chunk_size=request.chunk_size,
        chunk_count=len(split_reference_text(content, request.chunk_size)),
        workflow_id=workflow_id, created_at=datetime.now(UTC),
    )


def build_reference_workflow(book: ReferenceBookRecord, title: str, connection_id: str, model: str, temperature: float) -> WorkflowDocument:
    body_id = f"reference-body:{book.id}"
    body = WorkflowDocument.model_validate({
        "id": body_id, "name": f"拆书分块分析 / {title}", "revision": 1,
        "nodes": [
            {"id":"input","type":"workflow.input","position":{"x":80,"y":160},"config":{"name":"chunk","default":""}},
            {"id":"analyze","type":"ai.prompt_call","position":{"x":430,"y":160},"config":{"connection_id":connection_id,"model":model,"temperature":temperature,"system_prompt":"你是小说拆书分析员。只分析给定原文分块，输出情节推进、角色行动、冲突转折、节奏钩子、伏笔和可复用写法，并引用短证据。","user_prompt":"分析以下原文分块：\\n\\n{{input.text}}"}},
            {"id":"output","type":"workflow.output","position":{"x":780,"y":160},"config":{"name":"analysis"}},
        ],
        "edges":[
            {"id":"input-analyze","source":"input","target":"analyze","source_port":"value","target_port":"input"},
            {"id":"analyze-output","source":"analyze","target":"output","source_port":"text","target_port":"value"},
        ],
    })
    return WorkflowDocument.model_validate({
        "id": f"reference-analysis:{book.id}", "name": f"拆书 / {title}", "revision": 1,
        "nodes":[
            {"id":"book","type":"reference.book_source","position":{"x":80,"y":220},"config":{"reference_book_id":book.id,"content_hash":book.content_hash}},
            {"id":"split","type":"flow.split","position":{"x":430,"y":220},"config":{"mode":"fixed","chunk_size":book.chunk_size}},
            {"id":"map","type":"flow.map","position":{"x":780,"y":220},"config":{"body_workflow_id":body_id,"concurrency":2}},
            {"id":"join","type":"flow.join","position":{"x":1130,"y":220},"config":{"separator":"\\n\\n---\\n\\n"}},
             {"id":"report","type":"ai.prompt_call","position":{"x":1480,"y":220},"config":{"connection_id":connection_id,"model":model,"temperature":0.2,"system_prompt":"你是资深拆书编辑。根据分块分析生成结构化全书拆解报告，区分事实与判断，并为结论提供短证据。只输出 JSON。字段：summary、positioning、structure、characters、conflicts、hooks、foreshadowing、style、techniques、risks；除 summary/positioning 外各字段都是对象数组。","user_prompt":"综合以下按原文顺序排列的分块分析，输出结构化报告：\\n\\n{{input.text}}"}},
            {"id":"output","type":"workflow.output","position":{"x":1830,"y":220},"config":{"name":"book_report"}},
        ],
        "edges":[
            {"id":"book-split","source":"book","target":"split","source_port":"text","target_port":"text"},
            {"id":"split-map","source":"split","target":"map","source_port":"items","target_port":"items"},
            {"id":"map-join","source":"map","target":"join","source_port":"results","target_port":"items"},
            {"id":"join-report","source":"join","target":"report","source_port":"value","target_port":"input"},
            {"id":"report-output","source":"report","target":"output","source_port":"text","target_port":"value"},
        ],
    })
