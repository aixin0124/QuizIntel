"""把旧 SQLite 数据直接插入到 MySQL。

运行示例：
python -m backend.storage.migrate_sqlite_to_mysql --sqlite data/fun_research.db --mysql mysql+pymysql://root:10124@127.0.0.1:3306/fun_research?charset=utf8mb4
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

from .database import ResearchDatabase


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移趣测智研 SQLite 数据到 MySQL")
    parser.add_argument("--sqlite", default="data/fun_research.db", help="SQLite 数据库路径")
    parser.add_argument("--mysql", required=True, help="MySQL 连接地址")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite 数据库不存在：{sqlite_path}")

    target = ResearchDatabase(args.mysql)
    migrated_surveys = 0
    migrated_responses = 0
    migrated_generations = 0
    with sqlite3.connect(sqlite_path) as source:
        source.row_factory = sqlite3.Row
        with target._connection() as connection:
            for row in source.execute("SELECT * FROM wrapped_surveys ORDER BY id"):
                item = dict(row)
                status = {
                    "open": "collecting",
                    "pending": "draft",
                    "paused": "ended",
                }.get(item.get("status"), item.get("status") or "draft")
                if _exists(target, connection, "wrapped_surveys", int(item["id"])):
                    continue
                target._execute(
                    connection,
                    "INSERT INTO wrapped_surveys "
                    "(id, survey_name, theme, source, created_at, payload, status, "
                    "target_sample_count, ended_at, analysis_payload, deleted_at, share_token, version, "
                    "prompt_version, model_name, generation_latency_ms, quality_score) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item["id"],
                        item["survey_name"],
                        item["theme"],
                        item["source"],
                        item["created_at"],
                        item["payload"],
                        status,
                        item.get("target_sample_count"),
                        item.get("ended_at"),
                        item.get("analysis_payload"),
                        item.get("deleted_at"),
                        item.get("share_token"),
                        item.get("version") or 1,
                        item.get("prompt_version"),
                        item.get("model_name"),
                        item.get("generation_latency_ms"),
                        item.get("quality_score"),
                    ),
                )
                migrated_surveys += 1

            for row in source.execute("SELECT * FROM responses ORDER BY id"):
                item = dict(row)
                if _exists(target, connection, "responses", int(item["id"])):
                    continue
                target._execute(
                    connection,
                    "INSERT INTO responses "
                    "(id, survey_id, survey_version, result_type, created_at, submitted_at, payload, source, "
                    "duration_seconds, fingerprint_hash, browser_id_hash, ip_hash, access_code, is_test, "
                    "is_invalid, invalid_reason, invalid_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item["id"],
                        item.get("survey_id"),
                        item.get("survey_version") or 1,
                        item["result_type"],
                        item["created_at"],
                        item.get("submitted_at") or item["created_at"],
                        item["payload"],
                        item.get("source") or "public_link",
                        item.get("duration_seconds"),
                        item.get("fingerprint_hash"),
                        item.get("browser_id_hash"),
                        item.get("ip_hash"),
                        item.get("access_code"),
                        1 if item.get("is_test") and item.get("source") == "test" else 0,
                        item.get("is_invalid") or 0,
                        item.get("invalid_reason"),
                        item.get("invalid_at"),
                    ),
                )
                migrated_responses += 1

            if _table_exists(source, "generation_records"):
                for row in source.execute("SELECT * FROM generation_records ORDER BY id"):
                    item = dict(row)
                    if _exists(target, connection, "generation_records", int(item["id"])):
                        continue
                    target._execute(
                        connection,
                        "INSERT INTO generation_records "
                        "(id, survey_id, prompt_version, model_name, latency_ms, token_estimate, "
                        "cost_estimate, quality_score, retry_count, status, error_message, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            item["id"],
                            item.get("survey_id"),
                            item.get("prompt_version") or "legacy",
                            item.get("model_name") or "unknown",
                            item.get("latency_ms") or 0,
                            item.get("token_estimate") or 0,
                            item.get("cost_estimate") or 0,
                            item.get("quality_score") or 0,
                            item.get("retry_count") or 0,
                            item.get("status") or "success",
                            item.get("error_message"),
                            item.get("created_at"),
                        ),
                    )
                    migrated_generations += 1
    print(
        f"迁移完成：问卷 {migrated_surveys} 份，答卷 {migrated_responses} 份，生成记录 {migrated_generations} 条。"
    )


def _exists(database: ResearchDatabase, connection: Any, table: str, row_id: int) -> bool:
    return bool(database._fetchone(connection, f"SELECT id FROM {table} WHERE id = ?", (row_id,)))


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return bool(row)


if __name__ == "__main__":
    main()
