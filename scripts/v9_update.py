from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Missing update marker: {label}")
    return text.replace(old, new, 1)


def regex_once(text, pattern, replacement, label):
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected one match for {label}, got {count}")
    return updated


# ---------- gp_core: code is the canonical warehouse identity ----------
path = ROOT / "gp_core.py"
core = path.read_text(encoding="utf-8")
if "def item_link_key(" not in core:
    marker = "\ndef split_movement_item(value):"
    helper = '''\ndef item_link_key(code, name):
    """Stable item link: code first, normalized name only for legacy movement rows."""
    normalized_code = normalize_item_code(code)
    if normalized_code:
        return f"CODE:{normalized_code}"
    return f"NAME:{normalize_item_name(name)}"
\n'''
    core = replace_once(core, marker, helper + marker, "item_link_key")

new_stock_reader = '''def read_stock_report(file_bytes):
    """Read the current warehouse report. Item code is mandatory and canonical."""
    excel = pd.ExcelFile(io.BytesIO(file_bytes))
    for sheet_name in excel.sheet_names:
        for header_row in (0, 1, 2):
            candidate = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=header_row, dtype=object)
            columns = {str(column).strip(): column for column in candidate.columns}
            name_col = next((columns[key] for key in columns if 'اسم المادة' in key), None)
            qty_col = next((columns[key] for key in columns if key == 'الكمية'), None)
            code_col = next((columns[key] for key in columns if 'رمز المادة' in key), None)
            if name_col is None or qty_col is None or code_col is None:
                continue
            result = pd.DataFrame({
                'رمز المادة': candidate[code_col].map(normalize_item_code),
                'اسم المادة': candidate[name_col].where(candidate[name_col].notna(), '').astype(str).str.strip().str.strip('"'),
                'الكمية': pd.to_numeric(candidate[qty_col], errors='coerce').fillna(0),
            })
            # Ignore completely blank/footer rows, but never accept half-linked item rows.
            result = result[(result['رمز المادة'].ne('')) | (result['اسم المادة'].ne(''))].copy()
            if result.empty:
                raise ValueError('تقرير جرد المستودع لا يحتوي على أصناف.')
            missing_code = result['رمز المادة'].eq('')
            missing_name = result['اسم المادة'].eq('')
            if missing_code.any() or missing_name.any():
                raise ValueError('كل صنف في تقرير المستودع يجب أن يحتوي على رمز المادة واسم المادة.')
            duplicates = result.loc[result['رمز المادة'].duplicated(keep=False), 'رمز المادة'].drop_duplicates().tolist()
            if duplicates:
                preview = ', '.join(duplicates[:5])
                raise ValueError(f'رمز المادة يجب أن يكون فريداً في تقرير المستودع. رموز مكررة: {preview}')
            result['مفتاح المطابقة'] = result.apply(lambda row: item_link_key(row['رمز المادة'], row['اسم المادة']), axis=1)
            result['مفتاح المخزون'] = result['رمز المادة'].map(lambda code: f'CODE:{code}')
            return result.reset_index(drop=True)
    raise ValueError('لم يتم العثور على أعمدة رمز المادة واسم المادة والكمية في تقرير جرد المستودع.')

'''
core = regex_once(core, r"def read_stock_report\(file_bytes\):.*?(?=def read_movement_report\(file_bytes\):)", new_stock_reader, "read_stock_report")
core = core.replace("movement['مفتاح المطابقة'] = movement['اسم المادة'].map(normalize_item_name)",
                    "movement['مفتاح المطابقة'] = movement.apply(lambda row: item_link_key(row['رمز المادة'], row['اسم المادة']), axis=1)")
