from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

store_path = ROOT / "gp_store.py"
store = store_path.read_text(encoding="utf-8")
old = '''    def create_user(self,token,password,username,new_password,role,display_name=""):\n        username=str(username).strip()\n        if not username:raise AppError("Username is required")\n        if len(username)>80:raise AppError("Username is too long")\n        if role not in ("admin","store"):raise AppError("Invalid role")\n        hashed=password_hash(new_password)\n        display_name=str(display_name or username)[:120]\n        for attempt in range(2):\n            try:\n                with self.engine.begin() as c:\n                    self._lock(c);actor=self._actor(c,token,password,admin=True);t=self.tables["app_users"]\n                    if c.execute(select(t.c.username).where(t.c.username==username)).first():raise AppError("Username already exists")\n                    c.execute(insert(t).values(username=username,display_name=display_name,role=role,password_hash=hashed,\n                        active=True,failed_attempts=0,created_at=utcnow()))\n                    self._audit(c,actor["username"],"CREATE_USER",{"username":username,"role":role});self._touch(c)\n                return\n'''
new = '''    def create_user(self,token,username,new_password,role,display_name=""):\n        username=str(username).strip()\n        if not username:raise AppError("Username is required")\n        if len(username)>80:raise AppError("Username is too long")\n        if role not in ("admin","store"):raise AppError("Invalid role")\n        hashed=password_hash(new_password)\n        display_name=str(display_name or username)[:120]\n        for attempt in range(2):\n            try:\n                with self.engine.begin() as c:\n                    self._lock(c);actor=self._actor(c,token,admin=True);t=self.tables["app_users"]\n                    if c.execute(select(t.c.username).where(t.c.username==username)).first():raise AppError("Username already exists")\n                    c.execute(insert(t).values(username=username,display_name=display_name,role=role,password_hash=hashed,\n                        active=True,failed_attempts=0,created_at=utcnow()))\n                    self._audit(c,actor["username"],"CREATE_USER",{"username":username,"role":role});self._touch(c)\n                return\n'''
if new not in store:
    if old not in store:
        raise RuntimeError("create_user marker not found")
    store = store.replace(old, new, 1)
store_path.write_text(store, encoding="utf-8")

app_path = ROOT / "inventory_tracker.py"
app = app_path.read_text(encoding="utf-8")
old = '''                newpass=st.text_input(t("New password"),type="password",key="password_newuser")\n                password=st.text_input(t("Approval password"),type="password",key="password_useradmin")\n                if st.form_submit_button(t("Save"),type="primary"):\n                    try:store.create_user(token,password,username,newpass,role,display);success()\n                    except Exception as error:show_error(error)\n'''
new = '''                newpass=st.text_input(t("New password"),type="password",key="password_newuser")\n                if st.form_submit_button(t("Save"),type="primary"):\n                    try:store.create_user(token,username,newpass,role,display);success()\n                    except Exception as error:show_error(error)\n'''
if new not in app:
    if old not in app:
        raise RuntimeError("new user form marker not found")
    app = app.replace(old, new, 1)
app_path.write_text(app, encoding="utf-8")

ui_path = ROOT / "gp_ui.py"
ui = ui_path.read_text(encoding="utf-8")
if 'BUILD = "GP-CLOUD-v16.10"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.9"' not in ui:
        raise RuntimeError("build marker not found")
    ui = ui.replace('BUILD = "GP-CLOUD-v16.9"', 'BUILD = "GP-CLOUD-v16.10"', 1)
ui_path.write_text(ui, encoding="utf-8")

# Update every test call to the new create_user signature.
for rel in ["tests/test_store.py", "tests/test_core_and_ocr.py"]:
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    text = text.replace('s.create_user(t,"admin-bootstrap","a","1","store","A")', 's.create_user(t,"a","1","store","A")')
    text = text.replace('s.create_user(t,"admin-bootstrap","user name","","store","Blank Password")', 's.create_user(t,"user name","","store","Blank Password")')
    text = text.replace('s.create_user(t,"bootstrap",username,"p","store",username)', 's.create_user(t,username,"p","store",username)')
    text = text.replace('s.create_user(t,PASS,"store",PASS,"store")', 's.create_user(t,"store",PASS,"store")')
    text = text.replace('s.create_user(t,PASS,"hacker",PASS,"admin")', 's.create_user(t,"hacker",PASS,"admin")')
    text = text.replace('s.create_user(t,pw,"store1","Another-Test-Password-2026","store","Store User")', 's.create_user(t,"store1","Another-Test-Password-2026","store","Store User")')
    p.write_text(text, encoding="utf-8")

p = ROOT / "tests/test_core_and_ocr.py"
test = p.read_text(encoding="utf-8")
extra = '''\n\ndef test_new_user_form_has_no_approval_password_and_backend_uses_session_only():\n    app=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    store=(Path(__file__).resolve().parents[1]/"gp_store.py").read_text()\n    assert 'key="password_useradmin"' not in app\n    assert 'store.create_user(token,username,newpass,role,display)' in app\n    assert 'def create_user(self,token,username,new_password,role,display_name=""):' in store\n    assert 'actor=self._actor(c,token,admin=True)' in store\n'''
if 'def test_new_user_form_has_no_approval_password_and_backend_uses_session_only()' not in test:
    test += extra
p.write_text(test, encoding="utf-8")

print("v16.10b user creation no-approval flow applied")
