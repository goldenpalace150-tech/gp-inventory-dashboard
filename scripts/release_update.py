from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
app_path=ROOT/'inventory_tracker.py'
app=app_path.read_text(encoding='utf-8')

replacements=[
('''            if st.form_submit_button(t("Delete invoice"),type="primary",disabled=not confirmed):\n                try:store.delete_invoice(token,password,selected);success(message="Deleted")\n                except Exception as error:show_error(error)\n''',
'''            if st.form_submit_button(t("Delete invoice"),type="primary"):\n                try:\n                    if not confirmed:raise AppError("Confirm delete")\n                    store.delete_invoice(token,password,selected);success(message="Deleted")\n                except Exception as error:show_error(error)\n'''),
('''            if st.form_submit_button(t("Delete movement"),type="primary",disabled=not confirmed):\n                try:store.delete_movement(token,password,selected);success(message="Deleted")\n                except Exception as error:show_error(error)\n''',
'''            if st.form_submit_button(t("Delete movement"),type="primary"):\n                try:\n                    if not confirmed:raise AppError("Confirm delete")\n                    store.delete_movement(token,password,selected);success(message="Deleted")\n                except Exception as error:show_error(error)\n'''),
('''            if st.form_submit_button(t("Delete movement history report"),type="primary",disabled=not confirmed):\n                try:store.delete_movement_history(token,password);success(message="Deleted")\n                except Exception as error:show_error(error)\n''',
'''            if st.form_submit_button(t("Delete movement history report"),type="primary"):\n                try:\n                    if not confirmed:raise AppError("Confirm delete")\n                    store.delete_movement_history(token,password);success(message="Deleted")\n                except Exception as error:show_error(error)\n''')]

for old,new in replacements:
    if new in app:continue
    if old not in app:raise RuntimeError('delete form marker not found')
    app=app.replace(old,new,1)
app_path.write_text(app,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.12"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.11"' not in ui:raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.11"','BUILD = "GP-CLOUD-v16.12"',1)
ui_path.write_text(ui,encoding='utf-8')

test_path=ROOT/'tests/test_core_and_ocr.py'
test=test_path.read_text(encoding='utf-8')
extra='''\n\ndef test_delete_confirmation_does_not_disable_form_submit_buttons():\n    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()\n    assert 'Delete invoice"),type="primary",disabled=not confirmed' not in source\n    assert 'Delete movement"),type="primary",disabled=not confirmed' not in source\n    assert 'Delete movement history report"),type="primary",disabled=not confirmed' not in source\n    assert source.count('if not confirmed:raise AppError("Confirm delete")') >= 3\n'''
if 'def test_delete_confirmation_does_not_disable_form_submit_buttons()' not in test:
    test += extra
test_path.write_text(test,encoding='utf-8')

print('v16.12 delete-form confirmation deadlock fixed')
