-- Default PostgreSQL schema reference for uptime monitor.
-- Runtime table/column names can be overridden via .env TABLE_* and COL_* keys.

CREATE TABLE IF NOT EXISTS monitored_servers (
  id BIGSERIAL PRIMARY KEY,
  target TEXT NOT NULL UNIQUE,
  target_type TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS uptime_check_history (
  id BIGSERIAL PRIMARY KEY,
  server_id BIGINT NOT NULL,
  target TEXT NOT NULL,
  checked_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL,
  response_time_ms DOUBLE PRECISION,
  error_details TEXT,
  check_method TEXT NOT NULL,
  FOREIGN KEY(server_id) REFERENCES monitored_servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uptime_check_history_checked_at
  ON uptime_check_history (checked_at);

CREATE INDEX IF NOT EXISTS idx_uptime_check_history_server_id
  ON uptime_check_history (server_id);
