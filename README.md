# Golden Palace Inventory - Cloud v5

Streamlit inventory management with private Supabase PostgreSQL storage, Arabic task-based navigation, navy/gold branding, saved invoice drafts and isolated CPU invoice reading.

## Current rollout

The update is prepared on `cloud-v5-staging`. The deployed `main` branch must remain unchanged until the owner saves the database connection and initial administrator password in Streamlit Secrets. No real credentials belong in this repository.

The inventory schema has already been created in the owner's selected existing Free-plan Supabase project. No need to run SQL again for that project. See `DEPLOYMENT_STATUS.md` for the verified boundaries.

## Remaining private setup

In Streamlit **Manage app > Settings > Secrets**, configure the sections in `secrets.example.toml`. Use the exact **Session pooler** host from Supabase's **Connect** panel, port **5432**, database **postgres**, and the pooler username (including the project reference). The password is the database password, not a Supabase API key. Choose a separate initial app administrator password of at least 12 characters.

After these settings are saved, the staged update can be merged. Keep Python **3.11** and entry point **inventory_tracker.py**. The first successful startup creates the administrator; there is no default admin/123 password. Remove `auth.bootstrap_password` after the account is successfully created.

The new cloud database starts empty: import the current opening-stock report and Ameen movement report from Settings after login. This version does not automatically migrate an old JSON backup or SQLite file.

## Application structure

- `inventory_tracker.py`: login, stock, invoices, manual movements, analysis, day closing and settings.
- `gp_store.py`: cloud transactions, authentication, permissions, duplicate prevention, drafts and snapshots.
- `gp_core.py`: report import and reorder calculations.
- `gp_invoice.py`: exact code/name matching; ambiguous lines cannot post.
- `gp_ocr.py` and `invoice_ocr_worker.py`: disposable numeric OCR worker, memory/time limits, no paid OCR API.
- `gp_ui.py`, `assets/`, `.streamlit/config.toml`: scoped RTL layout and supplied Golden Palace branding; no login sidebar.
- `gp_reports.py`: on-demand Excel reports.
- `gp_backup.py`, `scripts/`: encrypted backups and restore into an empty destination only.
- `sql/setup.sql`: reproducible private schema setup for new projects.

Approved stock updates, their ledger rows and invoice registrations commit together. The server reads current database balances, not a stale browser balance. A failed database connection never silently redirects writes to local SQLite. The SQLite adapter is for tests only.

Successful OCR results are saved as drafts. Unsubmitted edits in the browser must be saved with **Save draft** or approved; closing a browser cannot guarantee saving unsent edits. Invoice images are not retained; source names, hashes and reviewed fields are stored. Numeric OCR uses the supplied Golden Palace portrait layout, not arbitrary invoice layouts; Arabic item names come from exact stock-code matches. Select IN/OUT and review every line before approving.

## Private database boundary

`gp_inventory` is a server-only schema, with schema/table/sequence privileges revoked from PUBLIC, anon and authenticated. It is not designed for direct browser Data API access. Keep it out of exposed API schemas. Optional least-privilege server and read-only backup roles are documented in `sql/restricted_roles.example.sql`; set their real passwords privately, never commit them. This template was not automatically executed.

## Independent backups - not yet enabled

`.github/workflows/encrypted-backup.yml` is opt-in. Configure repository secrets `GP_DB_HOST`, `GP_DB_USER`, `GP_DB_PASSWORD`, and `GP_BACKUP_KEY`, then set repository variable `GP_BACKUP_ENABLED` to `true`. Prefer a separate read-only database role. Generate a Fernet encryption key privately, for example `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Keep a separate private copy of that key; losing it prevents recovery.

The workflow stores encrypted snapshots as seven-day artifacts. No plaintext inventory or credentials are committed. Check the first manual run and test a restore in an empty destination before relying on it. Provider free-plan, scheduling and storage limits still apply. Cloud persistence is not a substitute for verified independent backups.

The backup includes business tables and password hashes, excluding login sessions. Restore refuses to overwrite a populated database. Run `sql/setup.sql` on a new destination, but do not bootstrap an administrator before restore:

```sh
python scripts/restore.py backup.gpbackup
python scripts/restore.py backup.gpbackup --confirm-empty-target
```

The first command verifies/decrypts only. Both commands read the private environment variables used by `scripts/backup.py`.

## Validation and assets

Local regression command:

```sh
python -m pytest -o addopts='' -q
```

The staging validation workflow compiles code and runs the offline tests under Python 3.11 without OCR model downloads or production secrets. It also assembles the supplied compressed logo from checked-in text segments, checks its SHA-256, and adds the verified JPEG to the staging branch only. The actual JPEG must exist before merging.

The offline tests do not establish live hosted OCR accuracy, Supabase network connectivity from Streamlit, or full concurrent PostgreSQL application behavior. Complete those acceptance checks after private configuration and before normal business use.

Do not add `packages.txt` for this pip-only OCR version. Standard dependency installation may download model packages; the first invoice read can download the English OCR model. No invoice image is sent to an external OCR API.
