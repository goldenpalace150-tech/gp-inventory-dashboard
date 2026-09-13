from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

req_path=ROOT/'requirements.txt'
req=req_path.read_text(encoding='utf-8')
if 'rapidocr==3.8.4' not in req:
    if 'rapidocr==3.9.2' not in req:raise RuntimeError('RapidOCR pin not found')
    req=req.replace('rapidocr==3.9.2','rapidocr==3.8.4',1)
req_path.write_text(req,encoding='utf-8')

worker_path=ROOT/'invoice_ocr_worker.py'
worker=worker_path.read_text(encoding='utf-8')
worker=worker.replace('BUILD = "GP-OCR-WAREHOUSE-v16.6"','BUILD = "GP-OCR-WAREHOUSE-v16.15"',1)
worker_path.write_text(worker,encoding='utf-8')

gp_path=ROOT/'gp_ocr.py'
gp=gp_path.read_text(encoding='utf-8')
gp=gp.replace('OCR_BUILD = "GP-OCR-WAREHOUSE-v16.6"','OCR_BUILD = "GP-OCR-WAREHOUSE-v16.15"',1)
gp_path.write_text(gp,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.15"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.14"' not in ui:raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.14"','BUILD = "GP-CLOUD-v16.15"',1)
ui_path.write_text(ui,encoding='utf-8')

# Force CI to instantiate both RapidOCR engines so packaged model readability is
# checked before promotion, not first discovered by a user scan.
test_path=ROOT/'tests/test_core_and_ocr.py'
test=test_path.read_text(encoding='utf-8')
extra='''\n\ndef test_rapidocr_pin_is_refreshed_for_model_permissions():\n    req=(Path(__file__).resolve().parents[1]/"requirements.txt").read_text()\n    assert "rapidocr==3.8.4" in req\n'''
if 'def test_rapidocr_pin_is_refreshed_for_model_permissions()' not in test:
    test += extra
test_path.write_text(test,encoding='utf-8')

print('v16.15 RapidOCR package refresh applied')
