from __future__ import annotations

import json
import sqlite3
import threading
import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    Artifact,
    Event,
    ExecutionGraph,
    NodeAttempt,
    NodeRun,
    ModelProfile,
    ModelProfileCreate,
    ProviderConnection,
    ProviderConnectionCreate,
    ProviderModel,
    ProviderModelCreate,
    ApprovalRecord,
    Project,
    ProjectCreate,
    AssetVersion,
    Skill,
    SkillVersion,
    NodeBindingTemplate,
    NodeBindingTemplateCreate,
    SubflowDefinition,
    SubflowCreate,
    ProductionCanvas,
    ProviderCall,
    ProviderUsage,
    Run,
    WorkflowDocument,
    WorkflowVersion,
    ReferenceBook, ReferenceBookRecord,
)


MAX_PROVIDER_PAYLOAD_BYTES = 8 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA synchronous = NORMAL")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_versions (
                    workflow_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    document TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    PRIMARY KEY(workflow_id, revision)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    graph_hash TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS node_runs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    node_id TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    input_artifact_ids TEXT NOT NULL DEFAULT '[]',
                    output_artifact_id TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    error TEXT,
                    input_snapshot TEXT,
                    UNIQUE(run_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    node_run_id TEXT NOT NULL REFERENCES node_runs(id),
                    schema_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    parent_artifact_ids TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    node_run_id TEXT,
                    type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS node_attempts (
                    id TEXT PRIMARY KEY,
                    node_run_id TEXT NOT NULL REFERENCES node_runs(id),
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    input_artifact_ids TEXT NOT NULL,
                    output_artifact_id TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error TEXT,
                    cached_from_artifact_id TEXT,
                    UNIQUE(node_run_id, attempt)
                );
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_calls (
                    id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL REFERENCES node_attempts(id),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request_id TEXT,
                    request_payload TEXT NOT NULL,
                    response_payload TEXT,
                    usage TEXT,
                    finish_reason TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS model_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    temperature REAL NOT NULL,
                    max_tokens INTEGER NOT NULL,
                    thinking INTEGER NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_connections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    provider_identity TEXT NOT NULL,
                    trust_group TEXT NOT NULL,
                    is_local INTEGER NOT NULL,
                    trust_confirmed INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_models (
                    connection_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    family TEXT NOT NULL,
                    reasoning INTEGER NOT NULL DEFAULT 0,
                    tool_call INTEGER NOT NULL DEFAULT 0,
                    context_window INTEGER,
                    max_output INTEGER,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(connection_id, model_id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    node_run_id TEXT NOT NULL REFERENCES node_runs(id),
                    status TEXT NOT NULL,
                    artifact_ids TEXT NOT NULL,
                    actor TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    UNIQUE(node_run_id)
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    current_chapter INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS asset_versions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    relative_path TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    previous_hash TEXT,
                    content TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT NOT NULL,
                    source_artifact_id TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, relative_path, version)
                );
                CREATE TABLE IF NOT EXISTS state_patch_applications (
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    artifact_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    note TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, artifact_id)
                );
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    current_version_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_versions (
                    id TEXT PRIMARY KEY,
                    skill_id TEXT NOT NULL REFERENCES skills(id),
                    version INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(skill_id, version)
                );
                CREATE TABLE IF NOT EXISTS node_binding_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    node_types TEXT NOT NULL,
                    skills TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    nodes TEXT NOT NULL,
                    edges TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS production_canvases (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id),
                    document TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reference_books (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    original_name TEXT NOT NULL, byte_size INTEGER NOT NULL,
                    content_hash TEXT NOT NULL, normalized_content TEXT NOT NULL,
                    chunk_size INTEGER NOT NULL, chunk_count INTEGER NOT NULL,
                    workflow_id TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prompt_overrides (
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    prompt_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, prompt_id)
                );
                CREATE TABLE IF NOT EXISTS prompt_override_versions (
                    project_id TEXT NOT NULL REFERENCES projects(id), prompt_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(project_id, prompt_id, revision)
                );
                CREATE INDEX IF NOT EXISTS idx_events_run_sequence ON events(run_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_attempts_node_run ON node_attempts(node_run_id, attempt);
                CREATE INDEX IF NOT EXISTS idx_provider_calls_attempt ON provider_calls(attempt_id);
                """
            )
            db.execute("PRAGMA journal_mode = WAL")
            node_run_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(node_runs)")
            }
            if "input_snapshot" not in node_run_columns:
                db.execute("ALTER TABLE node_runs ADD COLUMN input_snapshot TEXT")
            profile_columns = {row["name"] for row in db.execute("PRAGMA table_info(model_profiles)")}
            if "connection_id" not in profile_columns:
                db.execute("ALTER TABLE model_profiles ADD COLUMN connection_id TEXT")
            if "model_family" not in profile_columns:
                db.execute("ALTER TABLE model_profiles ADD COLUMN model_family TEXT")
            skill_version_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(skill_versions)")
            }
            if "capabilities" not in skill_version_columns:
                db.execute("ALTER TABLE skill_versions ADD COLUMN capabilities TEXT NOT NULL DEFAULT '[]'")
            if "parameters_schema" not in skill_version_columns:
                db.execute("ALTER TABLE skill_versions ADD COLUMN parameters_schema TEXT NOT NULL DEFAULT '{}'")

    def get_prompt_override(self, project_id: str, prompt_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM prompt_overrides WHERE project_id=? AND prompt_id=?",
                (project_id, prompt_id),
            ).fetchone()
        return dict(row) if row else None

    def save_prompt_override(self, project_id: str, prompt_id: str, content: str, expected_revision: int | None = None) -> dict[str, Any]:
        now = utc_now()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT revision FROM prompt_overrides WHERE project_id=? AND prompt_id=?",
                (project_id, prompt_id),
            ).fetchone()
            current = int(row["revision"]) if row else 0
            if expected_revision is not None and expected_revision != current:
                raise ValueError(f"Prompt 覆盖版本冲突，当前版本为 {current}")
            revision = current + 1
            db.execute(
                "INSERT INTO prompt_overrides VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(project_id,prompt_id) DO UPDATE SET revision=excluded.revision, content=excluded.content, content_hash=excluded.content_hash, updated_at=excluded.updated_at",
                (project_id, prompt_id, revision, content, content_hash, now, now),
            )
            db.execute(
                "INSERT INTO prompt_override_versions VALUES(?,?,?,?,?,?)",
                (project_id, prompt_id, revision, content, content_hash, now),
            )
        return self.get_prompt_override(project_id, prompt_id)

    def list_prompt_override_versions(self, project_id: str, prompt_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM prompt_override_versions WHERE project_id=? AND prompt_id=? ORDER BY revision DESC", (project_id, prompt_id)).fetchall()
        return [dict(row) for row in rows]

    def get_prompt_override_version(self, project_id: str, prompt_id: str, revision: int) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM prompt_override_versions WHERE project_id=? AND prompt_id=? AND revision=?", (project_id, prompt_id, revision)).fetchone()
        return dict(row) if row else None

    def delete_prompt_override(self, project_id: str, prompt_id: str, expected_revision: int | None = None) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT revision FROM prompt_overrides WHERE project_id=? AND prompt_id=?", (project_id, prompt_id)).fetchone()
            if not row:
                return False
            if expected_revision is not None and int(row["revision"]) != expected_revision:
                raise ValueError(f"Prompt 覆盖版本冲突，当前版本为 {row['revision']}")
            db.execute("DELETE FROM prompt_overrides WHERE project_id=? AND prompt_id=?", (project_id, prompt_id))
        return True

    def ensure_demo_project(self) -> None:
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO projects VALUES('demo-project','示例小说','demo',1,?,?)",
                (now, now),
            )

    def list_projects(self) -> list[Project]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [self._project_from_row(row) for row in rows]

    def get_project(self, project_id: str) -> Project | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return self._project_from_row(row) if row else None

    def create_project(self, project_id: str, project: ProjectCreate) -> Project:
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO projects VALUES(?,?,?,1,?,?)",
                (project_id, project.title, project.slug, now, now),
            )
        return self.get_project(project_id)

    def get_production_canvas(self, project_id: str) -> ProductionCanvas | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT document FROM production_canvases WHERE project_id=?", (project_id,)
            ).fetchone()
        return ProductionCanvas.model_validate_json(row["document"]) if row else None

    def save_production_canvas(self, canvas: ProductionCanvas) -> ProductionCanvas:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO production_canvases VALUES(?,?,?) "
                "ON CONFLICT(project_id) DO UPDATE SET document=excluded.document,updated_at=excluded.updated_at",
                (canvas.project_id, canvas.model_dump_json(), utc_now()),
            )
        return canvas

    def save_production_canvas_checked(
        self, canvas: ProductionCanvas, expected_revision: int
    ) -> ProductionCanvas:
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT document FROM production_canvases WHERE project_id=?",
                (canvas.project_id,),
            ).fetchone()
            current = ProductionCanvas.model_validate_json(row["document"]) if row else None
            current_revision = current.revision if current else 0
            if current_revision != expected_revision:
                raise ValueError(f"生产画布版本冲突，当前版本为 {current_revision}")
            saved = canvas.model_copy(update={"revision": current_revision + 1})
            db.execute(
                "INSERT INTO production_canvases VALUES(?,?,?) "
                "ON CONFLICT(project_id) DO UPDATE SET document=excluded.document,updated_at=excluded.updated_at",
                (saved.project_id, saved.model_dump_json(), utc_now()),
            )
        return saved

    def save_reference_book(self, book: ReferenceBookRecord) -> ReferenceBookRecord:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO reference_books VALUES(?,?,?,?,?,?,?,?,?,?)",
                (book.id, book.project_id, book.original_name, book.byte_size,
                 book.content_hash, book.normalized_content, book.chunk_size,
                 book.chunk_count, book.workflow_id, book.created_at.isoformat()),
            )
        return book

    def get_reference_book(self, book_id: str) -> ReferenceBookRecord | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM reference_books WHERE id=?", (book_id,)).fetchone()
        return ReferenceBookRecord.model_validate(dict(row)) if row else None

    def list_reference_books(self, project_id: str) -> list[ReferenceBook]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM reference_books WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [ReferenceBook.model_validate({key: value for key, value in dict(row).items() if key != "normalized_content"}) for row in rows]

    def get_reference_book_by_hash(self, project_id: str, content_hash: str, chunk_size: int) -> ReferenceBookRecord | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM reference_books WHERE project_id=? AND content_hash=? AND chunk_size=? ORDER BY created_at DESC LIMIT 1",
                (project_id, content_hash, chunk_size),
            ).fetchone()
        return ReferenceBookRecord.model_validate(dict(row)) if row else None


    def advance_project_chapter(self, project_id: str, completed_chapter: int) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE projects SET current_chapter=MAX(current_chapter, ?),updated_at=? WHERE id=?",
                (completed_chapter + 1, utc_now(), project_id),
            )

    def create_asset_version(
        self,
        version_id: str,
        project_id: str,
        relative_path: str,
        content_hash: str,
        previous_hash: str | None,
        content: str,
        actor: str,
        note: str,
        source_artifact_id: str | None = None,
    ) -> AssetVersion:
        with self._lock, self._connect() as db:
            next_version = db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM asset_versions "
                "WHERE project_id=? AND relative_path=?",
                (project_id, relative_path),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO asset_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    version_id, project_id, relative_path, next_version, content_hash,
                    previous_hash, content, actor, note, source_artifact_id, utc_now(),
                ),
            )
        return self.get_asset_version(version_id)

    def get_asset_version(self, version_id: str) -> AssetVersion | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM asset_versions WHERE id=?", (version_id,)).fetchone()
        return self._asset_version_from_row(row) if row else None

    def list_asset_versions(self, project_id: str, relative_path: str) -> list[AssetVersion]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM asset_versions WHERE project_id=? AND relative_path=? "
                "ORDER BY version DESC",
                (project_id, relative_path),
            ).fetchall()
        return [self._asset_version_from_row(row) for row in rows]

    def state_patch_was_applied(self, project_id: str, source_artifact_id: str) -> bool:
        with self._connect() as db:
            return bool(db.execute(
                "SELECT 1 FROM state_patch_applications WHERE project_id=? AND artifact_id=? LIMIT 1",
                (project_id, source_artifact_id),
            ).fetchone())

    def mark_state_patch_applied(
        self, project_id: str, artifact_id: str, actor: str, note: str
    ) -> bool:
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO state_patch_applications VALUES(?,?,?,?,?)",
                (project_id, artifact_id, actor, note, utc_now()),
            )
        return cursor.rowcount > 0

    def unmark_state_patch_applied(self, project_id: str, artifact_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "DELETE FROM state_patch_applications WHERE project_id=? AND artifact_id=?",
                (project_id, artifact_id),
            )

    def delete_asset_versions(self, version_ids: list[str]) -> None:
        if not version_ids:
            return
        with self._lock, self._connect() as db:
            placeholders = ",".join("?" for _ in version_ids)
            db.execute(
                f"DELETE FROM asset_versions WHERE id IN ({placeholders})",  # noqa: S608
                version_ids,
            )

    def import_skill(
        self,
        skill_id: str,
        version_id: str,
        name: str,
        description: str,
        execution_mode: str,
        instructions: str,
        metadata: dict,
        capabilities: list[str],
        parameters_schema: dict,
        content_hash: str,
    ) -> Skill:
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM skills WHERE name=?", (name,)).fetchone()
            if row:
                skill_id = row["id"]
            else:
                db.execute(
                    "INSERT INTO skills VALUES(?,?,?,?,?,?)",
                    (skill_id, name, description, None, now, now),
                )
            version = db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM skill_versions WHERE skill_id=?",
                (skill_id,),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO skill_versions "
                "(id,skill_id,version,name,description,execution_mode,instructions,metadata,content_hash,created_at,capabilities,parameters_schema) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    version_id, skill_id, version, name, description, execution_mode,
                    instructions, json.dumps(metadata, ensure_ascii=False), content_hash, now,
                    json.dumps(capabilities),
                    json.dumps(parameters_schema, ensure_ascii=False),
                ),
            )
            db.execute(
                "UPDATE skills SET description=?,current_version_id=?,updated_at=? WHERE id=?",
                (description, version_id, now, skill_id),
            )
        return self.get_skill(skill_id)

    def list_skills(self) -> list[Skill]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT s.*,v.* FROM skills s JOIN skill_versions v "
                "ON v.id=s.current_version_id ORDER BY s.name"
            ).fetchall()
        return [self._skill_from_joined_row(row) for row in rows]

    def get_skill(self, skill_id: str) -> Skill | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT s.*,v.* FROM skills s JOIN skill_versions v "
                "ON v.id=s.current_version_id WHERE s.id=?",
                (skill_id,),
            ).fetchone()
        return self._skill_from_joined_row(row) if row else None

    def get_skill_by_name(self, name: str) -> Skill | None:
        with self._connect() as db:
            row = db.execute("SELECT id FROM skills WHERE name=?", (name,)).fetchone()
        return self.get_skill(row["id"]) if row else None

    def list_node_binding_templates(self) -> list[NodeBindingTemplate]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM node_binding_templates ORDER BY name").fetchall()
        return [self._template_from_row(row) for row in rows]

    def get_node_binding_template(self, template_id: str) -> NodeBindingTemplate | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM node_binding_templates WHERE id=?", (template_id,)
            ).fetchone()
        return self._template_from_row(row) if row else None

    def upsert_node_binding_template(
        self, template_id: str, template: NodeBindingTemplateCreate
    ) -> NodeBindingTemplate:
        now = utc_now()
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT id,created_at FROM node_binding_templates WHERE name=?",
                (template.name,),
            ).fetchone()
            if existing:
                template_id = existing["id"]
                db.execute(
                    "UPDATE node_binding_templates SET description=?,node_types=?,skills=?,updated_at=? WHERE id=?",
                    (
                        template.description, json.dumps(template.node_types),
                        json.dumps([item.model_dump(mode="json") for item in template.skills], ensure_ascii=False),
                        now, template_id,
                    ),
                )
            else:
                db.execute(
                    "INSERT INTO node_binding_templates VALUES(?,?,?,?,?,?,?)",
                    (
                        template_id, template.name, template.description,
                        json.dumps(template.node_types),
                        json.dumps([item.model_dump(mode="json") for item in template.skills], ensure_ascii=False),
                        now, now,
                    ),
                )
        return self.get_node_binding_template(template_id)

    def list_subflows(self) -> list[SubflowDefinition]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM subflows ORDER BY name").fetchall()
        return [self._subflow_from_row(row) for row in rows]

    def get_subflow(self, subflow_id: str) -> SubflowDefinition | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM subflows WHERE id=?", (subflow_id,)).fetchone()
        return self._subflow_from_row(row) if row else None

    def upsert_subflow(self, subflow_id: str, subflow: SubflowCreate) -> SubflowDefinition:
        now = utc_now()
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT id FROM subflows WHERE name=?", (subflow.name,)
            ).fetchone()
            if existing:
                subflow_id = existing["id"]
                db.execute(
                    "UPDATE subflows SET description=?,nodes=?,edges=?,updated_at=? WHERE id=?",
                    (
                        subflow.description,
                        json.dumps([item.model_dump(mode="json") for item in subflow.nodes], ensure_ascii=False),
                        json.dumps([item.model_dump(mode="json") for item in subflow.edges], ensure_ascii=False),
                        now, subflow_id,
                    ),
                )
            else:
                db.execute(
                    "INSERT INTO subflows VALUES(?,?,?,?,?,?,?)",
                    (
                        subflow_id, subflow.name, subflow.description,
                        json.dumps([item.model_dump(mode="json") for item in subflow.nodes], ensure_ascii=False),
                        json.dumps([item.model_dump(mode="json") for item in subflow.edges], ensure_ascii=False),
                        now, now,
                    ),
                )
        return self.get_subflow(subflow_id)

    def ensure_default_connection(self) -> None:
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO provider_connections "
                "(id,name,protocol,base_url,provider_identity,trust_group,is_local,trust_confirmed,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,0,1,?,?)",
                (
                    "deepseek-official", "DeepSeek 官方", "openai-compatible",
                    "https://api.deepseek.com", "deepseek", "deepseek-official", now, now,
                ),
            )
            for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
                db.execute(
                    "INSERT OR IGNORE INTO provider_models "
                    "(connection_id,model_id,name,family,reasoning,tool_call,source,updated_at) "
                    "VALUES('deepseek-official',?,?, 'deepseek-v4',1,1,'manual',?)",
                    (model_id, model_id, now),
                )
            db.execute(
                "UPDATE model_profiles SET connection_id=COALESCE(connection_id,'deepseek-official'), "
                "model_family=COALESCE(model_family,'deepseek-v4')"
            )

    def list_provider_connections(self, secret_store=None) -> list[ProviderConnection]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM provider_connections ORDER BY name").fetchall()
        return [self._connection_from_row(row, secret_store) for row in rows]

    def get_provider_connection(self, connection_id: str, secret_store=None) -> ProviderConnection | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM provider_connections WHERE id=?", (connection_id,)).fetchone()
        return self._connection_from_row(row, secret_store) if row else None

    def create_provider_connection(self, connection_id: str, connection: ProviderConnectionCreate) -> None:
        connection.validate_trust()
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO provider_connections VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    connection_id, connection.name, connection.protocol, connection.base_url,
                    connection.provider_identity, connection.trust_group, int(connection.is_local),
                    int(connection.trust_confirmed), now, now,
                ),
            )

    def update_provider_connection(self, connection_id: str, connection: ProviderConnectionCreate) -> bool:
        connection.validate_trust()
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "UPDATE provider_connections SET name=?,protocol=?,base_url=?,provider_identity=?,"
                "trust_group=?,is_local=?,trust_confirmed=?,updated_at=? WHERE id=?",
                (
                    connection.name, connection.protocol, connection.base_url,
                    connection.provider_identity, connection.trust_group, int(connection.is_local),
                    int(connection.trust_confirmed), utc_now(), connection_id,
                ),
            )
        return cursor.rowcount > 0

    def delete_provider_connection(self, connection_id: str) -> str:
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM provider_connections WHERE id=?", (connection_id,)).fetchone():
                return "missing"
            if db.execute("SELECT 1 FROM model_profiles WHERE connection_id=?", (connection_id,)).fetchone():
                return "used"
            db.execute("DELETE FROM provider_connections WHERE id=?", (connection_id,))
            db.execute("DELETE FROM provider_models WHERE connection_id=?", (connection_id,))
            return "deleted"

    def list_provider_models(self, connection_id: str | None = None) -> list[ProviderModel]:
        with self._connect() as db:
            if connection_id:
                rows = db.execute(
                    "SELECT * FROM provider_models WHERE connection_id=? ORDER BY name", (connection_id,)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM provider_models ORDER BY connection_id, name"
                ).fetchall()
        return [self._provider_model_from_row(row) for row in rows]

    def get_provider_model(self, connection_id: str, model_id: str) -> ProviderModel | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM provider_models WHERE connection_id=? AND model_id=?",
                (connection_id, model_id),
            ).fetchone()
        return self._provider_model_from_row(row) if row else None

    def upsert_provider_model(self, model: ProviderModelCreate, source: str = "manual") -> ProviderModel:
        with self._lock, self._connect() as db:
            if not db.execute(
                "SELECT 1 FROM provider_connections WHERE id=?", (model.connection_id,)
            ).fetchone():
                raise ValueError("供应商连接不存在")
            db.execute(
                "INSERT INTO provider_models VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(connection_id,model_id) DO UPDATE SET name=excluded.name,"
                "family=excluded.family,reasoning=excluded.reasoning,tool_call=excluded.tool_call,"
                "context_window=excluded.context_window,max_output=excluded.max_output,"
                "source=excluded.source,updated_at=excluded.updated_at",
                (
                    model.connection_id, model.model_id, model.name, model.family,
                    int(model.reasoning), int(model.tool_call), model.context_window,
                    model.max_output, source, utc_now(),
                ),
            )
        return next(
            item for item in self.list_provider_models(model.connection_id)
            if item.model_id == model.model_id
        )

    def sync_provider_models(self, connection_id: str, models: list[dict]) -> list[ProviderModel]:
        for item in models:
            model_id = str(item["id"])
            self.upsert_provider_model(
                ProviderModelCreate(
                    connection_id=connection_id, model_id=model_id,
                    name=str(item.get("name") or model_id),
                    family=str(item.get("family") or model_id),
                    reasoning=bool(item.get("reasoning", False)),
                    tool_call=bool(item.get("tool_call", False)),
                ),
                source="synced",
            )
        return self.list_provider_models(connection_id)

    def ensure_default_model_profile(self) -> None:
        with self._lock, self._connect() as db:
            profiles = db.execute(
                "SELECT id, is_default FROM model_profiles ORDER BY created_at, id"
            ).fetchall()
            if profiles:
                defaults = [row for row in profiles if row["is_default"]]
                if not defaults:
                    db.execute(
                        "UPDATE model_profiles SET is_default=1 WHERE id=?", (profiles[0]["id"],)
                    )
                elif len(defaults) > 1:
                    db.execute("UPDATE model_profiles SET is_default=0")
                    db.execute(
                        "UPDATE model_profiles SET is_default=1 WHERE id=?", (defaults[0]["id"],)
                    )
                db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_one_default_model_profile "
                    "ON model_profiles(is_default) WHERE is_default=1"
                )
                return
            now = utc_now()
            db.execute(
                "INSERT INTO model_profiles "
                "(id,name,provider,model,temperature,max_tokens,thinking,is_default,version,created_at,updated_at,connection_id,model_family) "
                "VALUES(?,?,?, ?,?,?,?,1,1,?,?,?,?)",
                (
                    "deepseek-balanced",
                    "DeepSeek Flash｜创作均衡",
                    "connection",
                    "deepseek-v4-flash",
                    0.8,
                    1000,
                    0,
                    now,
                    now,
                    "deepseek-official",
                    "deepseek-v4",
                ),
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_one_default_model_profile "
                "ON model_profiles(is_default) WHERE is_default=1"
            )

    def ensure_writing_pipeline_profiles(self) -> None:
        now = utc_now()
        with self._lock, self._connect() as db:
            templates = [
                ("reviewer-balanced", "独立审查｜待换绑", "deepseek-v4-flash", 0.2, 1800),
                ("arbiter-balanced", "裁决｜待换绑", "deepseek-v4-flash", 0.2, 1800),
                ("revision-balanced", "定向修订｜待换绑", "deepseek-v4-flash", 0.5, 2400),
            ]
            for profile_id, name, model, temperature, max_tokens in templates:
                db.execute(
                    "INSERT OR IGNORE INTO model_profiles "
                    "(id,name,provider,model,temperature,max_tokens,thinking,is_default,version,created_at,updated_at,connection_id,model_family) "
                    "VALUES(?,?, 'connection', ?,?,?,0,0,1,?,?, 'deepseek-official','deepseek-v4')",
                    (profile_id, name, model, temperature, max_tokens, now, now),
                )

    def list_model_profiles(self) -> list[ModelProfile]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM model_profiles ORDER BY is_default DESC, name"
            ).fetchall()
        return [self._model_profile_from_row(row) for row in rows]

    def get_model_profile(self, profile_id: str) -> ModelProfile | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM model_profiles WHERE id=?", (profile_id,)).fetchone()
        return self._model_profile_from_row(row) if row else None

    def create_model_profile(self, profile_id: str, profile: ModelProfileCreate) -> ModelProfile:
        now = utc_now()
        with self._lock, self._connect() as db:
            count = db.execute("SELECT COUNT(*) FROM model_profiles").fetchone()[0]
            is_default = profile.is_default or count == 0
            if is_default:
                db.execute("UPDATE model_profiles SET is_default=0")
            db.execute(
                "INSERT INTO model_profiles "
                "(id,name,provider,model,temperature,max_tokens,thinking,is_default,version,created_at,updated_at,connection_id,model_family) "
                "VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?)",
                (
                    profile_id, profile.name, "connection", profile.model,
                    profile.temperature, profile.max_tokens, int(profile.thinking),
                    int(is_default), now, now, profile.connection_id, profile.model_family,
                ),
            )
        return self.get_model_profile(profile_id)

    def update_model_profile(self, profile_id: str, profile: ModelProfileCreate) -> ModelProfile | None:
        with self._lock, self._connect() as db:
            if not db.execute("SELECT 1 FROM model_profiles WHERE id=?", (profile_id,)).fetchone():
                return None
            current = db.execute(
                "SELECT is_default FROM model_profiles WHERE id=?", (profile_id,)
            ).fetchone()
            if current["is_default"] and not profile.is_default:
                raise ValueError("默认配置档不能直接取消，请将另一个配置档设为默认")
            if profile.is_default:
                db.execute("UPDATE model_profiles SET is_default=0")
            db.execute(
                "UPDATE model_profiles SET name=?, model=?, model_family=?, connection_id=?, temperature=?, max_tokens=?, "
                "thinking=?, is_default=?, version=version+1, updated_at=? WHERE id=?",
                (
                    profile.name, profile.model, profile.model_family, profile.connection_id, profile.temperature,
                    profile.max_tokens, int(profile.thinking), int(profile.is_default),
                    utc_now(), profile_id,
                ),
            )
        return self.get_model_profile(profile_id)

    def delete_model_profile(self, profile_id: str) -> bool:
        with self._lock, self._connect() as db:
            profile = db.execute(
                "SELECT is_default FROM model_profiles WHERE id=?", (profile_id,)
            ).fetchone()
            if not profile or profile["is_default"]:
                return False
            db.execute("DELETE FROM model_profiles WHERE id=?", (profile_id,))
        return True

    def delete_model_profile_checked(self, profile_id: str) -> str:
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            profile = db.execute(
                "SELECT is_default FROM model_profiles WHERE id=?", (profile_id,)
            ).fetchone()
            if not profile:
                return "missing"
            if profile["is_default"]:
                return "default"
            rows = db.execute("SELECT document FROM workflows").fetchall()
            for row in rows:
                document = json.loads(row["document"])
                if any(
                    node.get("config", {}).get("profile_id") == profile_id
                    for node in document.get("nodes", [])
                ):
                    return "used"
            db.execute("DELETE FROM model_profiles WHERE id=?", (profile_id,))
            return "deleted"

    def model_profile_usage(self, profile_id: str) -> list[dict]:
        usage: list[dict] = []
        with self._connect() as db:
            rows = db.execute("SELECT id, document FROM workflows").fetchall()
        for row in rows:
            document = json.loads(row["document"])
            node_ids = [
                node["id"] for node in document.get("nodes", [])
                if node.get("config", {}).get("profile_id") == profile_id
            ]
            if node_ids:
                usage.append({"workflow_id": row["id"], "node_ids": node_ids})
        return usage

    def save_workflow(self, workflow: WorkflowDocument) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO workflows(id, document, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET document=excluded.document, updated_at=excluded.updated_at",
                (workflow.id, workflow.model_dump_json(), utc_now()),
            )

    def publish_workflow_version(self, workflow: WorkflowDocument, note: str = "") -> WorkflowVersion:
        version = WorkflowVersion(workflow_id=workflow.id, revision=workflow.revision, document=workflow, created_at=datetime.now(UTC), note=note)
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO workflow_versions VALUES(?,?,?,?,?)",
                (version.workflow_id, version.revision, version.document.model_dump_json(), version.note, version.created_at.isoformat()),
            )
        return self.get_workflow_version(workflow.id, workflow.revision) or version

    def list_workflow_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM workflow_versions WHERE workflow_id=? ORDER BY revision DESC", (workflow_id,)).fetchall()
        return [WorkflowVersion(workflow_id=row["workflow_id"], revision=row["revision"], document=WorkflowDocument.model_validate_json(row["document"]), created_at=row["created_at"], note=row["note"]) for row in rows]

    def get_workflow_version(self, workflow_id: str, revision: int) -> WorkflowVersion | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM workflow_versions WHERE workflow_id=? AND revision=?", (workflow_id, revision)).fetchone()
        return WorkflowVersion(workflow_id=row["workflow_id"], revision=row["revision"], document=WorkflowDocument.model_validate_json(row["document"]), created_at=row["created_at"], note=row["note"]) if row else None

    def save_workflow_checked(
        self, workflow: WorkflowDocument, expected_revision: int | None = None
    ) -> None:
        profile_ids = {
            str(node.config["profile_id"])
            for node in workflow.nodes
            if node.config.get("profile_id")
        }
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current_row = db.execute(
                "SELECT document FROM workflows WHERE id=?", (workflow.id,)
            ).fetchone()
            current_revision = (
                WorkflowDocument.model_validate_json(current_row["document"]).revision
                if current_row else 0
            )
            if expected_revision is not None and current_revision != expected_revision:
                raise ValueError(f"Workflow 版本冲突，当前版本为 {current_revision}")
            if expected_revision is not None and workflow.revision <= current_revision:
                raise ValueError(
                    f"Workflow revision 必须大于当前版本 {current_revision}"
                )
            if profile_ids:
                placeholders = ",".join("?" for _ in profile_ids)
                existing = {
                    row["id"] for row in db.execute(
                        f"SELECT id FROM model_profiles WHERE id IN ({placeholders})",
                        tuple(sorted(profile_ids)),
                    ).fetchall()
                }
                missing = profile_ids - existing
                if missing:
                    raise ValueError(f"模型配置档不存在: {', '.join(sorted(missing))}")
            db.execute(
                "INSERT INTO workflows(id, document, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET document=excluded.document, updated_at=excluded.updated_at",
                (workflow.id, workflow.model_dump_json(), utc_now()),
            )

    def get_workflow(self, workflow_id: str) -> WorkflowDocument | None:
        with self._connect() as db:
            row = db.execute("SELECT document FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        return WorkflowDocument.model_validate_json(row["document"]) if row else None

    def list_workflows(self) -> list[WorkflowDocument]:
        with self._connect() as db:
            rows = db.execute("SELECT document FROM workflows ORDER BY updated_at DESC").fetchall()
        return [WorkflowDocument.model_validate_json(row["document"]) for row in rows]

    def delete_workflow(self, workflow_id: str) -> bool:
        with self._lock, self._connect() as db:
            cursor = db.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
        return cursor.rowcount > 0

    def create_run(self, run_id: str, graph: ExecutionGraph, node_run_ids: dict[str, str]) -> None:
        now = utc_now()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO runs VALUES(?, ?, 'pending', ?, ?, ?, NULL)",
                (run_id, graph.workflow_id, graph.graph_hash, graph.model_dump_json(), now),
            )
            for node in graph.nodes:
                db.execute(
                    "INSERT INTO node_runs(id, run_id, node_id, node_type, status) VALUES(?, ?, ?, ?, 'pending')",
                    (node_run_ids[node.id], run_id, node.id, node.type),
                )

    def ensure_dynamic_node_run(
        self, node_run_id: str, run_id: str, node_id: str, node_type: str, input_snapshot: dict[str, Any] | None = None
    ) -> NodeRun:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO node_runs(id, run_id, node_id, node_type, status) "
                "VALUES(?, ?, ?, ?, 'pending')",
                (node_run_id, run_id, node_id, node_type),
            )
            if input_snapshot is not None:
                db.execute("UPDATE node_runs SET input_snapshot=? WHERE id=?", (json.dumps(input_snapshot, ensure_ascii=False), node_run_id))
        return self.get_node_run(node_run_id)

    def update_run(self, run_id: str, status: str) -> None:
        completed_at = utc_now() if status in {"succeeded", "failed", "cancelled"} else None
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE runs SET status=?, completed_at=COALESCE(?, completed_at) WHERE id=?",
                (status, completed_at, run_id),
            )

    def update_node_run(self, node_run_id: str, **changes: Any) -> None:
        allowed = {
            "status", "attempt", "input_artifact_ids", "output_artifact_id",
            "started_at", "completed_at", "error",
            "input_snapshot",
        }
        values = {key: value for key, value in changes.items() if key in allowed}
        if "input_artifact_ids" in values:
            values["input_artifact_ids"] = json.dumps(values["input_artifact_ids"])
        if "input_snapshot" in values:
            values["input_snapshot"] = json.dumps(values["input_snapshot"], ensure_ascii=False)
        if not values:
            return
        assignment = ", ".join(f"{key}=?" for key in values)
        with self._lock, self._connect() as db:
            db.execute(
                f"UPDATE node_runs SET {assignment} WHERE id=?",  # noqa: S608 - keys are allowlisted
                (*values.values(), node_run_id),
            )

    def create_attempt(
        self, attempt_id: str, node_run_id: str, attempt: int, input_artifact_ids: list[str]
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO node_attempts(id, node_run_id, attempt, status, input_artifact_ids, started_at) "
                "VALUES(?, ?, ?, 'running', ?, ?)",
                (attempt_id, node_run_id, attempt, json.dumps(input_artifact_ids), utc_now()),
            )

    def complete_attempt(
        self,
        attempt_id: str,
        status: str,
        output_artifact_id: str | None = None,
        error: str | None = None,
        cached_from_artifact_id: str | None = None,
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE node_attempts SET status=?, output_artifact_id=?, completed_at=?, error=?, "
                "cached_from_artifact_id=? WHERE id=?",
                (status, output_artifact_id, utc_now(), error, cached_from_artifact_id, attempt_id),
            )

    def list_attempts(self, node_run_id: str) -> list[NodeAttempt]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM node_attempts WHERE node_run_id=? ORDER BY attempt", (node_run_id,)
            ).fetchall()
        return [
            NodeAttempt(
                id=row["id"], node_run_id=row["node_run_id"], attempt=row["attempt"],
                status=row["status"], input_artifact_ids=json.loads(row["input_artifact_ids"]),
                output_artifact_id=row["output_artifact_id"], started_at=row["started_at"],
                completed_at=row["completed_at"], error=row["error"],
                cached_from_artifact_id=row["cached_from_artifact_id"],
            )
            for row in rows
        ]

    def get_attempt(self, attempt_id: str) -> NodeAttempt | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT node_run_id FROM node_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
        if not row:
            return None
        return next(
            (item for item in self.list_attempts(row["node_run_id"]) if item.id == attempt_id),
            None,
        )

    def create_provider_call(
        self,
        call_id: str,
        attempt_id: str,
        provider: str,
        model: str,
        request_payload: dict[str, Any],
    ) -> None:
        serialized_payload = json.dumps(request_payload, ensure_ascii=False)
        if len(serialized_payload.encode()) > MAX_PROVIDER_PAYLOAD_BYTES:
            raise ValueError("供应商请求审计载荷超过 8 MB 限制")
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO provider_calls(id, attempt_id, provider, model, request_payload, status, started_at) "
                "VALUES(?, ?, ?, ?, ?, 'running', ?)",
                (
                    call_id,
                    attempt_id,
                    provider,
                    model,
                    serialized_payload,
                    utc_now(),
                ),
            )

    def complete_provider_call(
        self,
        call_id: str,
        *,
        status: str,
        request_id: str | None = None,
        response_payload: dict[str, Any] | None = None,
        usage: ProviderUsage | None = None,
        finish_reason: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        serialized_response = (
            json.dumps(response_payload, ensure_ascii=False)
            if response_payload is not None else None
        )
        if serialized_response and len(serialized_response.encode()) > MAX_PROVIDER_PAYLOAD_BYTES:
            raise ValueError("供应商响应审计载荷超过 8 MB 限制")
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE provider_calls SET status=?, request_id=?, response_payload=?, usage=?, "
                "finish_reason=?, error=?, completed_at=? WHERE id=?",
                (
                    status,
                    request_id,
                    serialized_response,
                    usage.model_dump_json() if usage else None,
                    finish_reason,
                    json.dumps(error, ensure_ascii=False) if error else None,
                    utc_now(),
                    call_id,
                ),
            )

    def list_provider_calls(self, attempt_id: str) -> list[ProviderCall]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM provider_calls WHERE attempt_id=? ORDER BY started_at", (attempt_id,)
            ).fetchall()
        return [
            ProviderCall(
                id=row["id"],
                attempt_id=row["attempt_id"],
                provider=row["provider"],
                model=row["model"],
                request_id=row["request_id"],
                request_payload=json.loads(row["request_payload"]),
                response_payload=json.loads(row["response_payload"]) if row["response_payload"] else None,
                usage=ProviderUsage.model_validate_json(row["usage"]) if row["usage"] else None,
                finish_reason=row["finish_reason"],
                status=row["status"],
                error=json.loads(row["error"]) if row["error"] else None,
                started_at=row["started_at"],
                completed_at=row["completed_at"],
            )
            for row in rows
        ]

    def save_artifact(self, artifact: Artifact) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO artifacts VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact.id, artifact.run_id, artifact.node_run_id, artifact.schema_type,
                    json.dumps(artifact.content, ensure_ascii=False), artifact.content_hash,
                    json.dumps(artifact.parent_artifact_ids), artifact.created_at.isoformat(),
                ),
            )

    def save_cache_entry(self, cache_key: str, artifact_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO cache_entries(cache_key, artifact_id, created_at) VALUES(?, ?, ?) "
                "ON CONFLICT(cache_key) DO UPDATE SET artifact_id=excluded.artifact_id, created_at=excluded.created_at",
                (cache_key, artifact_id, utc_now()),
            )

    def get_cached_artifact(self, cache_key: str) -> Artifact | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT artifact_id FROM cache_entries WHERE cache_key=?", (cache_key,)
            ).fetchone()
        return self.get_artifact(row["artifact_id"]) if row else None

    def append_event(
        self, event_id: str, run_id: str, node_run_id: str | None, event_type: str, payload: dict[str, Any]
    ) -> Event:
        timestamp = utc_now()
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "INSERT INTO events(event_id, run_id, node_run_id, type, timestamp, payload) VALUES(?, ?, ?, ?, ?, ?)",
                (event_id, run_id, node_run_id, event_type, timestamp, json.dumps(payload, ensure_ascii=False)),
            )
            sequence = cursor.lastrowid
        return Event(
            sequence=sequence, event_id=event_id, run_id=run_id, node_run_id=node_run_id,
            type=event_type, timestamp=timestamp, payload=payload,
        )

    def list_events(self, run_id: str, after: int = 0) -> list[Event]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE run_id=? AND sequence>? ORDER BY sequence",
                (run_id, after),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def get_run(self, run_id: str) -> Run | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                return None
            node_rows = db.execute(
                "SELECT * FROM node_runs WHERE run_id=? ORDER BY rowid", (run_id,)
            ).fetchall()
        return Run(
            id=row["id"], workflow_id=row["workflow_id"], status=row["status"],
            graph_hash=row["graph_hash"], snapshot=ExecutionGraph.model_validate_json(row["snapshot"]),
            created_at=row["created_at"], completed_at=row["completed_at"],
            node_runs=[self._node_run_from_row(item) for item in node_rows],
        )

    def get_latest_run_for_workflow(self, workflow_id: str, project_id: str | None = None) -> Run | None:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM runs WHERE workflow_id=? ORDER BY created_at DESC",
                (workflow_id,),
            ).fetchall()
        for row in rows:
            run = self.get_run(row["id"])
            if run and (project_id is None or run.snapshot.run_context.get("project_id") == project_id):
                return run
        return None

    def list_runs(self, project_id: str | None = None, limit: int = 50) -> list[Run]:
        """Return recent run snapshots for the local run history panel."""
        safe_limit = max(1, min(limit, 200))
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM runs ORDER BY created_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        runs: list[Run] = []
        for row in rows:
            run = self.get_run(row["id"])
            if run and (project_id is None or run.snapshot.run_context.get("project_id") == project_id):
                runs.append(run)
        return runs

    def get_latest_production_run_for_stage(self, project_id: str, stage_id: str) -> Run | None:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM runs WHERE workflow_id LIKE 'production:%' ORDER BY created_at DESC"
            ).fetchall()
        for row in rows:
            run = self.get_run(row["id"])
            if not run or run.snapshot.run_context.get("project_id") != project_id:
                continue
            if stage_id in run.snapshot.run_context.get("component_workflows", {}):
                return run
        return None

    def list_incomplete_run_ids(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM runs WHERE status IN ('pending', 'running') ORDER BY created_at"
            ).fetchall()
        return [row["id"] for row in rows]

    def migrate_legacy_run_context(
        self, run_id: str, project: Project, chapter_number: int = 1
    ) -> bool:
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT snapshot FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                return False
            graph = ExecutionGraph.model_validate_json(row["snapshot"])
            if graph.run_context.get("project_id"):
                return False
            archive_path = f"{project.slug}/manuscript/chapter-{chapter_number:04d}.md"
            graph.run_context = {
                "project_id": project.id,
                "project_title": project.title,
                "project_slug": project.slug,
                "chapter_number": chapter_number,
                "archive_path": archive_path,
            }
            for node in graph.nodes:
                if node.type == "writing.chapter_archive":
                    node.config.update({
                        "chapter_path": archive_path,
                        "project_id": project.id,
                        "chapter_number": chapter_number,
                    })
            graph.graph_hash = hashlib.sha256(
                json.dumps(
                    graph.model_dump(exclude={"graph_hash"}),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            db.execute(
                "UPDATE runs SET snapshot=?,graph_hash=? WHERE id=?",
                (graph.model_dump_json(), graph.graph_hash, run_id),
            )
        return True

    def get_approval_for_node(self, node_run_id: str) -> ApprovalRecord | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM approvals WHERE node_run_id=?", (node_run_id,)
            ).fetchone()
        return self._approval_from_row(row) if row else None

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        return self._approval_from_row(row) if row else None

    def list_pending_approvals(self) -> list[ApprovalRecord]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM approvals WHERE status='pending' ORDER BY created_at"
            ).fetchall()
        return [self._approval_from_row(row) for row in rows]

    def create_approval(
        self, approval_id: str, run_id: str, node_run_id: str, artifact_ids: list[str]
    ) -> ApprovalRecord:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO approvals "
                "(id,run_id,node_run_id,status,artifact_ids,created_at) VALUES(?,?,?,'pending',?,?)",
                (approval_id, run_id, node_run_id, json.dumps(artifact_ids), utc_now()),
            )
        return self.get_approval_for_node(node_run_id)

    def decide_approval(
        self, approval_id: str, decision: str, actor: str, note: str
    ) -> ApprovalRecord | None:
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if not row or row["status"] != "pending":
                return None
            db.execute(
                "UPDATE approvals SET status=?,actor=?,note=?,decided_at=? WHERE id=?",
                (decision, actor, note, utc_now(), approval_id),
            )
            node_status = "pending" if decision == "approved" else "rejected"
            db.execute(
                "UPDATE node_runs SET status=?,error=? WHERE id=?",
                (node_status, None if decision == "approved" else "人工驳回", row["node_run_id"]),
            )
            db.execute(
                "UPDATE runs SET status=?,completed_at=? WHERE id=?",
                (
                    "pending" if decision == "approved" else "rejected",
                    None if decision == "approved" else utc_now(),
                    row["run_id"],
                ),
            )
        return self.get_approval(approval_id)

    def get_node_run(self, node_run_id: str) -> NodeRun | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM node_runs WHERE id=?", (node_run_id,)).fetchone()
        return self._node_run_from_row(row) if row else None

    def reset_node_runs(self, run_id: str, node_ids: set[str]) -> None:
        if not node_ids:
            return
        with self._lock, self._connect() as db:
            placeholders = ",".join("?" for _ in node_ids)
            db.execute(
                f"UPDATE node_runs SET status='pending', output_artifact_id=NULL, started_at=NULL, "
                f"completed_at=NULL, error=NULL WHERE run_id=? AND node_id IN ({placeholders})",
                (run_id, *sorted(node_ids)),
            )
            db.execute("UPDATE runs SET status='pending', completed_at=NULL WHERE id=?", (run_id,))

    def prepare_run_for_recovery(self, run_id: str) -> int:
        now = utc_now()
        recovered_count = 0
        with self._lock, self._connect() as db:
            running_ids = [
                row["id"] for row in db.execute(
                    "SELECT id FROM node_runs WHERE run_id=? AND status='running'", (run_id,)
                ).fetchall()
            ]
            if running_ids:
                recovered_count = len(running_ids)
                placeholders = ",".join("?" for _ in running_ids)
                db.execute(
                    f"UPDATE node_attempts SET status='interrupted', completed_at=?, "
                    f"error='进程中断，等待恢复' WHERE status='running' AND node_run_id IN ({placeholders})",
                    (now, *running_ids),
                )
                db.execute(
                    f"UPDATE node_runs SET status='pending', error=NULL WHERE id IN ({placeholders})",
                    running_ids,
                )
                db.execute(
                    f"UPDATE provider_calls SET status='interrupted', completed_at=?, "
                    f"error=? WHERE status='running' AND attempt_id IN ("
                    f"SELECT id FROM node_attempts WHERE node_run_id IN ({placeholders}))",
                    (
                        now,
                        json.dumps({"message": "进程中断，远端请求结果未知，可能已经产生费用"}, ensure_ascii=False),
                        *running_ids,
                    ),
                )
            db.execute("UPDATE runs SET status='pending', completed_at=NULL WHERE id=?", (run_id,))
        return recovered_count

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            return None
        return Artifact(
            id=row["id"], run_id=row["run_id"], node_run_id=row["node_run_id"],
            schema_type=row["schema_type"], content=json.loads(row["content"]),
            content_hash=row["content_hash"], parent_artifact_ids=json.loads(row["parent_artifact_ids"]),
            created_at=row["created_at"],
        )

    def list_artifacts_by_schema(self, schema_type: str) -> list[Artifact]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM artifacts WHERE schema_type=? ORDER BY created_at DESC",
                (schema_type,),
            ).fetchall()
        return [
            Artifact(
                id=row["id"], run_id=row["run_id"], node_run_id=row["node_run_id"],
                schema_type=row["schema_type"], content=json.loads(row["content"]),
                content_hash=row["content_hash"],
                parent_artifact_ids=json.loads(row["parent_artifact_ids"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> Event:
        return Event(
            sequence=row["sequence"], event_id=row["event_id"], run_id=row["run_id"],
            node_run_id=row["node_run_id"], type=row["type"], timestamp=row["timestamp"],
            payload=json.loads(row["payload"]),
        )

    @staticmethod
    def _node_run_from_row(row: sqlite3.Row) -> NodeRun:
        return NodeRun(
            id=row["id"], run_id=row["run_id"], node_id=row["node_id"], node_type=row["node_type"],
            status=row["status"], attempt=row["attempt"],
            input_artifact_ids=json.loads(row["input_artifact_ids"]),
            output_artifact_id=row["output_artifact_id"], started_at=row["started_at"],
            completed_at=row["completed_at"], error=row["error"],
            input_snapshot=json.loads(row["input_snapshot"]) if row["input_snapshot"] else None,
        )

    @staticmethod
    def _model_profile_from_row(row: sqlite3.Row) -> ModelProfile:
        return ModelProfile(
            id=row["id"], name=row["name"], connection_id=row["connection_id"] or "deepseek-official",
            model=row["model"], model_family=row["model_family"] or "deepseek-v4",
            temperature=row["temperature"], max_tokens=row["max_tokens"],
            thinking=bool(row["thinking"]), is_default=bool(row["is_default"]),
            version=row["version"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _connection_from_row(row: sqlite3.Row, secret_store=None) -> ProviderConnection:
        secret = secret_store.get_provider(row["id"]) if secret_store else {}
        key = secret.get("api_key")
        return ProviderConnection(
            id=row["id"], name=row["name"], protocol=row["protocol"], base_url=row["base_url"],
            provider_identity=row["provider_identity"], trust_group=row["trust_group"],
            is_local=bool(row["is_local"]), trust_confirmed=bool(row["trust_confirmed"]),
            has_api_key=bool(key), key_hint=f"...{key[-4:]}" if key else None,
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _provider_model_from_row(row: sqlite3.Row) -> ProviderModel:
        return ProviderModel(
            connection_id=row["connection_id"], model_id=row["model_id"], name=row["name"],
            family=row["family"], reasoning=bool(row["reasoning"]),
            tool_call=bool(row["tool_call"]), context_window=row["context_window"],
            max_output=row["max_output"], source=row["source"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _approval_from_row(row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            id=row["id"], run_id=row["run_id"], node_run_id=row["node_run_id"],
            status=row["status"], artifact_ids=json.loads(row["artifact_ids"]),
            actor=row["actor"], note=row["note"], created_at=row["created_at"],
            decided_at=row["decided_at"],
        )

    @staticmethod
    def _project_from_row(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"], title=row["title"], slug=row["slug"],
            current_chapter=row["current_chapter"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _asset_version_from_row(row: sqlite3.Row) -> AssetVersion:
        return AssetVersion(
            id=row["id"], project_id=row["project_id"], relative_path=row["relative_path"],
            version=row["version"], content_hash=row["content_hash"],
            previous_hash=row["previous_hash"], content=row["content"], actor=row["actor"],
            note=row["note"], source_artifact_id=row["source_artifact_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _skill_from_joined_row(row: sqlite3.Row) -> Skill:
        version = SkillVersion(
            id=row["current_version_id"], skill_id=row["skill_id"],
            version=row["version"], name=row["name"], description=row["description"],
            execution_mode=row["execution_mode"], instructions=row["instructions"],
            metadata=json.loads(row["metadata"]), content_hash=row["content_hash"],
            capabilities=json.loads(row["capabilities"]),
            parameters_schema=json.loads(row["parameters_schema"]),
            created_at=row["created_at"],
        )
        return Skill(
            id=row["skill_id"], name=version.name, description=version.description,
            current_version=version, created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _template_from_row(row: sqlite3.Row) -> NodeBindingTemplate:
        return NodeBindingTemplate(
            id=row["id"], name=row["name"], description=row["description"],
            node_types=json.loads(row["node_types"]), skills=json.loads(row["skills"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _subflow_from_row(row: sqlite3.Row) -> SubflowDefinition:
        return SubflowDefinition(
            id=row["id"], name=row["name"], description=row["description"],
            nodes=json.loads(row["nodes"]), edges=json.loads(row["edges"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
