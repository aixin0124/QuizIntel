# 数据库表结构说明

当前数据库使用 MySQL 8，字符集为 `utf8mb4`。SQLite 仍用于本地开发和测试。系统采用个人工作区模型：每个普通账号拥有一个 `tenant`，新建问卷直接归当前账号管理，不再创建团队、成员或问卷授权记录。

## 表清单

| 表 | 用途 |
| --- | --- |
| `schema_migrations` | 记录初始化和结构清理版本 |
| `tenants` | 个人工作区及 Token 额度 |
| `admin_users` | 普通账号和平台管理员账号 |
| `admin_sessions` | 后台登录会话 |
| `login_failures` | 登录失败限流记录 |
| `operation_logs` | 登录、发布、删除、审核等操作审计 |
| `wrapped_surveys` | AI 包装后的问卷 |
| `responses` | 匿名答卷 |
| `generation_records` | 问卷解析、AI 包装和分析的 Token 调用记录 |
| `token_requests` | 个人账号申请 Token 的记录 |
| `platform_settings` | 平台级默认配置 |
| `user_notifications` | 面向账号的审核和业务通知 |
| `announcements` | 平台公告及发布状态 |
| `announcement_reads` | 用户公告已读记录 |

旧版本中的 `teams`、`team_members`、`team_invitations`、`survey_permissions` 已废弃。应用启动时会删除这些表，并删除 `wrapped_surveys.team_id` 等协作字段。

## 个人工作区

### `tenants`

保存个人工作区名称、状态和 Token 余额。它保留在系统中是因为 Token 额度、平台统计和内容审核仍按工作区归属。

- `slug`：工作区唯一标识。
- `token_balance`：当前可用 Token。
- `token_used`：累计已消耗 Token。
- `status`：工作区状态，当前使用 `active`。

### `admin_users`

保存登录账号。

- 普通注册账号使用 `owner` 角色。
- 平台管理员使用 `platform_admin` 角色，并通过独立的平台后台登录。
- `tenant_id` 指向个人工作区。
- 密码使用 PBKDF2-SHA256 哈希，不保存明文密码。

## 问卷与答卷

### `wrapped_surveys`

保存问卷标题、主题、完整 JSON、生命周期和平台审核信息。

- `created_by`：创建问卷的账号。
- `tenant_id`：所属个人工作区。
- `status`：`draft`、`collecting`、`ended` 或 `archived`。
- `share_token`：公开填写链接使用的随机令牌。
- `version`：问卷内容版本。
- `payload`：完整互动问卷 JSON。
- `analysis_payload`：问卷结束后生成的研究分析 JSON。
- `deleted_at`：软删除时间，非空表示进入回收站。
- `moderation_status`：`pending`、`approved` 或 `rejected`。

### 公告与通知

- `user_notifications` 只面向指定账号，用于问卷退回等私有业务提示。
- `announcements` 保存草稿、已发布和已下线的全局公告。
- `announcement_reads` 按用户记录公告已读状态，公告历史不会因已读而删除。

问卷访问权限只由创建账号和所属个人工作区决定，不再存在成员授权。

### `responses`

保存匿名答卷和结果分析。

- `survey_id`：对应问卷。
- `survey_version`：提交时使用的问卷版本。
- `source`：`public_link`、`admin_preview` 或 `test`。
- `is_test`：是否为明确的测试答卷。
- `is_invalid`：是否被管理员标记为无效。
- `fingerprint_hash`、`browser_id_hash`、`ip_hash`：仅保存哈希值，用于防止重复提交。
- `payload`：完整答卷 JSON。

## 用量与平台治理

### `generation_records`

记录解析问卷、生成互动包装和生成最终分析时的调用信息，包括模型、耗时、Token 估算、质量评分和状态。`created_by` 和 `tenant_id` 用于隔离个人账号用量。

### `token_requests`

普通账号向平台管理员申请 Token 的记录。审批通过后增加对应个人工作区的 `token_balance`。

### `platform_settings`

保存注册初始额度、解析默认消耗、分析默认消耗和内容审核开关等配置。

### `operation_logs`

保存登录、注册、生成问卷、发布问卷、修改标题、删除问卷、答卷处理和平台审核等操作，供审计和答辩说明使用。

## 初始化与升级

全新 MySQL 数据库可执行 `init_mysql.sql`。应用启动时也会自动创建缺失表和字段。

协作功能下线后的结构清理版本为 `2`：

1. 删除 `survey_permissions`。
2. 删除 `team_invitations`。
3. 删除 `team_members`。
4. 删除 `teams`。
5. 删除 `wrapped_surveys.team_id` 和其他协作字段。

清理动作不会删除问卷、答卷、个人账号或 Token 记录；历史协作授权本身会被删除，因为系统不再支持该权限模型。
