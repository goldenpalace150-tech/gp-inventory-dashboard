-- OPTIONAL hardening, after setup.sql. Run as postgres in Supabase SQL Editor.
-- Change both example passwords here before running; DO NOT commit filled passwords.
-- In Streamlit use the Session pooler host and user gp_app.PROJECT_REF.
CREATE ROLE gp_app LOGIN PASSWORD 'CHANGE_THIS_TO_A_NEW_STRONG_DATABASE_PASSWORD';
GRANT CONNECT ON DATABASE postgres TO gp_app;
GRANT USAGE ON SCHEMA gp_inventory TO gp_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA gp_inventory TO gp_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA gp_inventory TO gp_app;

-- Use this separate read-only account for scheduled exports.
CREATE ROLE gp_backup LOGIN PASSWORD 'CHANGE_THIS_TO_A_DIFFERENT_STRONG_DATABASE_PASSWORD';
GRANT CONNECT ON DATABASE postgres TO gp_backup;
GRANT USAGE ON SCHEMA gp_inventory TO gp_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA gp_inventory TO gp_backup;
