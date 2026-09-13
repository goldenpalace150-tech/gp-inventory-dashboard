from pathlib import Path

path = Path('invoice_ocr_worker.py')
text = path.read_text(encoding='utf-8')
marker = 'GP_RAPIDOCR_WRITABLE_MODEL_ROOT_V1'
if marker in text:
    print('RapidOCR writable model root fix already applied')
    raise SystemExit(0)

old_build = 'BUILD = "GP-OCR-WAREHOUSE-v16.15"'
if old_build in text:
    text = text.replace(old_build, 'BUILD = "GP-OCR-WAREHOUSE-v16.16"', 1)

anchor = '_engine = None\n_arabic_engine = None\n\n\n'
insert = '''_engine = None\n_arabic_engine = None\n\n# GP_RAPIDOCR_WRITABLE_MODEL_ROOT_V1\n# Streamlit Community Cloud installs Python packages under a read-only venv.\n# RapidOCR defaults to downloading missing ONNX models into site-packages/rapidocr/models,\n# which raises PermissionError there. Force all automatic model downloads into /tmp instead.\ndef _rapidocr_model_root():\n    root = Path(os.environ.get("GP_RAPIDOCR_MODEL_ROOT", "/tmp/gp_rapidocr_models"))\n    root.mkdir(parents=True, exist_ok=True)\n    return str(root)\n\n\n'''
if anchor not in text:
    raise SystemExit('Could not find engine globals anchor')
text = text.replace(anchor, insert, 1)

needle = '        "Global.use_cls": False,\n        "Global.max_side_len": 900,\n'
replacement = '        "Global.use_cls": False,\n        "Global.model_root_dir": _rapidocr_model_root(),\n        "Global.max_side_len": 900,\n'
count = text.count(needle)
if count != 2:
    raise SystemExit(f'Expected 2 RapidOCR parameter blocks, found {count}')
text = text.replace(needle, replacement)

path.write_text(text, encoding='utf-8')
print('Applied writable RapidOCR model root to both OCR engines')
