"""SQLite 数据持久化。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import SurveyResponse, WrappedSurvey


class ResearchDatabase:
    """保存包装方案和匿名答卷，不保存姓名、手机号等身份信息。"""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS wrapped_surveys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    survey_name TEXT NOT NULL,
                    theme TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    survey_id INTEGER,
                    result_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY (survey_id) REFERENCES wrapped_surveys(id)
                );
                CREATE INDEX IF NOT EXISTS idx_responses_survey_id ON responses(survey_id);
                """
            )

    def save_survey(self, survey: WrappedSurvey) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO wrapped_surveys "
                "(survey_name, theme, source, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                (
                    survey.survey_name,
                    survey.theme,
                    survey.source,
                    datetime.now().isoformat(timespec="seconds"),
                    json.dumps(survey.to_dict(), ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def save_response(self, response: SurveyResponse, survey_id: int | None = None) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO responses "
                "(survey_id, result_type, created_at, payload) VALUES (?, ?, ?, ?)",
                (
                    survey_id,
                    response.result_type,
                    datetime.now().isoformat(timespec="seconds"),
                    json.dumps(response.to_dict(), ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def list_surveys(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT s.id, s.survey_name, s.theme, s.source, s.created_at, "
                "(SELECT COUNT(*) FROM responses r WHERE r.survey_id = s.id) AS response_count "
                "FROM wrapped_surveys s ORDER BY s.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_survey(self, survey_id: int) -> dict[str, Any] | None:
        """根据编号读取完整包装方案。"""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM wrapped_surveys WHERE id = ?", (survey_id,)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        return item

    def list_responses(self, survey_id: int) -> list[SurveyResponse]:
        """按包装方案编号读取答卷，避免同名问卷的数据相互混入。"""

        query = "SELECT payload FROM responses WHERE survey_id = ? ORDER BY id DESC LIMIT 500"
        with self._connect() as connection:
            rows = connection.execute(query, (survey_id,)).fetchall()
        result: list[SurveyResponse] = []
        for row in rows:
            payload = json.loads(row["payload"])
            result.append(
                SurveyResponse(
                    wrapped_survey_name=payload["wrapped_survey_name"],
                    answers=payload["answers"],
                    result_type=payload["result_type"],
                    research_answers=payload["research_answers"],
                )
            )
        return result

    def list_response_rows(self, survey_id: int) -> list[dict[str, Any]]:
        """读取带编号和时间的答卷明细，供后台和报表导出使用。"""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, result_type, created_at, payload "
                "FROM responses WHERE survey_id = ? ORDER BY id DESC LIMIT 500",
                (survey_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload"])
            result.append(
                {
                    "id": row["id"],
                    "result_type": row["result_type"],
                    "created_at": row["created_at"],
                    "answers": payload.get("answers", {}),
                    "research_answers": payload.get("research_answers", {}),
                }
            )
        return result