analysis_marker = "    movement_df = movement_df.copy()\n    movement_df['التاريخ'] = pd.to_datetime(movement_df['التاريخ'], errors='coerce')"
analysis_replacement = "    movement_df = movement_df.copy()\n    stock_df = stock_df.copy()\n    movement_df['مفتاح المطابقة'] = movement_df.apply(lambda row: item_link_key(row.get('رمز المادة', ''), row.get('اسم المادة', '')), axis=1)\n    stock_df['مفتاح المطابقة'] = stock_df.apply(lambda row: item_link_key(row.get('رمز المادة', ''), row.get('اسم المادة', '')), axis=1)\n    movement_df['التاريخ'] = pd.to_datetime(movement_df['التاريخ'], errors='coerce')"
core = replace_once(core, analysis_marker, analysis_replacement, "analysis code linking")
new_unique = '''def ensure_unique_stock_keys(stock_df):
    stock_df = stock_df.copy()
    if 'رمز المادة' not in stock_df.columns or 'اسم المادة' not in stock_df.columns:
        raise ValueError('تقرير المستودع يجب أن يحتوي على رمز المادة واسم المادة.')
    stock_df['رمز المادة'] = stock_df['رمز المادة'].map(normalize_item_code)
    if stock_df['رمز المادة'].eq('').any():
        raise ValueError('كل صنف في المستودع يجب أن يحتوي على رمز مادة.')
    duplicates = stock_df.loc[stock_df['رمز المادة'].duplicated(keep=False), 'رمز المادة'].drop_duplicates().tolist()
    if duplicates:
        raise ValueError('رمز المادة مكرر في المستودع: ' + ', '.join(duplicates[:5]))
    stock_df['مفتاح المطابقة'] = stock_df.apply(lambda row: item_link_key(row['رمز المادة'], row['اسم المادة']), axis=1)
    stock_df['مفتاح المخزون'] = stock_df['رمز المادة'].map(lambda code: f'CODE:{code}')
    return stock_df

'''
core = regex_once(core, r"def ensure_unique_stock_keys\(stock_df\):.*?(?=\nCOL_CODE =)", new_unique, "ensure_unique_stock_keys")
core = core.replace('تغطية المخزون بالأيام', 'تغطية المستودع بالأيام')
core = core.replace('مخزون الأمان', 'رصيد الأمان')
path.write_text(core, encoding="utf-8")


# ---------- gp_store: persist code-based match keys ----------
path = ROOT / "gp_store.py"
store = path.read_text(encoding="utf-8")
store = store.replace("normalize_item_name, normalize_item_code, ensure_unique_stock_keys,",
                      "normalize_item_name, normalize_item_code, item_link_key, ensure_unique_stock_keys,")
store = store.replace("match_key=normalize_item_name(name),updated_at=utcnow()",
                      "match_key=item_link_key(code,name),updated_at=utcnow()")
store = store.replace('COL_USER:r["username"],COL_NOTE:r["reason"],COL_MATCH:normalize_item_name(r["item_name"])})',
                      'COL_USER:r["username"],COL_NOTE:r["reason"],COL_MATCH:item_link_key(r["item_code"],r["item_name"])})')
path.write_text(store, encoding="utf-8")


# ---------- gp_invoice: canonical code -> name pairing everywhere ----------
path = ROOT / "gp_invoice.py"
path.write_text('''"""Exact invoice matching against the current warehouse code master."""
import pandas as pd
from gp_core import COL_CODE, COL_NAME, COL_KEY, normalize_item_code
from gp_store import AppError, decimal_qty


def canonicalize_invoice_rows(items, stock, *, drop_unknown=False):
    """Use item code as the master identity and always restore its canonical name."""
    if stock is None or stock.empty:
        raise AppError("No stock")
    indexed = {}
    for _, row in stock.iterrows():
        code = normalize_item_code(row.get(COL_CODE, ""))
        if not code:
            raise AppError("Warehouse item code master is incomplete")
        if code in indexed:
            raise AppError(f"Duplicate warehouse item code: {code}")
        indexed[code] = row
    canonical = []
    ignored = []
    for position, item in enumerate(items or [], 1):
        if not isinstance(item, dict):
            if drop_unknown:
                continue
            raise AppError(f"Row {position}: invalid item row")
        code = normalize_item_code(item.get("item_code", ""))
        value = item.get("quantity")
        supplied_name = str(item.get("item_name", "") or "").strip()
        if not code and not supplied_name and (value is None or pd.isna(value)):
            continue
        if not code or code not in indexed:
            if drop_unknown:
                if code:
                    ignored.append(code)
                continue
            raise AppError(f"Row {position}: item code is not in the current warehouse report")
        row = indexed[code]
        canonical.append({
            "item_code": code,
            "item_name": str(row[COL_NAME]),
            "quantity": value,
        })
    return canonical, ignored


def match_invoice_lines(items, stock, movement_type):
    if movement_type not in ("IN", "OUT"):
        raise AppError("Select IN or OUT")
    canonical, _ = canonicalize_invoice_rows(items, stock, drop_unknown=False)
    if not canonical:
        raise AppError("No valid movement lines")
    stock_by_code = {normalize_item_code(row[COL_CODE]): row for _, row in stock.iterrows()}
    changes = []
    for position, item in enumerate(canonical, 1):
        qty = decimal_qty(item.get("quantity"), positive=True)
        row = stock_by_code[item["item_code"]]
        changes.append({"item_key": str(row[COL_KEY]), "movement_type": movement_type, "quantity": qty})
    return changes
''', encoding="utf-8")


