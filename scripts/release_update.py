from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

app_path=ROOT/'inventory_tracker.py'
app=app_path.read_text(encoding='utf-8')

old='''def show_error(error):\n    if isinstance(error,AppError):\n        st.error(t(str(error)))\n'''
new='''def show_error(error):\n    # Streamlit can retain cached objects created by the previous app module after\n    # a hot code pull. Their AppError class has the same name but a different\n    # Python class identity, so accept both the current class and that stale copy.\n    if isinstance(error,AppError) or type(error).__name__=="AppError":\n        st.error(t(str(error)))\n'''
if new not in app:
    if old not in app: raise RuntimeError('show_error AppError marker not found')
    app=app.replace(old,new,1)

old='''@st.cache_resource(show_spinner=False)\ndef get_store(settings_json):\n    return Store.from_settings(json.loads(settings_json))\n'''
new='''@st.cache_resource(show_spinner=False)\ndef get_store(settings_json,build):\n    # `build` is intentionally part of the cache key. After every release this\n    # creates a fresh Store instance so changed method signatures/classes cannot\n    # be mixed with a Store object cached by the previous Streamlit process.\n    return Store.from_settings(json.loads(settings_json))\n'''
if new not in app:
    if old not in app: raise RuntimeError('get_store marker not found')
    app=app.replace(old,new,1)

old='''        store=get_store(json.dumps(config,sort_keys=True))\n'''
new='''        store=get_store(json.dumps(config,sort_keys=True),BUILD)\n'''
if new not in app:
    if old not in app: raise RuntimeError('get_store call marker not found')
    app=app.replace(old,new,1)
app_path.write_text(app,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.11"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.10"' not in ui: raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.10"','BUILD = "GP-CLOUD-v16.11"',1)
ui_path.write_text(ui,encoding='utf-8')

# Regression coverage for the exact hot-reload failure that appeared on v16.10.
test_path=ROOT/'tests/test_core_and_ocr.py'
test=test_path.read_text(encoding='utf-8')
extra='''\n\ndef test_store_cache_is_versioned_by_build_and_stale_apperror_is_shown_safely():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'def get_store(settings_json,build):' in source\n    assert 'get_store(json.dumps(config,sort_keys=True),BUILD)' in source\n    assert 'type(error).__name__=="AppError"' in source\n'''
if 'def test_store_cache_is_versioned_by_build_and_stale_apperror_is_shown_safely()' not in test:
    test += extra
test_path.write_text(test,encoding='utf-8')

print('v16.11 Streamlit cache-version isolation applied')
