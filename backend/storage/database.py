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
            self._ensure_admin_seed(connection)
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
                quality_score REAL
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
        self._execute(connection, "UPDATE wrapped_surveys SET status = 'collecting' WHERE status = 'open'")
        self._execute(connection, "UPDATE wrapped_surveys SET status = 'draft' WHERE status = 'pending'")
        self._execute(connection, "UPDATE wrapped_surveys SET status = 'ended' WHERE status = 'paused'")

    def _normalize_response_sources(self, connection: Any) -> None:
        """后台浏览答卷默认参与统计，只有明确测试来源才排除。"""

        self._execute(
            connection,
            "UPDATE responses SET is_test = 0 WHERE source = 'admin_preview'",
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
    ) -> int:
        if status not in SURVEY_STATUSES:
            raise ValueError("问卷状态无效。")
        with self._connection() as connection:
            cursor = self._execute(
                connection,
                "INSERT INTO wrapped_surveys "
                "(survey_name, theme, source, created_at, payload, status, share_token, "
                "prompt_version, model_name, generation_latency_ms, quality_score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                "version = version + 1, analysis_payload = NULL, ended_at = NULL WHERE id = ?",
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
    ) -> list[dict[str, Any]]:
        with self._connection() as connection:
            conditions: list[str] = []
            values: list[Any] = []
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
                "s.quality_score, "
                "(SELECT COUNT(*) FROM responses r WHERE r.survey_id = s.id AND r.is_invalid = 0 AND r.is_test = 0) AS response_count "
                f"FROM wrapped_surveys s {where} ORDER BY s.id DESC LIMIT ?",
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
                "(survey_id, prompt_version, model_name, latency_ms, token_estimate, cost_estimate, "
                "quality_score, retry_count, status, error_message, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    survey_id,
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
        return {"token": token, "role": user["role"], "username": user["username"], "expires_in": ADMIN_SESSION_HOURS * 3600}

    def get_admin_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        now = self._now()
        with self._connection() as connection:
            row = self._fetchone(
                connection,
                "SELECT s.id AS session_id, s.admin_id, s.expires_at, u.username, u.role "
                "FROM admin_sessions s JOIN admin_users u ON u.id = s.admin_id "
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

    def list_admin_users(self) -> list[dict[str, Any]]:
        """读取管理员账号摘要，不返回密码哈希。"""

        with self._connection() as connection:
            return self._fetchall(
                connection,
                "SELECT id, username, role, is_active, created_at, updated_at "
                "FROM admin_users ORDER BY id",
            )

    def create_admin_user(
        self,
        username: str,
        password: str,
        role: str,
    ) -> dict[str, Any]:
        """创建管理员或只读查看者账号。"""

        username = username.strip()
        if not username:
            raise ValueError("账号不能为空。")
        if role not in {"admin", "viewer"}:
            raise ValueError("账号角色只能是 admin 或 viewer。")
        now = self._now()
        with self._connection() as connection:
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
                "(username, password_hash, role, is_active, created_at, updated_at) "
                "VALUES (?, ?, ?, 1, ?, ?)",
                (username, hash_password(password), role, now, now),
            )
            user_id = int(cursor.lastrowid)
        return {
            "id": user_id,
            "username": username,
            "role": role,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

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

    def _ensure_admin_seed(self, connection: Any) -> None:
        row = self._fetchone(connection, "SELECT id FROM admin_users LIMIT 1")
        if row:
            return
        now = self._now()
        self._execute(
            connection,
            "INSERT INTO admin_users (username, password_hash, role, is_active, created_at, updated_at) "
            "VALUES (?, ?, 'admin', 1, ?, ?)",
            ("admin", hash_password("10124"), now, now),
        )

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