# ---------- gp_ocr: discard totals/phone numbers unless they are warehouse codes ----------
path = ROOT / "gp_ocr.py"
ocr = path.read_text(encoding="utf-8")
ocr = ocr.replace('OCR_BUILD = "GP-OCR-ONNX-LITE-v5"', 'OCR_BUILD = "GP-OCR-WAREHOUSE-v9"')
ocr = ocr.replace('OCR_MAX_WORKER_MB = 480', 'OCR_MAX_WORKER_MB = 360')
ocr = ocr.replace('from gp_core import normalize_item_code\n', 'from gp_core import normalize_item_code\nfrom gp_invoice import canonicalize_invoice_rows\n')
new_extract = '''def extract_invoice_data(uploaded_file, stock_df=None):
    """OCR numeric fields, then keep only codes present in the warehouse master."""
    import math

    if stock_df is None or stock_df.empty:
        raise RuntimeError("Upload the current warehouse report with item codes before reading invoices.")
    image_bytes = uploaded_file.getvalue()
    lock = _ocr_scan_lock()
    if not lock.acquire(blocking=False):
        raise RuntimeError("Another invoice scan is running. Try again after it finishes.")
    try:
        result = _run_ocr_worker(image_bytes)
    finally:
        lock.release()

    if len(result.get("items", [])) > 60:
        raise RuntimeError("Too many OCR rows; use manual entry.")
    result.setdefault("warnings", [])
    canonical, ignored = canonicalize_invoice_rows(result.get("items", []), stock_df, drop_unknown=True)
    result["items"] = canonical
    if ignored:
        result["warnings"].append(
            "Ignored OCR numbers that are not item codes in the current warehouse report: " + ", ".join(ignored[:8])
        )
    if not canonical:
        result["warnings"].append("No warehouse item codes were confirmed from the image. Add the rows manually.")

    quantities = []
    for item in canonical:
        quantity = item.get("quantity")
        if quantity is None:
            continue
        try:
            value = float(quantity)
        except (ValueError, TypeError) as error:
            raise RuntimeError("Invalid OCR quantity.") from error
        if not math.isfinite(value) or value <= 0:
            raise RuntimeError("Invalid OCR quantity.")
        item["quantity"] = value
        quantities.append(value)

    printed_total = result.get("printed_total_candidate")
    if printed_total is not None and len(quantities) == len(canonical) and canonical:
        try:
            printed_total = float(printed_total)
            if not math.isclose(sum(quantities), printed_total, abs_tol=0.001):
                result["warnings"].append("Verified warehouse rows do not match the printed quantity total; review quantities.")
        except (TypeError, ValueError):
            pass

    result["image_hash"] = hashlib.sha256(image_bytes).hexdigest()
    result["source_name"] = getattr(uploaded_file, "name", "invoice-photo.jpg")
    return result
'''
ocr = regex_once(ocr, r"def extract_invoice_data\(uploaded_file, stock_df=None\):.*\Z", new_extract, "gp_ocr extract")
path.write_text(ocr, encoding="utf-8")


