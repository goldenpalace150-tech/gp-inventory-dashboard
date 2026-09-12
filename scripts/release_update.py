from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# -----------------------------
# Backend: retry transient DB write failures for user creation
# -----------------------------
store_path = ROOT / "gp_store.py"
store = store_path.read_text(encoding="utf-8")

old = '''from sqlalchemy import (\n    MetaData, Table, Column, String, Text, Integer, BigInteger, Numeric,\n    Boolean, Date, DateTime, JSON, ForeignKey, UniqueConstraint, CheckConstraint,\n    Index, select, insert, update, delete, func, create_engine,\n)\n'''
new = '''from sqlalchemy import (\n    MetaData, Table, Column, String, Text, Integer, BigInteger, Numeric,\n    Boolean, Date, DateTime, JSON, ForeignKey, UniqueConstraint, CheckConstraint,\n    Index, select, insert, update, delete, func, create_engine,\n)\nfrom sqlalchemy.exc import DBAPIError, IntegrityError\n'''
if new not in store:
    if old not in store:
        raise RuntimeError("sqlalchemy import marker not found")
    store = store.replace(old, new, 1)

old = '''    def create_user(self,token,password,username,new_password,role,display_name=""):\n        username=str(username).strip()\n        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}",username):raise AppError("Use 3 to 80 letters, digits, dots or underscores for usernames")\n        if role not in ("admin","store"):raise AppError("Invalid role")\n        hashed=password_hash(new_password)\n        with self.engine.begin() as c:\n            self._lock(c);actor=self._actor(c,token,password,admin=True);t=self.tables["app_users"]\n            if c.execute(select(t.c.username).where(t.c.username==username)).first():raise AppError("Username already exists")\n            c.execute(insert(t).values(username=username,display_name=str(display_name or username)[:120],role=role,password_hash=hashed,\n                active=True,failed_attempts=0,created_at=utcnow()))\n            self._audit(c,actor["username"],"CREATE_USER",{"username":username,"role":role});self._touch(c)\n'''
new = '''    def create_user(self,token,password,username,new_password,role,display_name=""):\n        username=str(username).strip()\n        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}",username):raise AppError("Use 3 to 80 letters, digits, dots or underscores for usernames")\n        if role not in ("admin","store"):raise AppError("Invalid role")\n        hashed=password_hash(new_password)\n        display_name=str(display_name or username)[:120]\n        for attempt in range(2):\n            try:\n                with self.engine.begin() as c:\n                    self._lock(c);actor=self._actor(c,token,password,admin=True);t=self.tables["app_users"]\n                    if c.execute(select(t.c.username).where(t.c.username==username)).first():raise AppError("Username already exists")\n                    c.execute(insert(t).values(username=username,display_name=display_name,role=role,password_hash=hashed,\n                        active=True,failed_attempts=0,created_at=utcnow()))\n                    self._audit(c,actor["username"],"CREATE_USER",{"username":username,"role":role});self._touch(c)\n                return\n            except IntegrityError as error:\n                sqlstate=str(getattr(getattr(error,"orig",None),"sqlstate","") or "")\n                if sqlstate=="23505":raise AppError("Username already exists") from None\n                raise\n            except DBAPIError as error:\n                sqlstate=str(getattr(getattr(error,"orig",None),"sqlstate","") or "")\n                transient=bool(getattr(error,"connection_invalidated",False)) or sqlstate.startswith("08") or sqlstate in {"55P03","57014","57P01","57P02","57P03"}\n                if attempt==0 and transient:\n                    self.engine.dispose()\n                    continue\n                raise\n'''
if new not in store:
    if old not in store:
        raise RuntimeError("create_user marker not found")
    store = store.replace(old, new, 1)
store_path.write_text(store, encoding="utf-8")

# -----------------------------
# UI: show safe DB error class/sqlstate instead of opaque-only failure
# -----------------------------
app_path = ROOT / "inventory_tracker.py"
app = app_path.read_text(encoding="utf-8")
old = '''    else:\n        reference=str(uuid.uuid4())[:8]\n        sqlstate=getattr(getattr(error,"orig",None),"sqlstate","")\n        # No repr/traceback of a database error: it may include secrets or invoice data.\n        LOG.error("App failure id=%s type=%s sqlstate=%s",reference,type(error).__name__,sqlstate)\n        st.error("Save/connection not confirmed. Refresh the data before retrying. "\n                 "No local database is used. Reference: "+reference)\n'''
new = '''    else:\n        reference=str(uuid.uuid4())[:8]\n        sqlstate=str(getattr(getattr(error,"orig",None),"sqlstate","") or "")\n        kind=type(error).__name__\n        # No repr/traceback of a database error: it may include secrets or invoice data.\n        LOG.error("App failure id=%s type=%s sqlstate=%s",reference,kind,sqlstate)\n        safe_detail=kind+(" / SQLSTATE "+sqlstate if sqlstate else "")\n        st.error("Save/connection not confirmed ("+safe_detail+"). Refresh the data before retrying. "\n                 "No local database is used. Reference: "+reference)\n'''
if new not in app:
    if old not in app:
        raise RuntimeError("show_error marker not found")
    app = app.replace(old, new, 1)
app_path.write_text(app, encoding="utf-8")

# -----------------------------
# Build + wording
# -----------------------------
ui_path = ROOT / "gp_ui.py"
ui = ui_path.read_text(encoding="utf-8")
if 'BUILD = "GP-CLOUD-v16.8"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.7"' not in ui:
        raise RuntimeError("build marker not found")
    ui = ui.replace('BUILD = "GP-CLOUD-v16.7"', 'BUILD = "GP-CLOUD-v16.8"', 1)
ui_path.write_text(ui, encoding="utf-8")

# -----------------------------
# Regression coverage
# -----------------------------
test_path = ROOT / "tests/test_core_and_ocr.py"
test = test_path.read_text(encoding="utf-8")
extra = '''\n\ndef test_admin_can_create_user_and_duplicate_is_safe_error():\n    s=Store.for_tests();pw="Test-Password-2026";s.initialize(password=pw);t=s.login("admin",pw)\n    s.create_user(t,pw,"store1","Another-Test-Password-2026","store","Store User")\n    users={u["username"]:u for u in s.list_users(t)}\n    assert users["store1"]["role"]=="store"\n    assert users["store1"]["display_name"]=="Store User"\n    try:\n        s.create_user(t,pw,"store1","Another-Test-Password-2026","store","Store User")\n    except AppError as error:\n        assert str(error)=="Username already exists"\n    else:\n        raise AssertionError("duplicate username must fail")\n\ndef test_safe_error_message_exposes_only_exception_class_and_sqlstate():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'safe_detail=kind+(" / SQLSTATE "+sqlstate if sqlstate else "")' in source\n    assert 'repr(error)' not in source\n'''
if 'def test_admin_can_create_user_and_duplicate_is_safe_error()' not in test:
    test += extra

test_path.write_text(test, encoding="utf-8")

print("v16.8 user creation resilience applied")
