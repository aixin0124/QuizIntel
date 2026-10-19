CREATE DATABASE IF NOT EXISTS fun_research
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE fun_research;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INT PRIMARY KEY,
    applied_at VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admin_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'owner',
    tenant_id INT,
    display_name VARCHAR(120),
    email VARCHAR(255),
    is_active TINYINT NOT NULL DEFAULT 1,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    INDEX idx_admin_users_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admin_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NOT NULL,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    expires_at VARCHAR(32) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    last_seen_at VARCHAR(32) NOT NULL,
    user_agent VARCHAR(255),
    ip_hash VARCHAR(128),
    INDEX idx_admin_sessions_admin_id (admin_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS login_failures (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL,
    ip_hash VARCHAR(128),
    failed_at VARCHAR(32) NOT NULL,
    INDEX idx_login_failures_lookup (username, failed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
    created_by INT,
    moderation_status VARCHAR(32) NOT NULL DEFAULT 'approved',
    moderation_note VARCHAR(500),
    reviewed_by INT,
    reviewed_at VARCHAR(32),
    UNIQUE KEY idx_wrapped_surveys_share_token (share_token),
    INDEX idx_wrapped_surveys_owner (tenant_id, created_by, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
    INDEX idx_responses_survey_id (survey_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
    INDEX idx_generation_records_owner (tenant_id, created_by, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS platform_settings (
    setting_key VARCHAR(120) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    notification_type VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    survey_id INT,
    read_at VARCHAR(32),
    created_at VARCHAR(32) NOT NULL,
    INDEX idx_user_notifications_unread (user_id, read_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS announcements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    published_at VARCHAR(32),
    created_by INT NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    INDEX idx_announcements_status (status, published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS announcement_reads (
    announcement_id INT NOT NULL,
    user_id INT NOT NULL,
    read_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (announcement_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO schema_migrations (version, applied_at)
VALUES (1, DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s'));

INSERT IGNORE INTO schema_migrations (version, applied_at)
VALUES (2, DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s'));
