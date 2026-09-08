# Cloud v5 preparation record

Date: 8 September 2026. This record distinguishes completed setup from remaining live checks.

## Completed before the staging commit

- Read the existing repository and retained its original main commit as the rollout base.
- Created a separate `cloud-v5-staging` branch. No production branch changes were made.
- Connected to the owner's selected existing Supabase project and verified that its organization is on the Free plan; no new paid project or plan was created.
- Applied migration `golden_palace_inventory_v5`: 13 private `gp_inventory` tables and one application-state row.
- Verified the anon and authenticated roles have no schema usage, table-read or table-write privileges in that schema.
- Ran PostgreSQL smoke checks: insert/update balance, reject a duplicate primary key, roll back a failing nested operation, then roll back all test data. Stock, users and movement-ledger tables remained empty; schema version 5 and revision 0 were verified.
- Ran the full source regression suite locally: **65 passed in 17.21 seconds**. Tests use synthetic data and the explicit SQLite test adapter. Python syntax checks passed.
- Matched uploaded application/module/test Git blob hashes to the locally tested files.
- Preserved the v4 isolated OCR worker. There was no new real OCR model execution.
- Prepared a checksum-verified compressed copy of the owner's horizontal logo and its emblem favicon. No replacement brand artwork was generated.

## Pending / not claimed complete

- Streamlit Secrets must be entered privately by the owner. No database password, app password, API key or private workbook was committed.
- The staging workflow results must be checked after the commit; its actual status is in GitHub Actions, not implied by this document.
- The actual assembled `assets/golden_palace.jpg` must be present before merging.
- The live Streamlit app has not yet been switched to cloud v5.
- PostgreSQL application-driver/TLS/pooler testing from the Streamlit host, concurrent-client integration tests, real hosted UI review and real invoice OCR remain to be verified.
- No inventory was imported and no old JSON backup was restored.
- No independent scheduled backup has been enabled. The encrypted workflow stays disabled until the required secrets and opt-in variable are configured.

Cloud persistence protects committed records from browser closure, but it is not a guarantee of uninterrupted free-tier hosting or a replacement for independently verified backups. Unsubmitted form edits require Save draft or approval.