# ---------- OCR worker: smaller models + only scan the relevant invoice regions ----------
path = ROOT / "invoice_ocr_worker.py"
worker = path.read_text(encoding="utf-8")
worker = worker.replace('BUILD = "GP-OCR-ONNX-LITE-v5"', 'BUILD = "GP-OCR-WAREHOUSE-v9"')
worker = worker.replace('MAX_SOURCE_SIDE = 1800', 'MAX_SOURCE_SIDE = 1200')
new_engine = '''def get_engine():
    global _engine
    if _engine is not None:
        return _engine
    _stage("import_start")
    from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR

    # Numeric/Latin invoice fields do not need the larger multilingual defaults.
    # Mobile PP-OCRv4 models plus one ONNX thread reduce host memory and latency.
    _engine = RapidOCR(params={
        "Global.use_cls": False,
        "Global.max_side_len": 900,
        "Global.text_score": 0.35,
        "EngineConfig.onnxruntime.intra_op_num_threads": 1,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
        "Det.engine_type": EngineType.ONNXRUNTIME,
        "Det.lang_type": LangDet.EN,
        "Det.model_type": ModelType.MOBILE,
        "Det.ocr_version": OCRVersion.PPOCRV4,
        "Det.limit_side_len": 640,
        "Det.limit_type": "max",
        "Rec.engine_type": EngineType.ONNXRUNTIME,
        "Rec.lang_type": LangRec.EN,
        "Rec.model_type": ModelType.MOBILE,
        "Rec.ocr_version": OCRVersion.PPOCRV4,
        "Rec.rec_batch_num": 1,
    })
    _stage("model_load_done")
    return _engine
'''
worker = regex_once(worker, r"def get_engine\(\):.*?(?=\ndef _clean\()", new_engine + "\n", "OCR engine")
worker = worker.replace('    output = engine(array)\n', '    output = engine(array, use_cls=False)\n')
region_code = '''\ndef _run_region(array, region, x0, y0, x1, y1):
    height, width = array.shape[:2]
    left, top = int(width * x0), int(height * y0)
    right, bottom = int(width * x1), int(height * y1)
    crop = array[top:bottom, left:right]
    if crop.size == 0:
        return []
    boxes = run_ocr(crop)
    for box in boxes:
        box["x"] += left
        box["y"] += top
        box["region"] = region
    return boxes


def run_targeted_ocr(array):
    """Scan only code, quantity and summary strips; ignore phones, prices and Arabic names."""
    boxes = []
    boxes.extend(_run_region(array, "code", 0.70, 0.28, 1.00, 0.63))
    boxes.extend(_run_region(array, "qty", 0.17, 0.28, 0.44, 0.63))
    boxes.extend(_run_region(array, "summary", 0.00, 0.58, 0.55, 0.78))
    _stage("targeted_ocr_done", boxes=len(boxes))
    return boxes
'''
if "def run_targeted_ocr(" not in worker:
    worker = replace_once(worker, "\ndef parse_codes(boxes, width, height):", region_code + "\ndef parse_codes(boxes, width, height):", "targeted OCR regions")
worker = worker.replace('    for box in sorted(boxes, key=lambda b: b["y"]):\n        # Codes are in the right-side item-code column in the Golden Palace layout.',
                        '    for box in sorted(boxes, key=lambda b: b["y"]):\n        if box.get("region") not in (None, "code"):\n            continue\n        # Codes are in the right-side item-code column in the Golden Palace layout.')
worker = worker.replace('    for box in boxes:\n        if not (width * 0.18 <= box["x"] <= width * 0.40):',
                        '    for box in boxes:\n        if box.get("region") not in (None, "qty"):\n            continue\n        if not (width * 0.15 <= box["x"] <= width * 0.45):', 1)
worker = worker.replace('    for box in boxes:\n        text = _clean(box["text"]).replace(" ", "").replace(",", ".")',
                        '    for box in boxes:\n        if box.get("region") not in (None, "summary"):\n            continue\n        text = _clean(box["text"]).replace(" ", "").replace(",", ".")', 1)
worker = worker.replace('    boxes = run_ocr(array)\n', '    boxes = run_targeted_ocr(array)\n', 1)
path.write_text(worker, encoding="utf-8")


# ---------- UI: canonical review rows + warehouse terminology ----------
path = ROOT / "inventory_tracker.py"
app = path.read_text(encoding="utf-8")
app = app.replace('read_stock_report,read_movement_report,enrich_stock_codes,build_inventory_analysis,',
                  'read_stock_report,read_movement_report,build_inventory_analysis,')
app = app.replace('from gp_invoice import match_invoice_lines',
                  'from gp_invoice import match_invoice_lines, canonicalize_invoice_rows')
