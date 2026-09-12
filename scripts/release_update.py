from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

store_path = ROOT / "gp_store.py"
store = store_path.read_text(encoding="utf-8")

old = '''def password_hash(password: str, *, enforce_policy=True) -> str:\n    if enforce_policy and (len(password) < 12 or len(password) > 256):\n        raise AppError("Use a password of 12 to 256 characters")\n    salt = secrets.token_bytes(16)\n    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF_ROUNDS)\n'''
new = '''def password_hash(password: str, *, enforce_policy=True) -> str:\n    # No password complexity/length policy. Store exactly what the operator enters.\n    password = str(password)\n    salt = secrets.token_bytes(16)\n    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF_ROUNDS)\n'''
if new not in store:
    if old not in store:
        raise RuntimeError("password_hash marker not found")
    store = store.replace(old, new, 1)

old = '''        algorithm, rounds, salt, target = encoded.split("$")\n        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 2_000_000 or len(password) > 256:\n            return False\n        value = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(rounds))\n'''
new = '''        algorithm, rounds, salt, target = encoded.split("$")\n        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 2_000_000:\n            return False\n        value = hashlib.pbkdf2_hmac("sha256", str(password).encode(), base64.b64decode(salt), int(rounds))\n'''
if new not in store:
    if old not in store:
        raise RuntimeError("password_matches marker not found")
    store = store.replace(old, new, 1)

old = '''                if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", username):\n                    raise AppError("Use 3 to 80 letters, digits, dots or underscores for usernames")\n                ZoneInfo(timezone_name)\n'''
new = '''                username = str(username).strip()\n                if not username:\n                    raise AppError("Username is required")\n                if len(username) > 80:\n                    raise AppError("Username is too long")\n                ZoneInfo(timezone_name)\n'''
if new not in store:
    if old not in store:
        raise RuntimeError("bootstrap username marker not found")
    store = store.replace(old, new, 1)

old = '''    def create_user(self,token,password,username,new_password,role,display_name=""):\n        username=str(username).strip()\n        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}",username):raise AppError("Use 3 to 80 letters, digits, dots or underscores for usernames")\n        if role not in ("admin","store"):raise AppError("Invalid role")\n        hashed=password_hash(new_password)\n'''
new = '''    def create_user(self,token,password,username,new_password,role,display_name=""):\n        username=str(username).strip()\n        if not username:raise AppError("Username is required")\n        if len(username)>80:raise AppError("Username is too long")\n        if role not in ("admin","store"):raise AppError("Invalid role")\n        hashed=password_hash(new_password)\n'''
if new not in store:
    if old not in store:
        raise RuntimeError("create_user username marker not found")
    store = store.replace(old, new, 1)

store_path.write_text(store, encoding="utf-8")

ui_path = ROOT / "gp_ui.py"
ui = ui_path.read_text(encoding="utf-8")
if 'BUILD = "GP-CLOUD-v16.9"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.8"' not in ui:
        raise RuntimeError("build marker not found")
    ui = ui.replace('BUILD = "GP-CLOUD-v16.8"', 'BUILD = "GP-CLOUD-v16.9"', 1)
labels = '''\n\n# ---- v16.9 simple user credentials ----\nAR.update({\n    "Username is required": "اسم المستخدم مطلوب.",\n    "Username is too long": "اسم المستخدم طويل جداً.",\n})\n'''
if '"Username is required":' not in ui:
    marker='\ndef set_language('
    pos=ui.find(marker)
    if pos < 0:
        raise RuntimeError("language marker not found")
    ui = ui[:pos] + labels + ui[pos:]
ui_path.write_text(ui, encoding="utf-8")

test_path = ROOT / "tests/test_store.py"
test = test_path.read_text(encoding="utf-8")
old = '''def test_no_default_password():\n    s=Store.for_tests()\n    with pytest.raises(AppError):s.initialize(password="")\n    with pytest.raises(AppError):s.initialize(password="123")\n'''
new = '''def test_simple_passwords_are_allowed_for_users():\n    s=Store.for_tests();s.initialize(password="admin-bootstrap")\n    t=s.login("admin","admin-bootstrap")\n    s.create_user(t,"admin-bootstrap","a","1","store","A")\n    assert s.login("a","1")\n    s.create_user(t,"admin-bootstrap","user name","","store","Blank Password")\n    assert s.login("user name","")\n'''
if new not in test:
    if old not in test:
        raise RuntimeError("password policy test marker not found")
    test = test.replace(old, new, 1)

test += '''\n\ndef test_usernames_have_no_character_or_minimum_length_rule():\n    s=Store.for_tests();s.initialize(password="bootstrap")\n    t=s.login("admin","bootstrap")\n    for username in ["x","موظف مخزن","user name","@"]:\n        s.create_user(t,"bootstrap",username,"p","store",username)\n        assert s.login(username,"p")\n'''

test_path.write_text(test, encoding="utf-8")

print("v16.9 simple usernames/passwords applied")
