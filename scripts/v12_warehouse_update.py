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


# ---------------------------------------------------------------------------
# requirements.txt - Arabic RapidOCR support for optional customer/header read
# ---------------------------------------------------------------------------
path = ROOT / "requirements.txt"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "onnxruntime>=1.22,<2\n",
    "onnxruntime>=1.22,<2\npython-bidi>=0.6,<1\n",
    "python-bidi dependency",
)
path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# gp_ocr.py - v12 metadata-aware OCR wrapper
# ---------------------------------------------------------------------------
path = ROOT / "gp_ocr.py"
text = path.read_text(encoding="utf-8")
text = text.replace('OCR_BUILD = "GP-OCR-WAREHOUSE-v9"', 'OCR_BUILD = "GP-OCR-WAREHOUSE-v12"', 1)
text = replace_once(
    text,
    'missing = [name for name in ("rapidocr", "onnxruntime") if importlib.util.find_spec(name) is None]',
    'missing = [name for name in ("rapidocr", "onnxruntime", "bidi") if importlib.util.find_spec(name) is None]',
    "OCR dependency check",
)
text = text.replace('OCR_BUILD + " | free local ONNX code/quantity reader"',
                    'OCR_BUILD + " | free local ONNX code/quantity/header reader"', 1)
path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# invoice_ocr_worker.py - detect movement, invoice reference and customer name
# ---------------------------------------------------------------------------
path = ROOT / "invoice_ocr_worker.py"
text = path.read_text(encoding="utf-8")
text = text.replace('BUILD = "GP-OCR-WAREHOUSE-v9"', 'BUILD = "GP-OCR-WAREHOUSE-v12"', 1)
text = replace_once(text, "_engine = None\n", "_engine = None\n_arabic_engine = None\n", "Arabic engine global")

arabic_engine = r'''

def get_arabic_engine():
    """Small Arabic recognition engine used only for the invoice header/recipient."""
    global _arabic_engine
    if _arabic_engine is not None:
        return _arabic_engine
    _stage("arabic_import_start")
    from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR

    _arabic_engine = RapidOCR(params={
        "Global.use_cls": False,
        "Global.max_side_len": 900,
        "Global.text_score": 0.30,
        "EngineConfig.onnxruntime.intra_op_num_threads": 1,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
        "Det.engine_type": EngineType.ONNXRUNTIME,
        "Det.lang_type": LangDet.MULTI,
        "Det.model_type": ModelType.MOBILE,
        "Det.ocr_version": OCRVersion.PPOCRV5,
        "Det.limit_side_len": 640,
        "Det.limit_type": "max",
        "Rec.engine_type": EngineType.ONNXRUNTIME,
        "Rec.lang_type": LangRec.ARABIC,
        "Rec.model_type": ModelType.MOBILE,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.rec_batch_num": 1,
    })
    _stage("arabic_model_load_done")
    return _arabic_engine
'''
text = replace_once(text, "    return _engine\n\n\ndef _clean", "    return _engine" + arabic_engine + "\n\ndef _clean", "Arabic OCR engine")