app = app.replace('    ok,_,detail=free_ocr_status()\n',
                  '    ok,_,detail=free_ocr_status()\n    code_master_ready = (not stock.empty and stock[COL_CODE].fillna("").astype(str).str.strip().ne("").all())\n')
app = app.replace('read=a.button(t("Read invoice"),type="primary",disabled=not (uploaded and ok),width="stretch")',
                  'read=a.button(t("Read invoice"),type="primary",disabled=not (uploaded and ok and code_master_ready),width="stretch")')
app = app.replace('            if not ok:st.info("OCR is unavailable on this host. Manual invoice entry remains available.")',
                  '            if not ok:st.info("OCR is unavailable on this host. Manual invoice entry remains available.")\n            if not code_master_ready:st.warning(t("Warehouse code master required"))')
old_rows = '''    rows=payload.get("items") or [{"item_code":"","item_name":"","quantity":None}]
    frame=pd.DataFrame(rows)[["item_code","item_name","quantity"]]
'''
new_rows = '''    rows=payload.get("items") or []
    try:
        rows, ignored_saved = canonicalize_invoice_rows(rows, stock, drop_unknown=True)
    except AppError:
        rows, ignored_saved = [], []
    if ignored_saved:
        st.warning(t("Ignored non-item numbers")+": "+", ".join(ignored_saved[:8]))
    rows=rows or [{"item_code":"","item_name":"","quantity":None}]
    frame=pd.DataFrame(rows)[["item_code","item_name","quantity"]]
'''
app = replace_once(app, old_rows, new_rows, "draft canonical rows")
app = app.replace('edited=st.data_editor(frame,hide_index=True,num_rows="dynamic",width="stretch",key="lines_"+suffix,',
                  'edited=st.data_editor(frame,hide_index=True,num_rows="dynamic",width="stretch",key="lines_"+suffix,disabled=["item_name"],')
app = app.replace('                updated=dict(payload)\n                updated.update(invoice_number=reference.strip(),movement_type=kind,\n                               items=clean_json(edited.to_dict("records")))',
                  '                canonical_rows, _ = canonicalize_invoice_rows(edited.to_dict("records"), stock, drop_unknown=False)\n                updated=dict(payload)\n                updated.update(invoice_number=reference.strip(),movement_type=kind,\n                               items=clean_json(canonical_rows))')
app = app.replace('                # Existing history can fill codes but never determines opening quantities.\n                history=store.movement_history(token)\n                if not history.empty:df=enrich_stock_codes(df,history)\n',
                  '                # The warehouse report is now the master source for both item code and item name.\n')
app = app.replace('"\\u062a\\u063a\\u0637\\u064a\\u0629 \\u0627\\u0644\\u0645\\u062e\\u0632\\u0648\\u0646 \\u0628\\u0627\\u0644\\u0623\\u064a\\u0627\\u0645"',
                  '"تغطية المستودع بالأيام"')
path.write_text(app, encoding="utf-8")


path = ROOT / "gp_ui.py"
ui = path.read_text(encoding="utf-8")
ui = ui.replace('BUILD = "GP-CLOUD-v6"', 'BUILD = "GP-CLOUD-v9"')
warehouse_overrides = '''\n# ---- v9 warehouse terminology and code-master guidance ----
AR.update({
    "Inventory": "إدارة المستودعات",
    "Stock": "المستودع",
    "store": "أمين مستودع",
    "Upload stock": "رفع جرد المستودع",
    "No stock": "لا توجد بيانات للمستودع. ارفع تقرير جرد المستودع من الإعدادات.",
    "Draft hint": "المسودة لا تغيّر رصيد المستودع. احفظ تعديلاتك قبل الخروج.",
    "OCR hint": "تُقرأ الرموز والكميات فقط، ثم يُربط كل رمز حصراً باسمه من تقرير المستودع قبل الاعتماد.",
    "Warehouse code master required": "ارفع تقرير جرد المستودع الذي يحتوي رمز المادة واسم المادة قبل قراءة الفواتير.",
    "Ignored non-item numbers": "تم تجاهل أرقام ليست رموز مواد في المستودع",
    "Importing stock": "جاري اعتماد رصيد المستودع...",
})
'''
if "v9 warehouse terminology" not in ui:
    ui += warehouse_overrides
path.write_text(ui, encoding="utf-8")

print("v9 source update applied")
