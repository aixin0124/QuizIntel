# 数据库表结构说明

当前运行库建议使用 MySQL 8，字符集为 `utf8mb4`。SQLite 仍保留为测试和旧数据来源。

## tenants / teams / team_members

`tenants` 作为旧数据和个人 Token 工作区的内部兼容表，前台不再暴露企业模块。每个注册账号拥有自己的个人工作区，问卷默认直接归创建者管理。历史数据仍通过 `tenant_id`、`team_id` 和 `created_by` 保留归属信息。

- `team_members.role`：组内成员权限，包含 `manager`、`editor`、`viewer`。
- `team_members.status`：成员状态，当前接受邀请后为 `accepted`。
- `team_invitations`：兼容历史协作数据，保存已注册账号之间的邀请、权限和接受/拒绝状态；前台统一称为协作成员邀请。
- `survey_permissions`：问卷级访问授权，保存成员对单份问卷的 `viewer` 或 `editor` 权限。

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

个人账号、平台超级管理员账号与登录会话。

- 密码使用 PBKDF2-SHA256 哈希。
- 普通注册账号使用 `owner` 角色，拥有自己问卷的最大权限；旧的 `admin`、`tenant_owner`、`survey_admin` 值只作为迁移兼容。
- `platform_admin` 只能通过 `/api/platform/auth/login` 登录平台后台。
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
- `tenant_id`、`team_id`、`created_by`：个人工作区、历史协作容器和创建人的归属信息。
- `moderation_status`、`moderation_note`、`reviewed_by`、`reviewed_at`：平台内容审核状态。

## token_requests / platform_settings

- `token_requests`：个人账号向平台管理员申请 Token 的记录，审批通过后增加对应个人工作区余额。
- `platform_settings`：注册初始额度、解析/分析默认估算和是否强制内容审核等全局设置。

## generation_records

除 AI 生成记录外，也记录问卷解析和最终分析的 Token 调用。`tenant_id` 用于把没有具体问卷编号的解析请求归属到个人工作区。