arabic_helpers = r'''

def run_arabic_ocr(array):
    engine = get_arabic_engine()
    _stage("arabic_ocr_start", height=array.shape[0], width=array.shape[1])
    output = engine(array, use_cls=False)
    boxes = _normalize_output(output)
    _stage("arabic_ocr_done", boxes=len(boxes))
    return boxes


def run_header_ocr(array):
    """Read only the document title + recipient/customer strip in Arabic."""
    global _engine
    # Numeric recognition is finished before this call. Release that ONNX session
    # before loading Arabic recognition to stay inside Streamlit Cloud memory.
    _engine = None
    gc.collect()
    height, width = array.shape[:2]
    left, top = int(width * 0.02), int(height * 0.20)
    right, bottom = int(width * 0.98), int(height * 0.45)
    crop = array[top:bottom, left:right]
    if crop.size == 0:
        return []
    boxes = run_arabic_ocr(crop)
    for box in boxes:
        box["x"] += left
        box["y"] += top
        box["region"] = "header"
    return boxes


def _arabic_search_text(value):
    value = _clean(value).replace("ـ", "")
    value = re.sub(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]", "", value)
    return value.translate(str.maketrans({"أ":"ا", "إ":"ا", "آ":"ا", "ٱ":"ا"}))


def parse_header_metadata(boxes, width, height):
    """Return detected movement IN/OUT and an optional customer/recipient name."""
    rows = [b for b in sorted(boxes or [], key=lambda b: (b.get("y", 0), -b.get("x", 0)))
            if b.get("score", 0) >= 0.28 and b.get("region") in (None, "header")]
    normalized = [_arabic_search_text(row.get("text", "")) for row in rows]
    joined = " | ".join(normalized)

    movement = ""
    # Prefer explicit stock terminology. Generic delivery/receipt words are only
    # fallbacks because they can also appear in explanatory sentences.
    if any(token in joined for token in ("اخراج مواد", "اخراج مخازن", "حركة اخراج", "مذكرة تسليم")):
        movement = "OUT"
    elif any(token in joined for token in ("ادخال مواد", "ادخال مخازن", "حركة ادخال", "مذكرة استلام")):
        movement = "IN"
    elif "اخراج" in joined:
        movement = "OUT"
    elif "ادخال" in joined:
        movement = "IN"

    customer = ""
    labels = ("للسيد", "اسم العميل", "اسم الزبون", "العميل", "الزبون")
    for index, row in enumerate(rows):
        raw = _clean(row.get("text", ""))
        norm = _arabic_search_text(raw)
        matched = next((label for label in labels if label in norm), None)
        if not matched:
            continue
        # Remove everything through the label. OCR can return the whole explanatory
        # sentence in one line, so a greedy prefix is intentional here.
        candidate = re.sub(r"^.*?(?:للسيد|اسم\s*العميل|اسم\s*الزبون|العميل|الزبون)\s*[:：\-]?\s*", "", raw).strip(" :：-ـ")
        if not candidate and index + 1 < len(rows):
            candidate = _clean(rows[index + 1].get("text", "")).strip(" :：-ـ")
        # Golden Palace delivery notes sometimes prefix a section/category before '/'.
        if "/" in candidate:
            pieces = [part.strip(" :：-ـ") for part in candidate.split("/") if part.strip(" :：-ـ")]
            if pieces:
                candidate = pieces[-1]
        # Keep only plausible human/customer text and never invent a value.
        if 2 <= len(candidate) <= 140 and re.search(r"[\u0600-\u06FF]", candidate):
            customer = candidate
            break
    return movement, customer
'''
text = replace_once(text, "    return boxes\n\n\ndef _run_region", "    return boxes" + arabic_helpers + "\n\ndef _run_region", "Arabic header helpers")

header_parser_marker = "def parse_codes(boxes, width, height):"
if "def parse_header_metadata" not in text:
    raise RuntimeError("Arabic metadata parser was not inserted")

old_header = '''    boxes = run_targeted_ocr(array)
    rows = parse_codes(boxes, width, height)
    warnings = [
        "هذه قراءة للرموز والكميات فقط. راجع الصورة وكل سطر قبل الاعتماد.",
        "نوع الحركة لا يُقرأ تلقائياً. اختر إدخال أو إخراج يدوياً.",
    ]
'''
new_header = '''    boxes = run_targeted_ocr(array)
    rows = parse_codes(boxes, width, height)
    movement_type = ""
    customer_name = ""
    header_failed = False
    try:
        header_boxes = run_header_ocr(array)
        movement_type, customer_name = parse_header_metadata(header_boxes, width, height)
    except Exception as error:
        # Header metadata is convenience OCR only; numeric stock rows must remain usable.
        header_failed = True
        _stage("header_ocr_failed", error_type=type(error).__name__)
    warnings = [
        "تمت قراءة رموز المواد والكميات ورقم الفاتورة آلياً. راجع كل سطر قبل الاعتماد.",
    ]
    if not movement_type:
        warnings.append("نوع الحركة غير مؤكد؛ اختر إدخال أو إخراج يدوياً.")
    if header_failed:
        warnings.append("تعذر قراءة بيانات رأس الفاتورة؛ أدخل نوع الحركة واسم الزبون يدوياً عند الحاجة.")
'''
text = replace_once(text, old_header, new_header, "invoice header metadata extraction")

