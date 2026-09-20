"""数据库持久化，兼容 SQLite 开发库和 MySQL 生产库。"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse

from ..models import SurveyResponse, WrappedSurvey


SURVEY_COLLECTING_STATUS = "collecting"
SURVEY_PUBLIC_STATUSES = {SURVEY_COLLECTING_STATUS}
SURVEY_STATUSES = {"draft", "collecting", "ended", "archived"}
ADMIN_SESSION_HOURS = 8
DEFAULT_TENANT_SLUG = "demo-tenant"
DEFAULT_TENANT_TOKEN_BALANCE = 100000
DEFAULT_OWNER_USERNAME = "aixin"
DEFAULT_OWNER_PASSWORD = "123456"


class ResearchDatabase:
    """保存问卷、答卷、管理员账号和审计记录。"""

    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self.engine = "mysql" if database_path.startswith(("mysql://", "mysql+pymysql://")) else "sqlite"
        self.param = "%s" if self.engine == "mysql" else "?"
        self.mysql_config = self._parse_mysql_url(database_path) if self.engine == "mysql" else None
        if self.engine == "sqlite":
            path = Path(database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self.engine == "mysql":
            try:
                import pymysql
            except ImportError as exc:
                raise RuntimeError("使用 MySQL 需要先安装 PyMySQL：pip install PyMySQL") from exc
            assert self.mysql_config is not None
            connection = pymysql.connect(**self.mysql_config)
        else:
            connection = sqlite3.connect(self.database_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _execute(self, connection: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
        cursor = connection.cursor()
        cursor.execute(sql.replace("?", self.param), params)
        return cursor

    def _fetchone(self, connection: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cursor = self._execute(connection, sql, params)
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def _fetchall(self, connection: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor = self._execute(connection, sql, params)
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return dict(row)
        return dict(row)

    def _init_schema(self) -> None:
        with self._connection() as connection:
            if self.engine == "mysql":
                self._init_mysql_schema(connection)
            else:
                self._init_sqlite_schema(connection)
            self._ensure_tenant_seed(connection)
            self._ensure_admin_seed(connection)
            self._backfill_tenant_links(connection)
            self._backfill_share_tokens(connection)
            self._normalize_response_sources(connection)

    def _init_sqlite_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                tenant_id INTEGER,
                display_name TEXT,
                email TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                user_agent TEXT,
                ip_hash TEXT,
                FOREIGN KEY (admin_id) REFERENCES admin_users(id)
            );
            CREATE TABLE IF NOT EXISTS login_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_hash TEXT,
                failed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id INTEGER,
                detail TEXT,
                created_at TEXT NOT NULL,
                ip_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS wrapped_surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_name TEXT NOT NULL,
                theme TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                target_sample_count INTEGER,
                ended_at TEXT,
                analysis_payload TEXT,
                deleted_at TEXT,
                share_token TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                prompt_version TEXT,
                model_name TEXT,
                generation_latency_ms INTEGER,
                quality_score REAL,
                tenant_id INTEGER,
                team_id INTEGER,
                created_by INTEGER,
                moderation_status TEXT NOT NULL DEFAULT 'approved',
                moderation_note TEXT,
                reviewed_by INTEGER,
                reviewed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER,
                survey_version INTEGER NOT NULL DEFAULT 1,
                result_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                submitted_at TEXT,
                payload TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'public_link',
                duration_seconds INTEGER,
                fingerprint_hash TEXT,
                browser_id_hash TEXT,
                ip_hash TEXT,
                access_code TEXT,
                is_test INTEGER NOT NULL DEFAULT 0,
                is_invalid INTEGER NOT NULL DEFAULT 0,
                invalid_reason TEXT,
                invalid_at TEXT,
                FOREIGN KEY (survey_id) REFERENCES wrapped_surveys(id)
            );
            CREATE TABLE IF NOT EXISTS generation_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER,
                tenant_id INTEGER,
                created_by INTEGER,
                prompt_version TEXT NOT NULL,
                model_name TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                token_estimate INTEGER NOT NULL,
                cost_estimate REAL NOT NULL,
                quality_score REAL NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (survey_id) REFERENCES wrapped_surveys(id)
            );
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                plan TEXT NOT NULL DEFAULT 'starter',
                token_balance INTEGER NOT NULL DEFAULT 0,
                token_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                created_by INTEGER,
                UNIQUE(tenant_id, name)
            );
            CREATE TABLE IF NOT EXISTS team_members (
                team_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'manager',
                status TEXT NOT NULL DEFAULT 'accepted',
                invited_by INTEGER,
                invited_at TEXT,
                responded_at TEXT,
                PRIMARY KEY (team_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS team_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                invitee_id INTEGER NOT NULL,
                invited_by INTEGER NOT NULL,
                permission TEXT NOT NULL DEFAULT 'viewer',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                responded_at TEXT
            );
            CREATE TABLE IF NOT EXISTS survey_permissions (
                survey_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permission TEXT NOT NULL DEFAULT 'viewer',
                granted_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (survey_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS token_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                requested_by INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by INTEGER,
                reviewed_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS platform_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_responses_survey_id ON responses(survey_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_wrapped_surveys_share_token ON wrapped_surveys(share_token);
            """
        )
        self._ensure_columns(
            connection,
            "wrapped_surveys",
            {
                "status": "TEXT NOT NULL DEFAULT 'draft'",
                "target_sample_count": "INTEGER",
                "ended_at": "TEXT",
                "analysis_payload": "TEXT",
                "deleted_at": "TEXT",
                "share_token": "TEXT",
                "version": "INTEGER NOT NULL DEFAULT 1",
                "prompt_version": "TEXT",
                "model_name": "TEXT",
                "generation_latency_ms": "INTEGER",
                "quality_score": "REAL",
                "tenant_id": "INTEGER",
                "team_id": "INTEGER",
                "created_by": "INTEGER",
                "moderation_status": "TEXT NOT NULL DEFAULT 'approved'",
                "moderation_note": "TEXT",
                "reviewed_by": "INTEGER",
                "reviewed_at": "TEXT",
            },
        )
        self._ensure_columns(
            connection,
            "admin_users",
            {
                "tenant_id": "INTEGER",
                "display_name": "TEXT",
                "email": "TEXT",
            },
        )
        self._ensure_columns(
            connection,
            "generation_records",
            {
                "tenant_id": "INTEGER",
                "created_by": "INTEGER",
            },
        )
        self._ensure_columns(
            connection,
            "responses",
            {
                "survey_version": "INTEGER NOT NULL DEFAULT 1",
                "submitted_at": "TEXT",
                "source": "TEXT NOT NULL DEFAULT 'public_link'",
                "duration_seconds": "INTEGER",
                "fingerprint_hash": "TEXT",
                "browser_id_hash": "TEXT",
                "ip_hash": "TEXT",
                "access_code": "TEXT",
                "is_test": "INTEGER NOT NULL DEFAULT 0",
                "is_invalid": "INTEGER NOT NULL DEFAULT 0",
                "invalid_reason": "TEXT",
                "invalid_at": "TEXT",
            },
        )
        self._ensure_columns(
            connection,
            "team_members",
            {
                "role": "TEXT NOT NULL DEFAULT 'manager'",
                "status": "TEXT NOT NULL DEFAULT 'accepted'",
                "invited_by": "INTEGER",
                "invited_at": "TEXT",
                "responded_at": "TEXT",
            },
        )
        connection.execute(
            "UPDATE wrapped_surveys SET status = 'collecting' WHERE status = 'open'"
        )
        connection.execute(
            "UPDATE wrapped_surveys SET status = 'draft' WHERE status = 'pending'"
        )
        connection.execute(
            "UPDATE wrapped_surveys SET status = 'ended' WHERE status = 'paused'"
        )

    def _init_mysql_schema(self, connection: Any) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INT PRIMARY KEY,
                applied_at VARCHAR(32) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(80) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'admin',
                tenant_id INT,
                display_name VARCHAR(120),
                email VARCHAR(255),
                is_active TINYINT NOT NULL DEFAULT 1,
                created_at VARCHAR(32) NOT NULL,
                updated_at VARCHAR(32) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                admin_id INT NOT NULL,
                token_hash VARCHAR(128) NOT NULL UNIQUE,
                expires_at VARCHAR(32) NOT NULL,
                created_at VARCHAR(32) NOT NULL,
                last_seen_at VARCHAR(32) NOT NULL,
                user_agent VARCHAR(255),
                ip_hash VARCHAR(128),
                INDEX idx_admin_sessions_admin_id (admin_id),
                CONSTRAINT fk_admin_sessions_admin FOREIGN KEY (admin_id) REFERENCES admin_users(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS login_failures (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(80) NOT NULL,
                ip_hash VARCHAR(128),
                failed_at VARCHAR(32) NOT NULL,
                INDEX idx_login_failures_lookup (username, failed_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                admin_id INT,
                action VARCHAR(120) NOT NULL,
                target_type VARCHAR(80),
                target_id INT,
                detail TEXT,
                created_at VARCHAR(32) NOT NULL,
                ip_hash VARCHAR(128),
                INDEX idx_operation_logs_target (target_type, target_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS wrapped_surveys (
                id INT AUTO_INCREMENT PRIMARY KEY,
                survey_name VARCHAR(255) NOT NULL,
                theme VARCHAR(255) NOT NULL,
                source VARCHAR(64) NOT NULL,
                created_at VARCHAR(32) NOT NULL,
                payload LONGTEXT NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'draft',
                target_sample_count INT,
                ended_at VARCHAR(32),
                analysis_payload LONGTEXT,
                deleted_at VARCHAR(32),
                share_token VARCHAR(64),
                version INT NOT NULL DEFAULT 1,
                prompt_version VARCHAR(80),
                model_name VARCHAR(120),
                generation_latency_ms INT,
                quality_score DOUBLE,
                tenant_id INT,
                team_id INT,
                created_by INT,
                moderation_status VARCHAR(32) NOT NULL DEFAULT 'approved',
                moderation_note VARCHAR(500),
                reviewed_by INT,
                reviewed_at VARCHAR(32),
                UNIQUE KEY idx_wrapped_surveys_share_token (share_token)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS responses (
                id INT AUTO_INCREMENT PRIMARY KEY,
                survey_id INT,
                survey_version INT NOT NULL DEFAULT 1,
                result_type VARCHAR(255) NOT NULL,
                created_at VARCHAR(32) NOT NULL,
                submitted_at VARCHAR(32),
                payload LONGTEXT NOT NULL,
                source VARCHAR(32) NOT NULL DEFAULT 'public_link',
                duration_seconds INT,
                fingerprint_hash VARCHAR(128),
                browser_id_hash VARCHAR(128),
                ip_hash VARCHAR(128),
                access_code VARCHAR(80),
                is_test TINYINT NOT NULL DEFAULT 0,
                is_invalid TINYINT NOT NULL DEFAULT 0,
                invalid_reason VARCHAR(255),
                invalid_at VARCHAR(32),
                INDEX idx_responses_survey_id (survey_id),
                CONSTRAINT fk_responses_survey FOREIGN KEY (survey_id) REFERENCES wrapped_surveys(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS generation_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                survey_id INT,
                tenant_id INT,
                created_by INT,
                prompt_version VARCHAR(80) NOT NULL,
                model_name VARCHAR(120) NOT NULL,
                latency_ms INT NOT NULL,
                token_estimate INT NOT NULL,
                cost_estimate DOUBLE NOT NULL,
                quality_score DOUBLE NOT NULL,
                retry_count INT NOT NULL DEFAULT 0,
                status VARCHAR(32) NOT NULL,
                error_message VARCHAR(500),
                created_at VARCHAR(32) NOT NULL,
                INDEX idx_generation_records_survey_id (survey_id),
                CONSTRAINT fk_generation_records_survey FOREIGN KEY (survey_id) REFERENCES wrapped_surveys(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(160) NOT NULL,
                slug VARCHAR(120) NOT NULL UNIQUE,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                plan VARCHAR(32) NOT NULL DEFAULT 'starter',
                token_balance BIGINT NOT NULL DEFAULT 0,
                token_used BIGINT NOT NULL DEFAULT 0,
                created_at VARCHAR(32) NOT NULL,
                updated_at VARCHAR(32) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS teams (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tenant_id INT NOT NULL,
                name VARCHAR(120) NOT NULL,
                description VARCHAR(500),
                created_at VARCHAR(32) NOT NULL,
                created_by INT,
                UNIQUE KEY idx_teams_tenant_name (tenant_id, name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS team_members (
                team_id INT NOT NULL,
                user_id INT NOT NULL,
                created_at VARCHAR(32) NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'manager',
                status VARCHAR(32) NOT NULL DEFAULT 'accepted',
                invited_by INT,
                invited_at VARCHAR(32),
                responded_at VARCHAR(32),
                PRIMARY KEY (team_id, user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS team_invitations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                team_id INT NOT NULL,
                invitee_id INT NOT NULL,
                invited_by INT NOT NULL,
                permission VARCHAR(32) NOT NULL DEFAULT 'viewer',
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                created_at VARCHAR(32) NOT NULL,
                responded_at VARCHAR(32),
                INDEX idx_team_invitations_invitee (invitee_id, status),
                INDEX idx_team_invitations_team (team_id, status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS survey_permissions (
                survey_id INT NOT NULL,
                user_id INT NOT NULL,
                permission VARCHAR(32) NOT NULL DEFAULT 'viewer',
                granted_by INT NOT NULL,
                created_at VARCHAR(32) NOT NULL,
                updated_at VARCHAR(32) NOT NULL,
                PRIMARY KEY (survey_id, user_id),
                INDEX idx_survey_permissions_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS token_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tenant_id INT NOT NULL,
                requested_by INT NOT NULL,
                amount BIGINT NOT NULL,
                reason VARCHAR(500) NOT NULL DEFAULT '',
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                reviewed_by INT,
                reviewed_at VARCHAR(32),
                created_at VARCHAR(32) NOT NULL,
                INDEX idx_token_requests_tenant (tenant_id, status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS platform_settings (
                setting_key VARCHAR(120) PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at VARCHAR(32) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        ]
        for statement in statements:
            self._execute(connection, statement)
        self._ensure_columns(
            connection,
            "wrapped_surveys",
            {
                "target_sample_count": "INT",
                "version": "INT NOT NULL DEFAULT 1",
                "prompt_version": "VARCHAR(80)",
                "model_name": "VARCHAR(120)",
                "generation_latency_ms": "INT",
                "quality_score": "DOUBLE",
                "tenant_id": "INT",
                "team_id": "INT",
                "created_by": "INT",
                "moderation_status": "VARCHAR(32) NOT NULL DEFAULT 'approved'",
                "moderation_note": "VARCHAR(500)",
                "reviewed_by": "INT",
                "reviewed_at": "VARCHAR(32)",
            },
        )
        self._ensure_columns(
            connection,
            "admin_users",
            {
                "tenant_id": "INT",
                "display_name": "VARCHAR(120)",
                "email": "VARCHAR(255)",
            },
        )
        self._ensure_columns(
            connection,
            "generation_records",
            {
                "tenant_id": "INT",
                "created_by": "INT",
            },
        )
        self._ensure_columns(
            connection,
            "responses",
            {
                "survey_version": "INT NOT NULL DEFAULT 1",
                "submitted_at": "VARCHAR(32)",
                "source": "VARCHAR(32) NOT NULL DEFAULT 'public_link'",
                "duration_seconds": "INT",
                "fingerprint_hash": "VARCHAR(128)",
                "browser_id_hash": "VARCHAR(128)",
                "ip_hash": "VARCHAR(128)",
                "access_code": "VARCHAR(80)",
                "is_test": "TINYINT NOT NULL DEFAULT 0",
                "is_invalid": "TINYINT NOT NULL DEFAULT 0",
                "invalid_reason": "VARCHAR(255)",
                "invalid_at": "VARCHAR(32)",
            },
        )
        self._ensure_columns(
            connection,
            "team_members",
            {
                "role": "VARCHAR(32) NOT NULL DEFAULT 'manager'",
                "status": "VARCHAR(32) NOT NULL DEFAULT 'accepted'",
                "invited_by": "INT",
                "invited_at": "VARCHAR(32)",
                "responded_at": "VARCHAR(32)",
            },
        )
        self._execute(connection, "UPDATE wrapped_surveys SET status = 'collecting' WHERE status = 'open'")
        self._execute(connection, "UPDATE wrapped_surveys SET status = 'draft' WHERE status = 'pending'")
        self._execute(connection, "UPDATE wrapped_surveys SET status = 'ended' WHERE status = 'paused'")

    def _normalize_response_sources(self, connection: Any) -> None:
        """后台浏览答卷默认参与统计，只有明确测试来源才排除。"""

        self._execute(
            connection,
            "UPDATE responses SET is_test = 0 WHERE source = 'admin_preview'",
        )

    def _ensure_tenant_seed(self, connection: Any) -> None:
        """为旧数据补建一个演示租户，并提供可展示的初始 Token 额度。"""

        row = self._fetchone(
            connection,
            "SELECT id FROM tenants WHERE slug = ?",
            (DEFAULT_TENANT_SLUG,),
        )
        if not row:
            now = self._now()
            self._execute(
                connection,
                "INSERT INTO tenants "
                "(name, slug, status, plan, token_balance, token_used, created_at, updated_at) "
                "VALUES (?, ?, 'active', 'starter', ?, 0, ?, ?)",
                ("趣测智研演示空间", DEFAULT_TENANT_SLUG, DEFAULT_TENANT_TOKEN_BALANCE, now, now),
            )
        self._ensure_platform_settings(connection)

    def _ensure_platform_settings(self, connection: Any) -> None:
        now = self._now()
        defaults = {
            "default_registration_tokens": "20000",
            "parse_request_tokens": "800",
            "analysis_request_tokens": "1800",
            "content_review_required": "false",
        }
        for key, value in defaults.items():
            self._execute(
                connection,
                "INSERT INTO platform_settings (setting_key, setting_value, updated_at) "
                "SELECT ?, ?, ? WHERE NOT EXISTS "
                "(SELECT 1 FROM platform_settings WHERE setting_key = ?)",
                (key, value, now, key),
            )

    def _default_tenant_id(self, connection: Any) -> int | None:
        row = self._fetchone(
            connection,
            "SELECT id FROM tenants WHERE slug = ?",
            (DEFAULT_TENANT_SLUG,),
        )
        return int(row["id"]) if row else None

    def _backfill_tenant_links(self, connection: Any) -> None:
        """把历史账号和问卷挂到演示租户，避免升级后数据从工作台消失。"""

        tenant_id = self._default_tenant_id(connection)
        if tenant_id is None:
            return
        self._execute(
            connection,
            "UPDATE admin_users SET tenant_id = ? "
            "WHERE tenant_id IS NULL AND role <> 'platform_admin'",
            (tenant_id,),
        )
        self._execute(
            connection,
            "UPDATE wrapped_surveys SET tenant_id = ? WHERE tenant_id IS NULL",
            (tenant_id,),
        )
        team = self._fetchone(
            connection,
            "SELECT id FROM teams WHERE tenant_id = ? ORDER BY id LIMIT 1",
            (tenant_id,),
        )
        if not team:
            now = self._now()
            team_cursor = self._execute(
                connection,
                "INSERT INTO teams (tenant_id, name, description, created_at, created_by) "
                "VALUES (?, ?, ?, ?, (SELECT id FROM admin_users WHERE username = 'aixin'))",
                (tenant_id, "我的问卷", "历史问卷的默认个人空间。", now),
            )
            team_id = int(team_cursor.lastrowid)
        else:
            team_id = int(team["id"])
        self._execute(
            connection,
            "UPDATE teams SET name = '我的问卷', description = '个人账号的默认问卷组。' "
            "WHERE id = ? AND name = '默认问卷组'",
            (team_id,),
        )
        owner = self._fetchone(
            connection,
            "SELECT id FROM admin_users WHERE username = 'aixin'",
        )
        if owner:
            self._execute(
                connection,
                "UPDATE teams SET created_by = COALESCE(created_by, ?) WHERE id = ?",
                (owner["id"], team_id),
            )
            self._execute(
                connection,
                "INSERT INTO team_members "
                "(team_id, user_id, created_at, role, status, invited_by, invited_at, responded_at) "
                "SELECT ?, ?, ?, 'manager', 'accepted', ?, ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?)",
                (team_id, owner["id"], self._now(), owner["id"], self._now(), self._now(), team_id, owner["id"]),
            )

    def _ensure_columns(self, connection: Any, table: str, definitions: dict[str, str]) -> None:
        columns = self._table_columns(connection, table)
        for column, definition in definitions.items():
            if column not in columns:
                self._execute(connection, f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _table_columns(self, connection: Any, table: str) -> set[str]:
        if self.engine == "mysql":
            rows = self._fetchall(connection, f"SHOW COLUMNS FROM {table}")
            return {str(row["Field"]) for row in rows}
        return {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }

    def save_survey(
        self,
        survey: WrappedSurvey,
        *,
        status: str = "draft",
        prompt_version: str | None = None,
        model_name: str | None = None,
        generation_latency_ms: int | None = None,
        quality_score: float | None = None,
        tenant_id: int | None = None,
        team_id: int | None = None,
        created_by: int | None = None,
        moderation_status: str = "approved",
    ) -> int:
        if status not in SURVEY_STATUSES:
            raise ValueError("问卷状态无效。")
        with self._connection() as connection:
            tenant_id = tenant_id or self._default_tenant_id(connection)
            cursor = self._execute(
                connection,
                "INSERT INTO wrapped_surveys "
                "(survey_name, theme, source, created_at, payload, status, share_token, "
                "prompt_version, model_name, generation_latency_ms, quality_score, tenant_id, "
                "team_id, created_by, moderation_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    survey.survey_name,
                    survey.theme,
                    survey.source,
                    self._now(),
                    json.dumps(survey.to_dict(), ensure_ascii=False),
                    status,
                    self._new_share_token(connection),
                    prompt_version,
                    model_name,
                    generation_latency_ms,
                    quality_score,
                    tenant_id,
                    team_id,
                    created_by,
                    moderation_status,
                ),
            )
            return int(cursor.lastrowid)

    def update_survey_title(self, survey_id: int, survey_name: str) -> dict[str, Any] | None:
        """同步更新问卷标题摘要和完整 payload。"""

        with self._connection() as connection:
            row = self._fetchone(connection, "SELECT payload FROM wrapped_surveys WHERE id = ?", (survey_id,))
            if not row:
                return None
            payload = json.loads(row["payload"])
            payload["survey_name"] = survey_name
            self._execute(
                connection,
                "UPDATE wrapped_surveys SET survey_name = ?, payload = ?, version = version + 1 WHERE id = ?",
                (survey_name, json.dumps(payload, ensure_ascii=False), survey_id),
            )
        return self.get_survey(survey_id)

    def update_survey_content(
        self,
        survey_id: int,
        survey: WrappedSurvey,
    ) -> dict[str, Any] | None:
        """保存管理员编辑后的互动问卷，并递增问卷版本号。"""

        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT id FROM wrapped_surveys WHERE id = ?",
                (survey_id,),
            )
            if not row:
                return None
            self._execute(
                connection,
                "UPDATE wrapped_surveys SET survey_name = ?, theme = ?, payload = ?, "
                "version = version + 1, analysis_payload = NULL, ended_at = NULL, "
                "moderation_status = 'pending', moderation_note = NULL, reviewed_by = NULL, reviewed_at = NULL "
                "WHERE id = ?",
                (
                    survey.survey_name,
                    survey.theme,
                    json.dumps(survey.to_dict(), ensure_ascii=False),
                    survey_id,
                ),
            )
        return self.get_survey(survey_id)

    def update_survey_publication(
        self,
        survey_id: int,
        *,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """更新问卷发布状态。"""

        if status is not None and status not in SURVEY_STATUSES:
            raise ValueError("问卷状态无效。")
        with self._connection() as connection:
            row = self._fetchone(connection, "SELECT id FROM wrapped_surveys WHERE id = ?", (survey_id,))
            if not row:
                return None
            if status == "ended":
                self._execute(
                    connection,
                    "UPDATE wrapped_surveys SET status = COALESCE(?, status), ended_at = COALESCE(ended_at, ?) WHERE id = ?",
                    (status, self._now(), survey_id),
                )
            else:
                self._execute(
                    connection,
                    "UPDATE wrapped_surveys SET status = COALESCE(?, status) WHERE id = ?",
                    (status, survey_id),
                )
        return self.get_survey(survey_id)

    def archive_survey(
        self,
        survey_id: int,
        *,
        analysis: dict[str, Any],
    ) -> dict[str, Any] | None:
        """封存问卷并保存最终分析结果。"""

        ended_at = self._now()
        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT id FROM wrapped_surveys WHERE id = ?",
                (survey_id,),
            )
            if not row:
                return None
            self._execute(
                connection,
                "UPDATE wrapped_surveys SET status = 'archived', "
                "ended_at = COALESCE(ended_at, ?), analysis_payload = ? "
                "WHERE id = ?",
                (
                    ended_at,
                    json.dumps(analysis, ensure_ascii=False),
                    survey_id,
                ),
            )
        return self.get_survey(survey_id)

    def finish_survey(self, survey_id: int, analysis: dict[str, Any]) -> dict[str, Any] | None:
        """保存最终分析并将问卷状态切换为已结束。"""

        ended_at = self._now()
        with self._connection() as connection:
            self._execute(
                connection,
                "UPDATE wrapped_surveys SET status = 'ended', ended_at = COALESCE(ended_at, ?), analysis_payload = ? WHERE id = ?",
                (ended_at, json.dumps(analysis, ensure_ascii=False), survey_id),
            )
        return self.get_survey(survey_id)

    def save_response(
        self,
        response: SurveyResponse,
        survey_id: int | None = None,
        *,
        survey_version: int = 1,
        source: str = "public_link",
        duration_seconds: int | None = None,
        fingerprint_hash: str | None = None,
        browser_id_hash: str | None = None,
        ip_hash: str | None = None,
        access_code: str | None = None,
        is_test: bool = False,
    ) -> int:
        with self._connection() as connection:
            now = self._now()
            cursor = self._execute(
                connection,
                "INSERT INTO responses "
                "(survey_id, survey_version, result_type, created_at, submitted_at, payload, source, "
                "duration_seconds, fingerprint_hash, browser_id_hash, ip_hash, access_code, is_test) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    survey_id,
                    survey_version,
                    response.result_type,
                    now,
                    now,
                    json.dumps(response.to_dict(), ensure_ascii=False),
                    source,
                    duration_seconds,
                    fingerprint_hash,
                    browser_id_hash,
                    ip_hash,
                    access_code,
                    1 if is_test and source == "test" else 0,
                ),
            )
            return int(cursor.lastrowid)

    def has_duplicate_response(
        self,
        survey_id: int,
        *,
        fingerprint_hash: str | None = None,
        browser_id_hash: str | None = None,
        ip_hash: str | None = None,
        access_code: str | None = None,
    ) -> bool:
        checks = [
            ("fingerprint_hash", fingerprint_hash),
            ("browser_id_hash", browser_id_hash),
            ("access_code", access_code),
        ]
        if not any(value for _, value in checks) and ip_hash:
            checks.append(("ip_hash", ip_hash))
        conditions = ["survey_id = ?", "is_invalid = 0", "is_test = 0"]
        values: list[Any] = [survey_id]
        duplicate_parts: list[str] = []
        for column, value in checks:
            if value:
                duplicate_parts.append(f"{column} = ?")
                values.append(value)
        if not duplicate_parts:
            return False
        conditions.append("(" + " OR ".join(duplicate_parts) + ")")
        with self._connection() as connection:
            row = self._fetchone(
                connection,
                f"SELECT id FROM responses WHERE {' AND '.join(conditions)} LIMIT 1",
                tuple(values),
            )
        return bool(row)

    def mark_response_invalid(
        self,
        response_id: int,
        *,
        invalid: bool,
        reason: str = "",
    ) -> dict[str, Any] | None:
        invalid_at = self._now() if invalid else None
        with self._connection() as connection:
            self._execute(
                connection,
                "UPDATE responses SET is_invalid = ?, invalid_reason = ?, invalid_at = ? WHERE id = ?",
                (1 if invalid else 0, reason if invalid else None, invalid_at, response_id),
            )
        return self.get_response_row(response_id)

    def delete_response(self, response_id: int) -> bool:
        with self._connection() as connection:
            cursor = self._execute(connection, "DELETE FROM responses WHERE id = ?", (response_id,))
            return bool(cursor.rowcount)

    def list_surveys(
        self,
        limit: int = 50,
        status: str | None = None,
        deleted: bool | None = False,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection:
            conditions: list[str] = []
            values: list[Any] = []
            if tenant_id is not None and user_id is None:
                conditions.append("s.tenant_id = ?")
                values.append(tenant_id)
            if user_id is not None:
                conditions.append(
                    "(s.created_by = ? OR (s.created_by IS NULL AND s.tenant_id = ?) "
                    "OR EXISTS (SELECT 1 FROM survey_permissions p WHERE p.survey_id = s.id AND p.user_id = ?) "
                    "OR EXISTS (SELECT 1 FROM teams manager_team "
                    "WHERE manager_team.id = s.team_id AND manager_team.created_by = ?))"
                )
                values.extend([user_id, tenant_id if tenant_id is not None else -1, user_id, user_id])
            if status:
                conditions.append("s.status = ?")
                values.append(status)
            if deleted is True:
                conditions.append("s.deleted_at IS NOT NULL")
            elif deleted is False:
                conditions.append("s.deleted_at IS NULL")
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            values.append(limit)
            rows = self._fetchall(
                connection,
                "SELECT s.id, s.survey_name, s.theme, s.source, s.created_at, s.status, "
                "s.target_sample_count, s.ended_at, s.deleted_at, "
                "s.share_token, s.version, s.prompt_version, s.model_name, s.generation_latency_ms, "
                "s.quality_score, s.tenant_id, s.team_id, s.created_by, s.moderation_status, "
                "s.moderation_note, s.reviewed_at, t.name AS team_name, "
                "(SELECT COUNT(*) FROM responses r WHERE r.survey_id = s.id AND r.is_invalid = 0 AND r.is_test = 0) AS response_count "
                f"FROM wrapped_surveys s LEFT JOIN teams t ON t.id = s.team_id {where} ORDER BY s.id DESC LIMIT ?",
                tuple(values),
            )
        return rows

    def get_survey(self, survey_id: int) -> dict[str, Any] | None:
        """根据编号读取完整包装方案。"""

        with self._connection() as connection:
            row = self._fetchone(connection, "SELECT * FROM wrapped_surveys WHERE id = ?", (survey_id,))
        return self._decode_survey_row(row)

    def get_survey_by_share_token(self, share_token: str) -> dict[str, Any] | None:
        """根据分享令牌读取问卷，供公开分享页使用。"""

        with self._connection() as connection:
            row = self._fetchone(connection, "SELECT * FROM wrapped_surveys WHERE share_token = ?", (share_token,))
        return self._decode_survey_row(row)

    def _decode_survey_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        item["analysis"] = json.loads(item["analysis_payload"]) if item.get("analysis_payload") else None
        item.pop("start_at", None)
        item.pop("end_at", None)
        return item

    def move_survey_to_trash(self, survey_id: int) -> dict[str, Any] | None:
        """将问卷软删除到回收站，保留所有答卷和分析数据。"""

        with self._connection() as connection:
            self._execute(
                connection,
                "UPDATE wrapped_surveys SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                (self._now(), survey_id),
            )
        return self.get_survey(survey_id)

    def restore_survey(self, survey_id: int) -> dict[str, Any] | None:
        """从回收站恢复问卷。"""

        with self._connection() as connection:
            self._execute(
                connection,
                "UPDATE wrapped_surveys SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL",
                (survey_id,),
            )
        return self.get_survey(survey_id)

    def permanently_delete_survey(self, survey_id: int) -> bool:
        """永久删除问卷及其答卷，调用方需先经过后台权限校验。"""

        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT id FROM wrapped_surveys WHERE id = ? AND deleted_at IS NOT NULL",
                (survey_id,),
            )
            if not row:
                return False
            self._execute(connection, "DELETE FROM responses WHERE survey_id = ?", (survey_id,))
            self._execute(connection, "DELETE FROM generation_records WHERE survey_id = ?", (survey_id,))
            self._execute(connection, "DELETE FROM wrapped_surveys WHERE id = ?", (survey_id,))
        return True

    def list_responses(
        self,
        survey_id: int,
        *,
        include_invalid: bool = False,
        include_test: bool = False,
    ) -> list[SurveyResponse]:
        """按包装方案编号读取答卷，避免同名问卷的数据相互混入。"""

        conditions = ["survey_id = ?"]
        if not include_invalid:
            conditions.append("is_invalid = 0")
        if not include_test:
            conditions.append("is_test = 0")
        with self._connection() as connection:
            rows = self._fetchall(
                connection,
                f"SELECT payload FROM responses WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT 500",
                (survey_id,),
            )
        result: list[SurveyResponse] = []
        for row in rows:
            payload = json.loads(row["payload"])
            result.append(
                SurveyResponse(
                    wrapped_survey_name=payload["wrapped_survey_name"],
                    answers=payload["answers"],
                    result_type=payload["result_type"],
                    research_answers=payload["research_answers"],
                    dimension_scores=payload.get("dimension_scores", {}),
                    analysis=payload.get("analysis", {}),
                )
            )
        return result

    def list_response_rows(
        self,
        survey_id: int,
        *,
        include_invalid: bool = False,
        include_test: bool = False,
    ) -> list[dict[str, Any]]:
        """读取带编号、来源和时间的答卷明细，供后台和报表导出使用。"""

        conditions = ["survey_id = ?"]
        if not include_invalid:
            conditions.append("is_invalid = 0")
        if not include_test:
            conditions.append("is_test = 0")
        with self._connection() as connection:
            rows = self._fetchall(
                connection,
                "SELECT id, survey_version, result_type, created_at, submitted_at, payload, source, "
                "duration_seconds, is_test, is_invalid, invalid_reason "
                f"FROM responses WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT 500",
                (survey_id,),
            )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload"])
            result.append(
                {
                    "id": row["id"],
                    "survey_version": row.get("survey_version", 1),
                    "result_type": row["result_type"],
                    "created_at": row["created_at"],
                    "submitted_at": row.get("submitted_at"),
                    "source": row.get("source") or "public_link",
                    "duration_seconds": row.get("duration_seconds"),
                    "is_test": bool(row.get("is_test")),
                    "is_invalid": bool(row.get("is_invalid")),
                    "invalid_reason": row.get("invalid_reason"),
                    "answers": payload.get("answers", {}),
                    "research_answers": payload.get("research_answers", {}),
                    "dimension_scores": payload.get("dimension_scores", {}),
                    "analysis": payload.get("analysis", {}),
                }
            )
        return result

    def get_response_row(self, response_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = self._fetchone(connection, "SELECT * FROM responses WHERE id = ?", (response_id,))
        if not row:
            return None
        payload = json.loads(row["payload"])
        row["answers"] = payload.get("answers", {})
        row["research_answers"] = payload.get("research_answers", {})
        row["dimension_scores"] = payload.get("dimension_scores", {})
        return row

    def record_generation(
        self,
        *,
        survey_id: int | None,
        tenant_id: int | None = None,
        created_by: int | None = None,
        prompt_version: str,
        model_name: str,
        latency_ms: int,
        token_estimate: int,
        cost_estimate: float,
        quality_score: float,
        retry_count: int,
        status: str,
        error_message: str = "",
    ) -> int:
        with self._connection() as connection:
            cursor = self._execute(
                connection,
                "INSERT INTO generation_records "
                "(survey_id, tenant_id, created_by, prompt_version, model_name, latency_ms, token_estimate, cost_estimate, "
                "quality_score, retry_count, status, error_message, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    survey_id,
                    tenant_id,
                    created_by,
                    prompt_version,
                    model_name,
                    latency_ms,
                    token_estimate,
                    cost_estimate,
                    quality_score,
                    retry_count,
                    status,
                    error_message[:500],
                    self._now(),
                ),
            )
            return int(cursor.lastrowid)

    def list_generation_records(self, survey_id: int | None = None) -> list[dict[str, Any]]:
        with self._connection() as connection:
            if survey_id is None:
                return self._fetchall(connection, "SELECT * FROM generation_records ORDER BY id DESC LIMIT 100")
            return self._fetchall(
                connection,
                "SELECT * FROM generation_records WHERE survey_id = ? ORDER BY id DESC LIMIT 20",
                (survey_id,),
            )

    def authenticate_admin(
        self,
        username: str,
        password: str,
        *,
        ip_hash: str | None = None,
        user_agent: str | None = None,
        required_role: str | None = None,
        excluded_role: str | None = None,
    ) -> dict[str, Any] | None:
        username = username.strip()
        if not username or self._is_login_limited(username, ip_hash):
            return None
        with self._connection() as connection:
            user = self._fetchone(
                connection,
                "SELECT * FROM admin_users WHERE username = ? AND is_active = 1",
                (username,),
            )
            if not user or not verify_password(password, user["password_hash"]):
                self._execute(
                    connection,
                    "INSERT INTO login_failures (username, ip_hash, failed_at) VALUES (?, ?, ?)",
                    (username, ip_hash, self._now()),
                )
                return None
            if required_role and user["role"] != required_role:
                return None
            if excluded_role and user["role"] == excluded_role:
                return None
            token = secrets.token_urlsafe(32)
            now = datetime.now()
            self._execute(
                connection,
                "INSERT INTO admin_sessions "
                "(admin_id, token_hash, expires_at, created_at, last_seen_at, user_agent, ip_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user["id"],
                    hash_token(token),
                    (now + timedelta(hours=ADMIN_SESSION_HOURS)).isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"),
                    (user_agent or "")[:255],
                    ip_hash,
                ),
            )
            tenant = (
                self._fetchone(
                    connection,
                    "SELECT id, name, token_balance, token_used FROM tenants WHERE id = ?",
                    (user.get("tenant_id"),),
                )
                if user.get("tenant_id")
                else None
            )
        return {
            "token": token,
            "admin_id": int(user["id"]),
            "role": user["role"],
            "username": user["username"],
            "display_name": user.get("display_name") or user["username"],
            "tenant_id": tenant["id"] if tenant else None,
            "tenant_name": tenant["name"] if tenant else None,
            "token_balance": tenant["token_balance"] if tenant else None,
            "token_used": tenant["token_used"] if tenant else None,
            "expires_in": ADMIN_SESSION_HOURS * 3600,
        }

    def get_active_user_role(self, username: str) -> str | None:
        username = username.strip()
        if not username:
            return None
        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT role FROM admin_users WHERE username = ? AND is_active = 1",
                (username,),
            )
        return str(row["role"]) if row else None

    def get_admin_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        now = self._now()
        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT s.id AS session_id, s.admin_id, s.expires_at, u.username, u.role "
                ", u.tenant_id, u.display_name, t.name AS tenant_name, "
                "t.token_balance, t.token_used "
                "FROM admin_sessions s JOIN admin_users u ON u.id = s.admin_id "
                "LEFT JOIN tenants t ON t.id = u.tenant_id "
                "WHERE s.token_hash = ? AND u.is_active = 1",
                (hash_token(token),),
            )
            if not row or str(row["expires_at"]) <= now:
                return None
            self._execute(connection, "UPDATE admin_sessions SET last_seen_at = ? WHERE id = ?", (now, row["session_id"]))
        return row

    def change_admin_password(self, admin_id: int, old_password: str, new_password: str) -> bool:
        with self._connection() as connection:
            user = self._fetchone(connection, "SELECT * FROM admin_users WHERE id = ?", (admin_id,))
            if not user or not verify_password(old_password, user["password_hash"]):
                return False
            self._execute(
                connection,
                "UPDATE admin_users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(new_password), self._now(), admin_id),
            )
        return True

    def list_admin_users(self, tenant_id: int | None = None) -> list[dict[str, Any]]:
        """读取管理员账号摘要，不返回密码哈希。"""

        with self._connection() as connection:
            condition = " WHERE tenant_id = ?" if tenant_id is not None else ""
            params = (tenant_id,) if tenant_id is not None else ()
            return self._fetchall(
                connection,
                "SELECT id, username, role, tenant_id, display_name, email, is_active, created_at, updated_at "
                f"FROM admin_users{condition} ORDER BY id",
                params,
            )

    def create_admin_user(
        self,
        username: str,
        password: str,
        role: str,
        tenant_id: int | None = None,
        display_name: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        """创建企业成员账号，保留旧的管理员账号创建接口。"""

        username = username.strip()
        if not username:
            raise ValueError("账号不能为空。")
        if role not in {"admin", "viewer", "survey_admin", "member"}:
            raise ValueError("账号角色无效。")
        now = self._now()
        with self._connection() as connection:
            if tenant_id is None:
                tenant_id = self._default_tenant_id(connection)
            exists = self._fetchone(
                connection,
                "SELECT id FROM admin_users WHERE username = ?",
                (username,),
            )
            if exists:
                raise ValueError("账号名已存在。")
            cursor = self._execute(
                connection,
                "INSERT INTO admin_users "
                "(username, password_hash, role, tenant_id, display_name, email, is_active, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    username,
                    hash_password(password),
                    role,
                    tenant_id,
                    display_name or username,
                    email,
                    now,
                    now,
                ),
            )
            user_id = int(cursor.lastrowid)
        return {
            "id": user_id,
            "username": username,
            "role": role,
            "tenant_id": tenant_id,
            "display_name": display_name or username,
            "email": email,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

    def register_tenant(
        self,
        *,
        username: str,
        password: str,
        company_name: str = "",
        email: str = "",
    ) -> dict[str, Any]:
        """注册一个个人工作区，并创建默认问卷组。"""

        username = username.strip()
        company_name = " ".join(company_name.split()).strip()
        email = email.strip()
        if not username:
            raise ValueError("账号不能为空。")
        workspace_name = company_name or f"{username} 的个人工作区"
        if len(username) > 80 or len(workspace_name) > 160:
            raise ValueError("账号或工作区名称过长。")
        now = self._now()
        with self._connection() as connection:
            exists = self._fetchone(
                connection,
                "SELECT id FROM admin_users WHERE username = ?",
                (username,),
            )
            if exists:
                raise ValueError("账号名已存在。")
            slug_base = _slugify(company_name)
            if not company_name:
                slug_base = _slugify(username)
            slug = slug_base
            while self._fetchone(connection, "SELECT id FROM tenants WHERE slug = ?", (slug,)):
                slug = f"{slug_base}-{secrets.token_hex(2)}"
            default_tokens = self.get_platform_setting_int(
                "default_registration_tokens",
                connection=connection,
                default=20000,
            )
            tenant_cursor = self._execute(
                connection,
                "INSERT INTO tenants "
                "(name, slug, status, plan, token_balance, token_used, created_at, updated_at) "
                "VALUES (?, ?, 'active', 'starter', ?, 0, ?, ?)",
                (workspace_name, slug, default_tokens, now, now),
            )
            tenant_id = int(tenant_cursor.lastrowid)
            user_cursor = self._execute(
                connection,
                "INSERT INTO admin_users "
                "(username, password_hash, role, tenant_id, display_name, email, is_active, created_at, updated_at) "
                "VALUES (?, ?, 'owner', ?, ?, ?, 1, ?, ?)",
                (username, hash_password(password), tenant_id, username, email, now, now),
            )
            user_id = int(user_cursor.lastrowid)
            team_cursor = self._execute(
                connection,
                "INSERT INTO teams (tenant_id, name, description, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (tenant_id, "我的问卷", "个人账号的默认问卷组。", now, user_id),
            )
            team_id = int(team_cursor.lastrowid)
            self._execute(
                connection,
                "INSERT INTO team_members "
                "(team_id, user_id, created_at, role, status, invited_by, invited_at, responded_at) "
                "VALUES (?, ?, ?, 'manager', 'accepted', ?, ?, ?)",
                (team_id, user_id, now, user_id, now, now),
            )
        return {
            "tenant": {
                "id": tenant_id,
                "name": workspace_name,
                "slug": slug,
                "plan": "starter",
                "token_balance": default_tokens,
                "token_used": 0,
                "created_at": now,
            },
            "user": {
                "id": user_id,
                "username": username,
                "display_name": username,
                "email": email,
                "role": "owner",
                "tenant_id": tenant_id,
            },
            "workspace": {
                "id": tenant_id,
                "name": workspace_name,
                "token_balance": default_tokens,
            },
            "team": {"id": team_id, "name": "我的问卷"},
        }

    def get_tenant(self, tenant_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._fetchone(connection, "SELECT * FROM tenants WHERE id = ?", (tenant_id,))

    def list_teams(self, tenant_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT t.id, t.tenant_id, t.name, t.description, t.created_at, "
                "(SELECT COUNT(*) FROM team_members m WHERE m.team_id = t.id) AS member_count, "
                "(SELECT COUNT(*) FROM wrapped_surveys s WHERE s.team_id = t.id AND s.deleted_at IS NULL) AS survey_count "
                "FROM teams t WHERE t.tenant_id = ? ORDER BY t.id",
                (tenant_id,),
            )

    def list_user_teams(self, user_id: int, tenant_id: int | None = None) -> list[dict[str, Any]]:
        """读取当前账号创建或已接受加入的问卷组。"""

        conditions = ["(t.created_by = ? OR tm.user_id IS NOT NULL)"]
        query_values: list[Any] = [user_id]
        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT t.id, t.tenant_id, t.name, t.description, t.created_at, t.created_by, "
                "CASE WHEN t.created_by = ? THEN 'manager' ELSE COALESCE(tm.role, 'viewer') END AS member_role, "
                "(SELECT COUNT(*) FROM team_members m WHERE m.team_id = t.id AND m.status = 'accepted') AS member_count, "
                "(SELECT COUNT(*) FROM wrapped_surveys s WHERE s.team_id = t.id AND s.deleted_at IS NULL) AS survey_count "
                "FROM teams t "
                "LEFT JOIN team_members tm ON tm.team_id = t.id AND tm.user_id = ? AND tm.status = 'accepted' "
                f"WHERE {' AND '.join(conditions)} ORDER BY t.id DESC",
                tuple([user_id, user_id] + query_values),
            )

    def create_team(
        self,
        tenant_id: int,
        name: str,
        description: str,
        created_by: int,
    ) -> dict[str, Any]:
        name = " ".join(name.split()).strip()
        if not name:
            raise ValueError("问卷组名称不能为空。")
        if len(name) > 120:
            raise ValueError("问卷组名称不能超过 120 个字符。")
        now = self._now()
        with self._connection() as connection:
            exists = self._fetchone(
                connection,
                "SELECT id FROM teams WHERE tenant_id = ? AND name = ?",
                (tenant_id, name),
            )
            if exists:
                raise ValueError("同一企业下不能创建同名问卷组。")
            cursor = self._execute(
                connection,
                "INSERT INTO teams (tenant_id, name, description, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (tenant_id, name, description.strip()[:500], now, created_by),
            )
            team_id = int(cursor.lastrowid)
            self._execute(
                connection,
                "INSERT INTO team_members "
                "(team_id, user_id, created_at, role, status, invited_by, invited_at, responded_at) "
                "VALUES (?, ?, ?, 'manager', 'accepted', ?, ?, ?)",
                (team_id, created_by, now, created_by, now, now),
            )
        return {
            "id": team_id,
            "tenant_id": tenant_id,
            "name": name,
            "description": description.strip()[:500],
            "created_at": now,
            "created_by": created_by,
            "member_role": "manager",
            "member_count": 1,
            "survey_count": 0,
        }

    def get_team_role(self, team_id: int, user_id: int) -> str | None:
        with self._connection() as connection:
            team = self._fetchone(
                connection,
                "SELECT created_by FROM teams WHERE id = ?",
                (team_id,),
            )
            if not team:
                return None
            if int(team["created_by"] or 0) == user_id:
                return "manager"
            member = self._fetchone(
                connection,
                "SELECT role FROM team_members "
                "WHERE team_id = ? AND user_id = ? AND status = 'accepted'",
                (team_id, user_id),
            )
        return str(member["role"]) if member else None

    def list_team_members(self, team_id: int, owner_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            team = self._fetchone(
                connection,
                "SELECT id FROM teams WHERE id = ? AND created_by = ?",
                (team_id, owner_id),
            )
            if not team:
                return []
            return self._fetchall(
                connection,
                "SELECT u.id, u.username, u.display_name, u.email, u.is_active, "
                "m.role AS member_role, m.status, m.created_at, m.responded_at "
                "FROM team_members m JOIN admin_users u ON u.id = m.user_id "
                "WHERE m.team_id = ? AND m.status = 'accepted' ORDER BY "
                "CASE WHEN m.role = 'manager' THEN 0 ELSE 1 END, m.created_at",
                (team_id,),
            )

    def list_team_invitations(self, team_id: int, owner_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            team = self._fetchone(
                connection,
                "SELECT id FROM teams WHERE id = ? AND created_by = ?",
                (team_id, owner_id),
            )
            if not team:
                return []
            return self._fetchall(
                connection,
                "SELECT i.id, i.team_id, i.invitee_id, i.permission, i.status, i.created_at, "
                "i.responded_at, u.username AS invitee_username, u.display_name AS invitee_name "
                "FROM team_invitations i JOIN admin_users u ON u.id = i.invitee_id "
                "WHERE i.team_id = ? ORDER BY CASE WHEN i.status = 'pending' THEN 0 ELSE 1 END, i.id DESC",
                (team_id,),
            )

    def create_team_invitation(
        self,
        team_id: int,
        inviter_id: int,
        invitee_username: str,
        permission: str,
    ) -> dict[str, Any]:
        permission = permission.strip().lower()
        if permission not in {"viewer", "editor"}:
            raise ValueError("成员权限只能是 viewer 或 editor。")
        invitee_username = invitee_username.strip()
        if not invitee_username:
            raise ValueError("请输入已注册用户的账号或邮箱。")
        now = self._now()
        with self._connection() as connection:
            team = self._fetchone(
                connection,
                "SELECT id, name FROM teams WHERE id = ? AND created_by = ?",
                (team_id, inviter_id),
            )
            if not team:
                raise ValueError("只有问卷组创建者可以邀请成员。")
            invitee = self._fetchone(
                connection,
                "SELECT id, username, display_name, email FROM admin_users "
                "WHERE is_active = 1 AND (username = ? OR email = ?)",
                (invitee_username, invitee_username),
            )
            if not invitee:
                raise ValueError("只能邀请已经注册且处于启用状态的用户。")
            if int(invitee["id"]) == inviter_id:
                raise ValueError("不能邀请自己加入问卷组。")
            member = self._fetchone(
                connection,
                "SELECT status FROM team_members WHERE team_id = ? AND user_id = ?",
                (team_id, invitee["id"]),
            )
            if member and member["status"] == "accepted":
                raise ValueError("该用户已经是问卷组成员。")
            pending = self._fetchone(
                connection,
                "SELECT id FROM team_invitations "
                "WHERE team_id = ? AND invitee_id = ? AND status = 'pending'",
                (team_id, invitee["id"]),
            )
            if pending:
                raise ValueError("该用户已有一条待处理邀请。")
            cursor = self._execute(
                connection,
                "INSERT INTO team_invitations "
                "(team_id, invitee_id, invited_by, permission, status, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (team_id, invitee["id"], inviter_id, permission, now),
            )
            invitation_id = int(cursor.lastrowid)
        return {
            "id": invitation_id,
            "team_id": team_id,
            "team_name": team["name"],
            "invitee_id": int(invitee["id"]),
            "invitee_username": invitee["username"],
            "invitee_name": invitee.get("display_name") or invitee["username"],
            "permission": permission,
            "status": "pending",
            "created_at": now,
        }

    def list_user_invitations(self, user_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT i.id, i.team_id, i.permission, i.status, i.created_at, i.responded_at, "
                "t.name AS team_name, inviter.username AS invited_by_username, "
                "inviter.display_name AS invited_by_name "
                "FROM team_invitations i JOIN teams t ON t.id = i.team_id "
                "LEFT JOIN admin_users inviter ON inviter.id = i.invited_by "
                "WHERE i.invitee_id = ? ORDER BY CASE WHEN i.status = 'pending' THEN 0 ELSE 1 END, i.id DESC",
                (user_id,),
            )

    def respond_team_invitation(
        self,
        invitation_id: int,
        user_id: int,
        *,
        accepted: bool,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._connection() as connection:
            invitation = self._fetchone(
                connection,
                "SELECT * FROM team_invitations "
                "WHERE id = ? AND invitee_id = ? AND status = 'pending'",
                (invitation_id, user_id),
            )
            if not invitation:
                return None
            status = "accepted" if accepted else "rejected"
            self._execute(
                connection,
                "UPDATE team_invitations SET status = ?, responded_at = ? WHERE id = ?",
                (status, now, invitation_id),
            )
            if accepted:
                member = self._fetchone(
                    connection,
                    "SELECT team_id FROM team_members WHERE team_id = ? AND user_id = ?",
                    (invitation["team_id"], user_id),
                )
                if member:
                    self._execute(
                        connection,
                        "UPDATE team_members SET role = ?, status = 'accepted', invited_by = ?, "
                        "invited_at = ?, responded_at = ? WHERE team_id = ? AND user_id = ?",
                        (
                            invitation["permission"],
                            invitation["invited_by"],
                            invitation["created_at"],
                            now,
                            now,
                            invitation["team_id"],
                            user_id,
                        ),
                    )
                else:
                    self._execute(
                        connection,
                        "INSERT INTO team_members "
                        "(team_id, user_id, created_at, role, status, invited_by, invited_at, responded_at) "
                        "VALUES (?, ?, ?, ?, 'accepted', ?, ?, ?)",
                        (
                            invitation["team_id"],
                            user_id,
                            now,
                            invitation["permission"],
                            invitation["invited_by"],
                            invitation["created_at"],
                            now,
                        ),
                    )
            return self._fetchone(
                connection,
                "SELECT i.id, i.team_id, i.permission, i.status, i.created_at, i.responded_at, "
                "t.name AS team_name FROM team_invitations i JOIN teams t ON t.id = i.team_id "
                "WHERE i.id = ?",
                (invitation_id,),
            )

    def get_survey_permission(
        self,
        survey_id: int,
        user_id: int,
        tenant_id: int | None = None,
    ) -> str | None:
        with self._connection() as connection:
            survey = self._fetchone(
                connection,
                "SELECT created_by, tenant_id, team_id FROM wrapped_surveys WHERE id = ?",
                (survey_id,),
            )
            if not survey:
                return None
            if int(survey["created_by"] or 0) == user_id:
                return "owner"
            if survey["created_by"] is None and tenant_id is not None and survey["tenant_id"] == tenant_id:
                return "owner"
            if survey["team_id"]:
                team = self._fetchone(
                    connection,
                    "SELECT created_by FROM teams WHERE id = ?",
                    (survey["team_id"],),
                )
                if team and int(team["created_by"] or 0) == user_id:
                    return "manager"
            permission = self._fetchone(
                connection,
                "SELECT permission FROM survey_permissions WHERE survey_id = ? AND user_id = ?",
                (survey_id, user_id),
            )
        return str(permission["permission"]) if permission else None

    def can_manage_survey_access(
        self,
        survey_id: int,
        user_id: int,
        tenant_id: int | None = None,
    ) -> bool:
        return self.get_survey_permission(survey_id, user_id, tenant_id) in {"owner", "manager"}

    def list_survey_permissions(
        self,
        survey_id: int,
        owner_id: int,
        tenant_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if not self.can_manage_survey_access(survey_id, owner_id, tenant_id):
            return []
        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT p.survey_id, p.user_id, p.permission, p.created_at, p.updated_at, "
                "u.username, u.display_name, u.email, u.is_active "
                "FROM survey_permissions p JOIN admin_users u ON u.id = p.user_id "
                "WHERE p.survey_id = ? ORDER BY p.user_id",
                (survey_id,),
            )

    def set_survey_permission(
        self,
        survey_id: int,
        owner_id: int,
        target_user_id: int,
        permission: str | None,
        tenant_id: int | None = None,
    ) -> dict[str, Any] | None:
        if not self.can_manage_survey_access(survey_id, owner_id, tenant_id):
            raise ValueError("只有问卷创建者或问卷组管理者可以调整访问权限。")
        if target_user_id == owner_id:
            raise ValueError("问卷创建者不需要额外设置访问权限。")
        if permission not in {None, "viewer", "editor"}:
            raise ValueError("问卷权限只能是 viewer 或 editor。")
        now = self._now()
        with self._connection() as connection:
            user = self._fetchone(
                connection,
                "SELECT id, username, display_name, email FROM admin_users WHERE id = ? AND is_active = 1",
                (target_user_id,),
            )
            if not user:
                raise ValueError("被授权用户不存在或已停用。")
            current = self._fetchone(
                connection,
                "SELECT survey_id FROM survey_permissions WHERE survey_id = ? AND user_id = ?",
                (survey_id, target_user_id),
            )
            if permission is None:
                if current:
                    self._execute(
                        connection,
                        "DELETE FROM survey_permissions WHERE survey_id = ? AND user_id = ?",
                        (survey_id, target_user_id),
                    )
                return {
                    "survey_id": survey_id,
                    "user_id": target_user_id,
                    "permission": None,
                    "username": user["username"],
                    "display_name": user.get("display_name") or user["username"],
                }
            if current:
                self._execute(
                    connection,
                    "UPDATE survey_permissions SET permission = ?, granted_by = ?, updated_at = ? "
                    "WHERE survey_id = ? AND user_id = ?",
                    (permission, owner_id, now, survey_id, target_user_id),
                )
            else:
                self._execute(
                    connection,
                    "INSERT INTO survey_permissions "
                    "(survey_id, user_id, permission, granted_by, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (survey_id, target_user_id, permission, owner_id, now, now),
                )
        return {
            "survey_id": survey_id,
            "user_id": target_user_id,
            "permission": permission,
            "username": user["username"],
            "display_name": user.get("display_name") or user["username"],
        }

    def get_billing_overview(self, tenant_id: int, user_id: int | None = None) -> dict[str, Any]:
        with self._connection() as connection:
            tenant = self._fetchone(connection, "SELECT * FROM tenants WHERE id = ?", (tenant_id,))
            requests = self._fetchone(
                connection,
                "SELECT COUNT(*) AS count FROM token_requests "
                "WHERE tenant_id = ? AND status = 'pending' "
                + ("AND requested_by = ?" if user_id is not None else ""),
                (tenant_id, user_id) if user_id is not None else (tenant_id,),
            )
            usage_condition = "tenant_id = ?"
            usage_values: tuple[Any, ...] = (tenant_id,)
            if user_id is not None:
                # API 用量按登录账号隔离，不能用工作区作为历史记录的兜底条件。
                usage_condition = "created_by = ?"
                usage_values = (user_id,)
            usage = self._fetchall(
                connection,
                "SELECT id, survey_id, "
                "(SELECT survey_name FROM wrapped_surveys WHERE id = generation_records.survey_id) AS survey_name, "
                "prompt_version, model_name, token_estimate, status, created_at "
                f"FROM generation_records WHERE {usage_condition} "
                "ORDER BY id DESC LIMIT 8",
                usage_values,
            )
            used_row = self._fetchone(
                connection,
                "SELECT COALESCE(SUM(token_estimate), 0) AS total, "
                "COALESCE(SUM(CASE WHEN created_at LIKE ? THEN token_estimate ELSE 0 END), 0) AS today, "
                "COUNT(*) AS calls, COALESCE(AVG(NULLIF(latency_ms, 0)), 0) AS average_latency "
                f"FROM generation_records WHERE status = 'success' AND {usage_condition}",
                (f"{datetime.now().date().isoformat()}%", *usage_values),
            )
        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant["name"] if tenant else "未命名租户",
            "balance": int(tenant["token_balance"] if tenant else 0),
            "used": int(used_row["total"] if used_row else 0),
            "today_used": int(used_row["today"] if used_row else 0),
            "api_calls": int(used_row["calls"] if used_row else 0),
            "average_latency_ms": round(float(used_row["average_latency"] if used_row else 0), 1),
            "pending_requests": int(requests["count"] if requests else 0),
            "recent_usage": usage,
        }

    def consume_tokens(self, tenant_id: int, amount: int) -> bool:
        amount = max(0, int(amount))
        if amount == 0:
            return True
        with self._connection() as connection:
            cursor = self._execute(
                connection,
                "UPDATE tenants SET token_balance = token_balance - ?, token_used = token_used + ?, "
                "updated_at = ? WHERE id = ? AND token_balance >= ? AND status = 'active'",
                (amount, amount, self._now(), tenant_id, amount),
            )
            return bool(cursor.rowcount)

    def refund_tokens(self, tenant_id: int, amount: int) -> None:
        amount = max(0, int(amount))
        if amount == 0:
            return
        with self._connection() as connection:
            clamp_function = "GREATEST" if self.engine == "mysql" else "MAX"
            self._execute(
                connection,
                f"UPDATE tenants SET token_balance = token_balance + ?, token_used = {clamp_function}(0, token_used - ?), "
                "updated_at = ? WHERE id = ?",
                (amount, amount, self._now(), tenant_id),
            )

    def create_token_request(self, tenant_id: int, requested_by: int, amount: int, reason: str) -> dict[str, Any]:
        amount = int(amount)
        if amount < 100:
            raise ValueError("申请额度至少为 100 Token。")
        if amount > 10_000_000:
            raise ValueError("单次申请额度不能超过 10,000,000 Token。")
        now = self._now()
        with self._connection() as connection:
            cursor = self._execute(
                connection,
                "INSERT INTO token_requests "
                "(tenant_id, requested_by, amount, reason, status, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (tenant_id, requested_by, amount, reason.strip()[:500], now),
            )
            request_id = int(cursor.lastrowid)
        return {
            "id": request_id,
            "tenant_id": tenant_id,
            "requested_by": requested_by,
            "amount": amount,
            "reason": reason.strip()[:500],
            "status": "pending",
            "created_at": now,
        }

    def list_token_requests(
        self,
        tenant_id: int | None = None,
        requested_by: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection:
            conditions = []
            values: list[Any] = []
            if tenant_id is not None:
                conditions.append("r.tenant_id = ?")
                values.append(tenant_id)
            if requested_by is not None:
                conditions.append("r.requested_by = ?")
                values.append(requested_by)
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            return self._fetchall(
                connection,
                "SELECT r.*, t.name AS tenant_name, u.username AS requested_by_name "
                f"FROM token_requests r LEFT JOIN tenants t ON t.id = r.tenant_id "
                f"LEFT JOIN admin_users u ON u.id = r.requested_by {where} "
                "ORDER BY r.id DESC LIMIT 100",
                tuple(values),
            )

    def review_token_request(
        self,
        request_id: int,
        reviewer_id: int,
        *,
        approved: bool,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT * FROM token_requests WHERE id = ? AND status = 'pending'",
                (request_id,),
            )
            if not row:
                return None
            status = "approved" if approved else "rejected"
            self._execute(
                connection,
                "UPDATE token_requests SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
                (status, reviewer_id, now, request_id),
            )
            if approved:
                self._execute(
                    connection,
                    "UPDATE tenants SET token_balance = token_balance + ?, updated_at = ? WHERE id = ?",
                    (row["amount"], now, row["tenant_id"]),
                )
            return self._fetchone(connection, "SELECT * FROM token_requests WHERE id = ?", (request_id,))

    def get_platform_setting(
        self,
        key: str,
        *,
        connection: Any | None = None,
        default: str = "",
    ) -> str:
        if connection is not None:
            row = self._fetchone(
                connection,
                "SELECT setting_value FROM platform_settings WHERE setting_key = ?",
                (key,),
            )
            return str(row["setting_value"]) if row else default
        with self._connection() as owned_connection:
            row = self._fetchone(
                owned_connection,
                "SELECT setting_value FROM platform_settings WHERE setting_key = ?",
                (key,),
            )
            return str(row["setting_value"]) if row else default

    def get_platform_setting_int(
        self,
        key: str,
        *,
        connection: Any | None = None,
        default: int = 0,
    ) -> int:
        try:
            return int(self.get_platform_setting(key, connection=connection, default=str(default)))
        except (TypeError, ValueError):
            return default

    def list_platform_settings(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT setting_key, setting_value, updated_at FROM platform_settings ORDER BY setting_key",
            )

    def update_platform_setting(self, key: str, value: str) -> dict[str, Any]:
        now = self._now()
        with self._connection() as connection:
            if self.engine == "mysql":
                self._execute(
                    connection,
                    "INSERT INTO platform_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?) "
                    "ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value), updated_at = VALUES(updated_at)",
                    (key, value.strip(), now),
                )
            else:
                self._execute(
                    connection,
                    "INSERT INTO platform_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value, updated_at = excluded.updated_at",
                    (key, value.strip(), now),
                )
            return self._fetchone(
                connection,
                "SELECT setting_key, setting_value, updated_at FROM platform_settings WHERE setting_key = ?",
                (key,),
            ) or {"setting_key": key, "setting_value": value.strip(), "updated_at": now}

    def platform_overview(self) -> dict[str, int]:
        today_prefix = f"{datetime.now().date().isoformat()}%"
        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT "
                "(SELECT COUNT(*) FROM tenants WHERE status = 'active') AS tenant_count, "
                "(SELECT COUNT(*) FROM admin_users WHERE is_active = 1 AND role <> 'platform_admin') AS user_count, "
                "(SELECT COUNT(*) FROM admin_users WHERE role <> 'platform_admin') AS account_count, "
                "(SELECT COUNT(*) FROM wrapped_surveys WHERE deleted_at IS NULL) AS survey_count, "
                "(SELECT COUNT(*) FROM responses WHERE is_invalid = 0 AND is_test = 0) AS response_count, "
                "(SELECT COALESCE(SUM(token_estimate), 0) FROM generation_records "
                "WHERE status = 'success') AS token_used, "
                "(SELECT COALESCE(SUM(token_estimate), 0) FROM generation_records "
                "WHERE status = 'success' AND created_at LIKE ?) AS token_used_today, "
                "(SELECT COUNT(*) FROM generation_records WHERE status = 'success') AS api_call_count, "
                "(SELECT COALESCE(AVG(NULLIF(latency_ms, 0)), 0) FROM generation_records "
                "WHERE status = 'success') AS average_latency_ms, "
                "(SELECT COUNT(*) FROM token_requests WHERE status = 'pending') AS pending_token_requests, "
                "(SELECT COUNT(*) FROM wrapped_surveys WHERE deleted_at IS NULL AND moderation_status = 'pending') AS pending_reviews",
                (today_prefix,),
            )
        return {key: int(value or 0) for key, value in (row or {}).items()}

    def list_platform_tenants(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT t.*, "
                "(SELECT COUNT(*) FROM admin_users u WHERE u.tenant_id = t.id AND u.is_active = 1) AS user_count, "
                "(SELECT COUNT(*) FROM wrapped_surveys s WHERE s.tenant_id = t.id AND s.deleted_at IS NULL) AS survey_count "
                "FROM tenants t ORDER BY t.id DESC",
            )

    def list_platform_users(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT u.id, u.username, u.display_name, u.email, u.role, u.is_active, "
                "u.tenant_id, u.created_at, u.updated_at, t.name AS workspace_name, "
                "COALESCE((SELECT SUM(g.token_estimate) FROM generation_records g "
                "WHERE g.created_by = u.id AND g.status = 'success'), 0) AS token_used, "
                "(SELECT COUNT(*) FROM wrapped_surveys s WHERE s.deleted_at IS NULL AND "
                "(s.created_by = u.id OR (s.created_by IS NULL AND s.tenant_id = u.tenant_id))) AS survey_count, "
                "(SELECT COUNT(*) FROM responses r JOIN wrapped_surveys s ON s.id = r.survey_id "
                "WHERE s.deleted_at IS NULL AND r.is_invalid = 0 AND r.is_test = 0 AND "
                "(s.created_by = u.id OR (s.created_by IS NULL AND s.tenant_id = u.tenant_id))) AS response_count, "
                "(SELECT COUNT(*) FROM generation_records g "
                "WHERE g.created_by = u.id AND g.status = 'success') AS api_call_count "
                "FROM admin_users u LEFT JOIN tenants t ON t.id = u.tenant_id "
                "ORDER BY u.id DESC",
            )

    def update_user_status(self, user_id: int, is_active: bool) -> dict[str, Any] | None:
        with self._connection() as connection:
            self._execute(
                connection,
                "UPDATE admin_users SET is_active = ?, updated_at = ? WHERE id = ?",
                (1 if is_active else 0, self._now(), user_id),
            )
            return self._fetchone(
                connection,
                "SELECT u.id, u.username, u.display_name, u.email, u.role, u.is_active, "
                "u.tenant_id, u.created_at, u.updated_at, t.name AS tenant_name "
                "FROM admin_users u LEFT JOIN tenants t ON t.id = u.tenant_id "
                "WHERE u.id = ?",
                (user_id,),
            )

    def list_platform_reviews(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT s.id, s.survey_name, s.theme, s.status, s.moderation_status, "
                "s.moderation_note, s.created_at, s.reviewed_at, t.name AS workspace_name, "
                "u.username AS created_by_name "
                "FROM wrapped_surveys s LEFT JOIN tenants t ON t.id = s.tenant_id "
                "LEFT JOIN admin_users u ON u.id = s.created_by "
                "WHERE s.deleted_at IS NULL ORDER BY "
                "CASE s.moderation_status WHEN 'pending' THEN 0 WHEN 'rejected' THEN 1 ELSE 2 END, s.id DESC "
                "LIMIT 100",
            )

    def review_survey(
        self,
        survey_id: int,
        reviewer_id: int,
        *,
        approved: bool,
        note: str = "",
    ) -> dict[str, Any] | None:
        status = "approved" if approved else "rejected"
        with self._connection() as connection:
            self._execute(
                connection,
                "UPDATE wrapped_surveys SET moderation_status = ?, moderation_note = ?, reviewed_by = ?, reviewed_at = ? "
                "WHERE id = ?",
                (status, note.strip()[:500], reviewer_id, self._now(), survey_id),
            )
        return self.get_survey(survey_id)

    def log_operation(
        self,
        *,
        admin_id: int | None,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        detail: dict[str, Any] | None = None,
        ip_hash: str | None = None,
    ) -> None:
        with self._connection() as connection:
            self._execute(
                connection,
                "INSERT INTO operation_logs (admin_id, action, target_type, target_id, detail, created_at, ip_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    admin_id,
                    action,
                    target_type,
                    target_id,
                    json.dumps(detail or {}, ensure_ascii=False),
                    self._now(),
                    ip_hash,
                ),
            )

    def _is_login_limited(self, username: str, ip_hash: str | None) -> bool:
        since = (datetime.now() - timedelta(minutes=15)).isoformat(timespec="seconds")
        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT COUNT(*) AS count FROM login_failures WHERE username = ? AND failed_at >= ?",
                (username, since),
            )
        return int(row["count"] if row else 0) >= 5

    def _merge_admin_user_references(
        self,
        connection: Any,
        source_id: int,
        target_id: int,
    ) -> None:
        """把重复账号的关联记录迁移到保留账号。"""

        if source_id == target_id:
            return
        for table, column in (
            ("wrapped_surveys", "created_by"),
            ("teams", "created_by"),
            ("operation_logs", "admin_id"),
            ("token_requests", "requested_by"),
            ("token_requests", "reviewed_by"),
            ("team_invitations", "invitee_id"),
            ("team_invitations", "invited_by"),
            ("team_members", "invited_by"),
            ("survey_permissions", "granted_by"),
        ):
            self._execute(
                connection,
                f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                (target_id, source_id),
            )

        memberships = self._fetchall(
            connection,
            "SELECT team_id FROM team_members WHERE user_id = ?",
            (source_id,),
        )
        for membership in memberships:
            team_id = int(membership["team_id"])
            existing = self._fetchone(
                connection,
                "SELECT team_id FROM team_members WHERE team_id = ? AND user_id = ?",
                (team_id, target_id),
            )
            if existing:
                self._execute(
                    connection,
                    "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
                    (team_id, source_id),
                )
            else:
                self._execute(
                    connection,
                    "UPDATE team_members SET user_id = ? WHERE team_id = ? AND user_id = ?",
                    (target_id, team_id, source_id),
                )

        permissions = self._fetchall(
            connection,
            "SELECT survey_id, permission FROM survey_permissions WHERE user_id = ?",
            (source_id,),
        )
        for permission_row in permissions:
            survey_id = int(permission_row["survey_id"])
            existing = self._fetchone(
                connection,
                "SELECT permission FROM survey_permissions WHERE survey_id = ? AND user_id = ?",
                (survey_id, target_id),
            )
            if existing:
                permission = (
                    "editor"
                    if permission_row["permission"] == "editor"
                    or existing["permission"] == "editor"
                    else "viewer"
                )
                self._execute(
                    connection,
                    "UPDATE survey_permissions SET permission = ?, updated_at = ? "
                    "WHERE survey_id = ? AND user_id = ?",
                    (permission, self._now(), survey_id, target_id),
                )
                self._execute(
                    connection,
                    "DELETE FROM survey_permissions WHERE survey_id = ? AND user_id = ?",
                    (survey_id, source_id),
                )
            else:
                self._execute(
                    connection,
                    "UPDATE survey_permissions SET user_id = ? WHERE survey_id = ? AND user_id = ?",
                    (target_id, survey_id, source_id),
                )

    def _ensure_admin_seed(self, connection: Any) -> None:
        """确保演示账号为 aixin，并把历史 admin 账号平滑迁移过来。"""

        tenant_id = self._default_tenant_id(connection)
        now = self._now()
        legacy_row = self._fetchone(
            connection,
            "SELECT id FROM admin_users WHERE username = ? AND role <> 'platform_admin'",
            ("admin",),
        )
        owner_row = self._fetchone(
            connection,
            "SELECT id FROM admin_users WHERE username = ? AND role <> 'platform_admin'",
            (DEFAULT_OWNER_USERNAME,),
        )
        if legacy_row and owner_row and int(legacy_row["id"]) != int(owner_row["id"]):
            legacy_id = int(legacy_row["id"])
            duplicate_id = int(owner_row["id"])
            self._merge_admin_user_references(connection, duplicate_id, legacy_id)
            self._execute(
                connection,
                "DELETE FROM admin_sessions WHERE admin_id IN (?, ?)",
                (legacy_id, duplicate_id),
            )
            self._execute(connection, "DELETE FROM admin_users WHERE id = ?", (duplicate_id,))
            owner_id = legacy_id
        elif legacy_row:
            owner_id = int(legacy_row["id"])
            self._execute(
                connection,
                "DELETE FROM admin_sessions WHERE admin_id = ?",
                (owner_id,),
            )
        elif owner_row:
            owner_id = int(owner_row["id"])
            self._execute(
                connection,
                "DELETE FROM admin_sessions WHERE admin_id = ?",
                (owner_id,),
            )
        else:
            cursor = self._execute(
                connection,
                "INSERT INTO admin_users "
                "(username, password_hash, role, tenant_id, display_name, is_active, created_at, updated_at) "
                "VALUES (?, ?, 'owner', ?, ?, 1, ?, ?)",
                (
                    DEFAULT_OWNER_USERNAME,
                    hash_password(DEFAULT_OWNER_PASSWORD),
                    tenant_id,
                    "问卷管理员",
                    now,
                    now,
                ),
            )
            owner_id = int(cursor.lastrowid)

        self._execute(
            connection,
            "UPDATE admin_users SET username = ?, password_hash = ?, role = 'owner', "
            "tenant_id = COALESCE(tenant_id, ?), display_name = COALESCE(display_name, ?), "
            "is_active = 1, updated_at = ? WHERE id = ?",
            (
                DEFAULT_OWNER_USERNAME,
                hash_password(DEFAULT_OWNER_PASSWORD),
                tenant_id,
                "问卷管理员",
                now,
                owner_id,
            ),
        )
        self._execute(
            connection,
            "DELETE FROM login_failures WHERE username IN (?, ?)",
            ("admin", DEFAULT_OWNER_USERNAME),
        )
        platform_row = self._fetchone(
            connection,
            "SELECT id FROM admin_users WHERE username = ?",
            ("platform",),
        )
        if not platform_row:
            self._execute(
                connection,
                "INSERT INTO admin_users "
                "(username, password_hash, role, tenant_id, display_name, is_active, created_at, updated_at) "
                "VALUES (?, ?, 'platform_admin', NULL, ?, 1, ?, ?)",
                ("platform", hash_password("10124"), "平台管理员", now, now),
            )
        else:
            self._execute(
                connection,
                "UPDATE admin_users SET password_hash = ?, role = 'platform_admin', "
                "tenant_id = NULL, display_name = ?, is_active = 1, updated_at = ? WHERE id = ?",
                (hash_password("10124"), "平台管理员", now, platform_row["id"]),
            )
        self._execute(connection, "DELETE FROM login_failures WHERE username = ?", ("platform",))

    def _backfill_share_tokens(self, connection: Any) -> None:
        """给历史问卷补齐分享令牌，保证旧数据也能直接生成分享链接。"""

        rows = self._fetchall(
            connection,
            "SELECT id FROM wrapped_surveys WHERE share_token IS NULL OR share_token = ''",
        )
        for row in rows:
            self._execute(
                connection,
                "UPDATE wrapped_surveys SET share_token = ? WHERE id = ?",
                (self._new_share_token(connection), row["id"]),
            )

    def _new_share_token(self, connection: Any) -> str:
        """生成短而难猜的分享令牌。"""

        while True:
            token = secrets.token_urlsafe(12)
            exists = self._fetchone(
                connection,
                "SELECT 1 FROM wrapped_surveys WHERE share_token = ?",
                (token,),
            )
            if not exists:
                return token

    def _parse_mysql_url(self, value: str) -> dict[str, Any]:
        parsed = urlparse(value.replace("mysql+pymysql://", "mysql://", 1))
        database = parsed.path.lstrip("/")
        if not database:
            raise ValueError("MySQL 连接地址必须包含数据库名。")
        query = parse_qs(parsed.query)
        return {
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or "root"),
            "password": unquote(parsed.password or ""),
            "database": database,
            "charset": query.get("charset", ["utf8mb4"])[0],
            "autocommit": False,
            "cursorclass": __import__("pymysql").cursors.DictCursor,
        }

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    """使用 PBKDF2 保存管理员密码，避免明文或单一后台密码。"""

    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"pbkdf2_sha256$200000${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _slugify(value: str) -> str:
    """生成租户地址标识，中文企业名使用稳定的短前缀加随机后缀。"""

    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    normalized = "-".join(part for part in normalized.split("-") if part)
    return (normalized[:72] or "tenant") + "-" + secrets.token_hex(2)
