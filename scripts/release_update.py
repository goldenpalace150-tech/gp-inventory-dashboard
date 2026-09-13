from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

worker_path=ROOT/'invoice_ocr_worker.py'
worker=worker_path.read_text(encoding='utf-8')
worker=worker.replace('BUILD = "GP-OCR-WAREHOUSE-v16.15"','BUILD = "GP-OCR-WAREHOUSE-v16.16"',1)

anchor='_engine = None\n_arabic_engine = None\n\n\n'
insert='''_engine = None\n_arabic_engine = None\n\n# Streamlit Cloud may expose site-packages as read-only. RapidOCR normally\n# resolves/downloads ONNX files under site-packages/rapidocr/models. Force all\n# OCR model files into a writable process cache instead.\ndef _rapidocr_model_root():\n    root=Path(os.environ.get("GP_RAPIDOCR_MODEL_ROOT","/tmp/gp_rapidocr_models"))\n    root.mkdir(parents=True,exist_ok=True)\n    return str(root)\n\n\n'''
if '_rapidocr_model_root' not in worker:
    if anchor not in worker:raise RuntimeError('OCR engine globals marker not found')
    worker=worker.replace(anchor,insert,1)

needle='        "Global.use_cls": False,\n        "Global.max_side_len": 900,\n'
replacement='        "Global.use_cls": False,\n        "Global.model_root_dir": _rapidocr_model_root(),\n        "Global.max_side_len": 900,\n'
if '"Global.model_root_dir": _rapidocr_model_root()' not in worker:
    if worker.count(needle)!=2:raise RuntimeError('expected two RapidOCR parameter blocks')
    worker=worker.replace(needle,replacement)
worker_path.write_text(worker,encoding='utf-8')

gp_path=ROOT/'gp_ocr.py'
gp=gp_path.read_text(encoding='utf-8')
gp=gp.replace('OCR_BUILD = "GP-OCR-WAREHOUSE-v16.15"','OCR_BUILD = "GP-OCR-WAREHOUSE-v16.16"',1)
gp_path.write_text(gp,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.16"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.15"' not in ui:raise RuntimeError('app build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.15"','BUILD = "GP-CLOUD-v16.16"',1)
ui_path.write_text(ui,encoding='utf-8')

test_path=ROOT/'tests/test_core_and_ocr.py'
test=test_path.read_text(encoding='utf-8')
extra='''\n\ndef test_rapidocr_uses_writable_model_root():\n    source=(Path(__file__).resolve().parents[1]/"invoice_ocr_worker.py").read_text()\n    assert 'GP_RAPIDOCR_MODEL_ROOT' in source\n    assert '/tmp/gp_rapidocr_models' in source\n    assert source.count('"Global.model_root_dir": _rapidocr_model_root()')==2\n'''
if 'def test_rapidocr_uses_writable_model_root()' not in test:
    test += extra
test_path.write_text(test,encoding='utf-8')

print('v16.16 writable RapidOCR model root applied')