old_completeness = '''    completeness = 0.4 * bool(items) + 0.2 * bool(reference)
    if items:
        completeness += 0.2 * len(known_quantities) / len(items)

    del boxes, array, image
'''
new_completeness = '''    completeness = 0.4 * bool(items) + 0.2 * bool(reference)
    if items:
        completeness += 0.2 * len(known_quantities) / len(items)
    completeness += 0.1 * bool(movement_type) + 0.1 * bool(customer_name)

    del boxes, array, image
'''
text = replace_once(text, old_completeness, new_completeness, "OCR completeness")

text = replace_once(
    text,
    '''        "invoice_number": reference,
        "movement_type": "OUT",
        "movement_detected": False,
''',
    '''        "invoice_number": reference,
        "movement_type": movement_type,
        "movement_detected": bool(movement_type),
        "customer_name": customer_name,
''',
    "OCR metadata return",
)
text = text.replace('"ocr_text": "Numeric-only mode: Arabic names come from stock.",',
                    '"ocr_text": "Warehouse code matching + Arabic header metadata mode.",', 1)
path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# inventory_tracker.py - use OCR metadata, visible cell borders, force report delete UI
# ---------------------------------------------------------------------------
path = ROOT / "inventory_tracker.py"
app = path.read_text(encoding="utf-8")
app = replace_once(
    app,
    'result=extract_invoice_data(uploaded,stock); result["movement_type"]=""\n                            result.setdefault("customer_name",""); result.setdefault("driver","")',
    'result=extract_invoice_data(uploaded,stock)\n                            if result.get("movement_type") not in ("IN","OUT"): result["movement_type"]=""\n                            result.setdefault("customer_name",""); result.setdefault("driver","")',
    "preserve OCR movement/customer metadata",
)

old_delete_ui = '''        latest=ids[0]
        if selected!=latest:st.info(t("Only latest warehouse report can be deleted"))
        with st.form("delete_stock_report_form"):
            st.caption(t("Warehouse report delete hint"))
            confirmed=st.checkbox(t("Confirm delete"),key="delete_stock_report_confirm")
            password=st.text_input(t("Approval password"),type="password",key="password_delete_stock")
            if st.form_submit_button(t("Delete warehouse report"),type="primary",disabled=not (confirmed and selected==latest)):
                try:store.delete_stock_report(token,password,selected);success(message="Deleted")
                except Exception as error:show_error(error)
'''
new_delete_ui = '''        with st.form("delete_stock_report_form"):
            st.caption(t("Warehouse report delete hint"))
            confirmed=st.checkbox(t("Confirm delete"),key="delete_stock_report_confirm")
            password=st.text_input(t("Approval password"),type="password",key="password_delete_stock")
            if st.form_submit_button(t("Delete warehouse report"),type="primary",disabled=not confirmed):
                try:store.delete_stock_report(token,password,selected);success(message="Deleted")
                except Exception as error:show_error(error)
'''
app = replace_once(app, old_delete_ui, new_delete_ui, "unconditional admin report delete UI")
path.write_text(app, encoding="utf-8")


