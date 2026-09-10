from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

app = ROOT / "inventory_tracker.py"
text = app.read_text(encoding="utf-8")
old = '''def sidebar_navigation(store,token,actor,stamp):
    nav=["Dashboard","Stock","Invoices","Movements","Analysis","Closing","Settings"]
    desired=st.session_state.get("page","Dashboard")
    if desired not in nav:desired="Dashboard"
    if st.session_state.get("sidebar_nav")!=desired:
        st.session_state["sidebar_nav"]=desired
    icons={"Dashboard":"⌂","Stock":"▦","Invoices":"▤","Movements":"⇄","Analysis":"◫","Closing":"✓","Settings":"⚙"}
    with st.sidebar:
'''
new = '''def sidebar_navigation(store,token,actor,stamp):
    nav=["Dashboard","Stock","Invoices","Movements","Analysis","Closing","Settings"]
    desired=st.session_state.get("page","Dashboard")
    if desired not in nav:desired="Dashboard"
    # Initialize the radio only once. Do not overwrite sidebar_nav on every rerun:
    # a widget click updates sidebar_nav before this function executes.
    if "sidebar_nav" not in st.session_state:
        st.session_state["sidebar_nav"]=desired
    icons={"Dashboard":"⌂","Stock":"▦","Invoices":"▤","Movements":"⇄","Analysis":"◫","Closing":"✓","Settings":"⚙"}
    with st.sidebar:
'''
if old not in text:
    if new not in text:
        raise RuntimeError("sidebar navigation marker not found")
else:
    text = text.replace(old, new, 1)
app.write_text(text, encoding="utf-8")

ui = ROOT / "gp_ui.py"
ui_text = ui.read_text(encoding="utf-8")
ui_text = ui_text.replace('BUILD = "GP-CLOUD-v15"', 'BUILD = "GP-CLOUD-v15.1"', 1)
ui.write_text(ui_text, encoding="utf-8")

# Update the regression test so this exact failure cannot return.
test = ROOT / "tests/test_core_and_ocr.py"
t = test.read_text(encoding="utf-8")
marker = '''    assert "with st.sidebar:" in source and "sidebar_navigation" in source
    assert "use_container_width" not in source
'''
replacement = '''    assert "with st.sidebar:" in source and "sidebar_navigation" in source
    assert 'if "sidebar_nav" not in st.session_state:' in source
    assert 'st.session_state.get("sidebar_nav")!=desired' not in source
    assert "use_container_width" not in source
'''
if replacement not in t:
    if marker not in t:
        raise RuntimeError("sidebar test marker not found")
    t = t.replace(marker, replacement, 1)
test.write_text(t, encoding="utf-8")

print("v15.1 sidebar navigation fix applied")
