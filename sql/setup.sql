-- Golden Palace Cloud v5. Run as the database administrator.
-- Existing data is preserved. This private schema is for trusted server access,
-- not browser access through Supabase anon/authenticated Data API clients.
BEGIN;
CREATE SCHEMA IF NOT EXISTS gp_inventory;
REVOKE ALL ON SCHEMA gp_inventory FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS gp_inventory.app_state (
 id SERIAL PRIMARY KEY, schema_version INTEGER NOT NULL, revision BIGINT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL, settings JSON NOT NULL,
 history_as_of TIMESTAMPTZ, history_hash VARCHAR(64), timezone VARCHAR(64) NOT NULL,
 CHECK (id = 1)
);
CREATE TABLE IF NOT EXISTS gp_inventory.app_users (
 username VARCHAR(80) PRIMARY KEY, display_name VARCHAR(120) NOT NULL,
 role VARCHAR(16) NOT NULL CHECK (role IN ('admin','store')),
 password_hash TEXT NOT NULL, active BOOLEAN NOT NULL,
 failed_attempts INTEGER NOT NULL, locked_until TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS gp_inventory.audit_log (
 event_id VARCHAR(36) PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL,
 username VARCHAR(80) NOT NULL, action VARCHAR(40) NOT NULL, details JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS gp_inventory.auth_sessions (
 token_hash VARCHAR(64) PRIMARY KEY, username VARCHAR(80) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS gp_inventory.baseline_snapshots (
 operation_id VARCHAR(36) PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL,
 username VARCHAR(80) NOT NULL, stock JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS gp_inventory.daily_closures (
 business_date DATE PRIMARY KEY, closed_at TIMESTAMPTZ NOT NULL,
 username VARCHAR(80) NOT NULL, movement_count INTEGER NOT NULL,
 total_in NUMERIC(20,4) NOT NULL, total_out NUMERIC(20,4) NOT NULL,
 no_invoice_count INTEGER NOT NULL, analysis JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS gp_inventory.daily_stock_snapshots (
 business_date DATE NOT NULL, item_key TEXT NOT NULL,
 item_code VARCHAR(160) NOT NULL, item_name TEXT NOT NULL,
 quantity NUMERIC(20,4) NOT NULL, match_key TEXT NOT NULL,
 PRIMARY KEY (business_date,item_key)
);
CREATE TABLE IF NOT EXISTS gp_inventory.imported_movement_history (
 row_id BIGSERIAL PRIMARY KEY, item_code VARCHAR(160) NOT NULL,
 item_name TEXT NOT NULL, movement_date TIMESTAMPTZ NOT NULL,
 reference TEXT NOT NULL, customer TEXT NOT NULL,
 qty_in NUMERIC(20,4) NOT NULL, qty_out NUMERIC(20,4) NOT NULL,
 balance NUMERIC(20,4), username VARCHAR(80) NOT NULL,
 statement TEXT NOT NULL, match_key TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_history_match_date ON gp_inventory.imported_movement_history(match_key,movement_date);
CREATE TABLE IF NOT EXISTS gp_inventory.invoice_drafts (
 draft_id VARCHAR(36) PRIMARY KEY, username VARCHAR(80) NOT NULL,
 image_hash VARCHAR(64), source_name VARCHAR(240) NOT NULL,
 payload JSON NOT NULL, status VARCHAR(16) NOT NULL,
 version INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(username,image_hash), CHECK(status IN ('pending','posted','discarded'))
);
CREATE INDEX IF NOT EXISTS ix_draft_owner_status ON gp_inventory.invoice_drafts(username,status);
CREATE TABLE IF NOT EXISTS gp_inventory.movement_ledger (
 ledger_id BIGSERIAL PRIMARY KEY, operation_id VARCHAR(36) NOT NULL,
 line_no INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL,
 business_date DATE NOT NULL, username VARCHAR(80) NOT NULL,
 source VARCHAR(16) NOT NULL, movement_type VARCHAR(3) NOT NULL,
 item_key TEXT NOT NULL, item_code VARCHAR(160) NOT NULL, item_name TEXT NOT NULL,
 quantity NUMERIC(20,4) NOT NULL, quantity_before NUMERIC(20,4) NOT NULL,
 quantity_after NUMERIC(20,4) NOT NULL, invoice_reference VARCHAR(160) NOT NULL,
 without_invoice BOOLEAN NOT NULL, delivery_note BOOLEAN NOT NULL, reason TEXT NOT NULL,
 UNIQUE(operation_id,line_no), CHECK(movement_type IN ('IN','OUT')), CHECK(quantity>0)
);
CREATE INDEX IF NOT EXISTS ix_ledger_business_date ON gp_inventory.movement_ledger(business_date);
CREATE TABLE IF NOT EXISTS gp_inventory.operations (
 operation_id VARCHAR(36) PRIMARY KEY, request_key VARCHAR(100) NOT NULL UNIQUE,
 payload_hash VARCHAR(64) NOT NULL, username VARCHAR(80) NOT NULL,
 source VARCHAR(30) NOT NULL, business_date DATE NOT NULL,
 created_at TIMESTAMPTZ NOT NULL, details JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS gp_inventory.posted_invoices (
 invoice_reference VARCHAR(160) PRIMARY KEY, image_hash VARCHAR(64) UNIQUE,
 operation_id VARCHAR(36) NOT NULL UNIQUE, posted_at TIMESTAMPTZ NOT NULL,
 username VARCHAR(80) NOT NULL, recognized_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS gp_inventory.stock_state (
 item_key TEXT PRIMARY KEY, item_code VARCHAR(160) NOT NULL,
 item_name TEXT NOT NULL, quantity NUMERIC(20,4) NOT NULL,
 match_key TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
INSERT INTO gp_inventory.app_state(id,schema_version,revision,updated_at,settings,timezone)
VALUES (1,5,0,now(),'{"lead_days":30,"safety_days":15,"slow_days":90,"demand_window_days":90,"review_days":30,"purchase_prefixes":["إد.م. م. م."]}'::json,'Asia/Damascus')
ON CONFLICT(id) DO NOTHING;
REVOKE ALL ON ALL TABLES IN SCHEMA gp_inventory FROM PUBLIC,anon,authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA gp_inventory FROM PUBLIC,anon,authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gp_inventory REVOKE ALL ON TABLES FROM PUBLIC,anon,authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gp_inventory REVOKE ALL ON SEQUENCES FROM PUBLIC,anon,authenticated;
COMMIT;