# ---------------------------------------------------------------------------
# gp_store.py - admin may delete any warehouse-report record with no dependency gate
# Current stock/ledger are intentionally left untouched to avoid corrupting later work.
# ---------------------------------------------------------------------------
path = ROOT / "gp_store.py"
store = path.read_text(encoding="utf-8")
new_delete_method = r'''    def delete_stock_report(self,token,password,operation_id):
        """Admin-only force delete of a warehouse-report record.

        This deliberately removes the selected baseline snapshot/history record without
        rewinding current stock or later ledger rows. It therefore has no dependency
        condition and cannot invalidate quantities already used by later movements.
        """
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token,password,admin=True)
            baselines=self.tables["baseline_snapshots"]; operations=self.tables["operations"]
            target=c.execute(select(baselines).where(
                baselines.c.operation_id==str(operation_id)
            ).with_for_update()).mappings().first()
            if not target:raise AppError("Record not found")
            op=c.execute(select(operations).where(
                operations.c.operation_id==target["operation_id"]
            ).with_for_update()).mappings().first()
            if not op or op["source"]!="BASELINE":raise AppError("Record not found")
            payload=target["stock"] if isinstance(target["stock"],dict) else {}
            c.execute(delete(baselines).where(baselines.c.operation_id==target["operation_id"]))
            c.execute(delete(operations).where(operations.c.operation_id==target["operation_id"]))
            self._audit(c,actor["username"],"DELETE_STOCK_REPORT",{
                "operation_id":target["operation_id"],
                "source_name":payload.get("source_name",""),
                "forced":True,
                "current_stock_unchanged":True,
            })
            self._touch(c)
            return target["operation_id"]

'''
store = regex_once(
    store,
    r'    def delete_stock_report\(self,token,password,operation_id\):.*?(?=    def closure\()',
    new_delete_method,
    "force delete stock report",
)
path.write_text(store, encoding="utf-8")


# ---------------------------------------------------------------------------
# gp_ui.py - v12 labels/hints
# ---------------------------------------------------------------------------
path = ROOT / "gp_ui.py"
ui = path.read_text(encoding="utf-8")
ui = re.sub(r'BUILD = "GP-CLOUD-v\d+"', 'BUILD = "GP-CLOUD-v12"', ui, count=1)
if "v12 OCR + accessibility" not in ui:
    ui += '''\n\n# ---- v12 OCR + accessibility / force report deletion ----\nAR.update({\n    "Warehouse report delete hint": "الحذف متاح للمدير دون شروط. يتم حذف سجل تقرير المستودع المحدد فقط، ولا يتم تغيير الرصيد الحالي أو الحركات اللاحقة.",\n    "OCR hint": "تُقرأ رموز المواد والكميات ورقم الفاتورة تلقائياً، ويحاول النظام أيضاً تحديد نوع الحركة واسم الزبون من رأس المستند عند ظهورهما بوضوح. تبقى المراجعة قبل الاعتماد إلزامية.",\n})\n'''
path.write_text(ui, encoding="utf-8")


# ---------------------------------------------------------------------------
# assets/style.css - actual visible borders between form cells + tighter spacing
# ---------------------------------------------------------------------------
path = ROOT / "assets/style.css"
css = path.read_text(encoding="utf-8")
if "v12: accessible form cells" not in css:
    css += '''\n\n/* v12: accessible form cells. Every Streamlit column inside a form is visibly separated. */\n[data-testid="stForm"] [data-testid="stHorizontalBlock"] {\n  gap:12px !important; align-items:stretch !important;\n}\n[data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {\n  border:1px solid #cfd9e5; border-radius:13px; padding:12px 14px 10px;\n  background:#fbfcfe; box-sizing:border-box; min-width:0;\n}\n[data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:focus-within {\n  border-color:var(--gp-gold); box-shadow:0 0 0 2px #caa24b24;\n}\n.gp-form-gap { height:12px; }\n@media (max-width:800px) {\n  [data-testid="stForm"] [data-testid="stHorizontalBlock"] { gap:8px !important; }\n  [data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { padding:10px; }\n  .gp-form-gap { height:8px; }\n}\n'''
path.write_text(css, encoding="utf-8")

print("v12 warehouse update applied")
