from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

app = ROOT / "inventory_tracker.py"
text = app.read_text(encoding="utf-8")

old_sidebar = '''def sidebar_navigation(store,token,actor,stamp):
    nav=["Dashboard","Stock","Invoices","Movements","Analysis","Closing","Settings"]
    desired=st.session_state.get("page","Dashboard")
    if desired not in nav:desired="Dashboard"
    if st.session_state.get("sidebar_nav")!=desired:
        st.session_state["sidebar_nav"]=desired
    icons={"Dashboard":"⌂","Stock":"▦","Invoices":"▤","Movements":"⇄","Analysis":"◫","Closing":"✓","Settings":"⚙"}
    with st.sidebar:
'''

intermediate_sidebar = '''def sidebar_navigation(store,token,actor,stamp):
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

new_sidebar = '''def sidebar_navigation(store,token,actor,stamp):
    nav=["Dashboard","Stock","Invoices","Movements","Analysis","Closing","Settings"]
    # Streamlit updates sidebar_nav before each rerun when the user clicks the radio.
    # Never overwrite that click from the older page value. Programmatic navigation
    # uses nav_request and is consumed here before the radio widget is created.
    requested=st.session_state.pop("nav_request",None)
    desired=requested if requested in nav else st.session_state.get("page","Dashboard")
    if desired not in nav:desired="Dashboard"
    if "sidebar_nav" not in st.session_state or requested in nav:
        st.session_state["sidebar_nav"]=desired
    icons={"Dashboard":"⌂","Stock":"▦","Invoices":"▤","Movements":"⇄","Analysis":"◫","Closing":"✓","Settings":"⚙"}
    with st.sidebar:
'''

if new_sidebar not in text:
    if old_sidebar in text:
        text = text.replace(old_sidebar, new_sidebar, 1)
    elif intermediate_sidebar in text:
        text = text.replace(intermediate_sidebar, new_sidebar, 1)
    else:
        raise RuntimeError("sidebar navigation marker not found")

# Dashboard quick actions run after the sidebar radio has already been instantiated.
# They therefore request navigation for the next rerun instead of mutating the
# sidebar widget state directly.
for target in ("Invoices", "Movements", "Stock", "Analysis"):
    old = f'st.session_state["page"]="{target}"; st.rerun()'
    new = f'st.session_state["nav_request"]="{target}"; st.rerun()'
    if new not in text:
        if old not in text:
            raise RuntimeError(f"quick navigation marker not found: {target}")
        text = text.replace(old, new, 1)

app.write_text(text, encoding="utf-8")

ui = ROOT / "gp_ui.py"
ui_text = ui.read_text(encoding="utf-8")
if 'BUILD = "GP-CLOUD-v15.1"' not in ui_text:
    if 'BUILD = "GP-CLOUD-v15"' not in ui_text:
        raise RuntimeError("build marker not found")
    ui_text = ui_text.replace('BUILD = "GP-CLOUD-v15"', 'BUILD = "GP-CLOUD-v15.1"', 1)
ui.write_text(ui_text, encoding="utf-8")

# Guard the exact regression: a sidebar click must remain the source of truth,
# while dashboard quick actions must still be able to navigate programmatically.
test = ROOT / "tests/test_core_and_ocr.py"
t = test.read_text(encoding="utf-8")
marker = '''    assert "with st.sidebar:" in source and "sidebar_navigation" in source
    assert "use_container_width" not in source
'''
replacement = '''    assert "with st.sidebar:" in source and "sidebar_navigation" in source
    assert 'requested=st.session_state.pop("nav_request",None)' in source
    assert 'if "sidebar_nav" not in st.session_state or requested in nav:' in source
    assert 'st.session_state.get("sidebar_nav")!=desired' not in source
    assert 'st.session_state["nav_request"]="Invoices"' in source
    assert 'st.session_state["nav_request"]="Movements"' in source
    assert 'st.session_state["nav_request"]="Stock"' in source
    assert 'st.session_state["nav_request"]="Analysis"' in source
    assert "use_container_width" not in source
'''
if replacement not in t:
    if marker not in t:
        raise RuntimeError("sidebar test marker not found")
    t = t.replace(marker, replacement, 1)
test.write_text(t, encoding="utf-8")

print("v15.1 sidebar navigation fix applied")
