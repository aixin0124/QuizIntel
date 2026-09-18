# 数据库表结构说明

当前运行库建议使用 MySQL 8，字符集为 `utf8mb4`。SQLite 仍保留为测试和旧数据来源。

## wrapped_surveys

保存 AI 包装后的问卷主表。

- `status`：生命周期状态，包含 `draft`、`collecting`、`ended`、`archived`。
- `target_sample_count`：可选的目标样本数限制。
- `version`：问卷版本号，标题或题目语义变更后递增，答卷会记录提交时版本。
- `share_token`：公开分享令牌，用户只能通过 `/share/{token}` 访问。
- `prompt_version`、`model_name`、`generation_latency_ms`、`quality_score`：AI 生成质量控制字段。
- `payload`：完整问卷 JSON。
- `analysis_payload`：结束问卷后生成的最终分析 JSON。

## responses

保存匿名答卷。

- `source`：答卷来源，包含 `public_link`、`admin_preview`、`test`；后台浏览来源默认按正式答卷统计。
- `survey_version`：提交时对应的问卷版本，避免题目修改后旧答卷语义混乱。
- `duration_seconds`：提交耗时。
- `fingerprint_hash`、`browser_id_hash`、`ip_hash`、`access_code`：防重复提交字段，只保存哈希或访问码。
- `is_test`：是否明确测试答卷；当前只有 `test` 来源默认写为测试，`admin_preview` 来源仍按有效答卷处理。
- `is_invalid`、`invalid_reason`、`invalid_at`：管理员标记无效答卷。
- `payload`：完整答卷 JSON。

## admin_users / admin_sessions

后台账号与登录会话。

- 密码使用 PBKDF2-SHA256 哈希。
- `role` 支持 `admin` 和 `viewer`，查看者只能读取后台数据。
- 会话默认 8 小时过期。

## operation_logs

记录后台登录、发布、删除、改标题、标记答卷等操作，便于答辩说明安全审计。

## generation_records

记录每次 AI 生成。

- `prompt_version`：Prompt 版本。
- `model_name`：模型名称。
- `latency_ms`：生成耗时。
- `token_estimate`、`cost_estimate`：粗略 token 和成本记录。
- `quality_score`：题量、维度覆盖、选项映射完整度的综合评分。
- `retry_count`：结构校验失败后的重试次数。
