CREATE DATABASE IF NOT EXISTS fun_research
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE fun_research;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INT PRIMARY KEY,
  applied_at VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO schema_migrations (version, applied_at)
VALUES (1, DATE_FORMAT(NOW(), '%Y-%m-%dT%H:%i:%s'));
