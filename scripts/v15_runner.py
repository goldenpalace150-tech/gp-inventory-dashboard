from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts/v15_zoho_shell.py"), run_name="__main__")

# re.sub replacement processing in the updater turns the intended source-level
# \\n escape into a literal newline inside the quoted st.code() string. Normalize
# that one generated line before compile/validation.
path = ROOT / "inventory_tracker.py"
text = path.read_text(encoding="utf-8")
broken = 'st.code("database.host / database.user / database.password / database.dbname\nauth.bootstrap_username / auth.bootstrap_password",language="text")'
fixed = 'st.code("database.host / database.user / database.password / database.dbname\\nauth.bootstrap_username / auth.bootstrap_password",language="text")'
if broken in text:
    text = text.replace(broken, fixed, 1)
path.write_text(text, encoding="utf-8")
print("v15 post-generation source normalization applied")
