"""Isolated low-memory OCR for the Golden Palace invoice template.

This worker uses RapidOCR + ONNX Runtime instead of EasyOCR/PyTorch. It reads
only the numeric fields required by the inventory app: item codes, quantities
and invoice reference. Arabic product names continue to come from stock data.
"""
from __future__ import annotations

import faulthandler
import gc
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import traceback

for _name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "OMP_THREAD_LIMIT",
):
    os.environ[_name] = "1"
os.environ["MALLOC_ARENA_MAX"] = "2"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

BUILD = "GP-OCR-WAREHOUSE-v16.6"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_SOURCE_SIDE = 1200
MAX_ROWS = 60
_MIN_SCORE = 0.35
_engine = None
_arabic_engine = None


def _stage(name: str, **details) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in details.items())
    print(f"[{BUILD}] {name} {suffix}".rstrip(), flush=True)


def get_engine():
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


def _clean(value) -> str:
    return str(value or "").strip().replace("\u200e", "").replace("\u200f", "")


def _load_image(path):
    from PIL import Image, ImageEnhance, ImageOps
    import numpy as np

    source = Path(path)
    if source.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 12 MB. Upload a smaller JPEG/PNG.")
    with Image.open(source) as original:
        if original.width * original.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds 24 megapixels. Resize it before scanning.")
        original.draft("RGB", (MAX_SOURCE_SIDE, MAX_SOURCE_SIDE))
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((MAX_SOURCE_SIDE, MAX_SOURCE_SIDE), Image.Resampling.LANCZOS)
        image = ImageEnhance.Contrast(image).enhance(1.08)
        array = np.asarray(image)
    return image, array


def _normalize_output(output):
    """Return list of {text, score, x, y} across RapidOCR output versions."""
    result = []
    # RapidOCR 3.x exposes boxes/txts/scores; older adapters may be tuple-like.
    boxes = getattr(output, "boxes", None)
    txts = getattr(output, "txts", None)
    scores = getattr(output, "scores", None)
    if boxes is not None and txts is not None:
        scores = scores if scores is not None else [1.0] * len(txts)
        iterable = zip(boxes, txts, scores)
    elif isinstance(output, (tuple, list)) and len(output) >= 1:
        raw = output[0] if len(output) == 2 and isinstance(output[0], list) else output
        iterable = []
        for item in raw or []:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                bbox = item[0]
                text = item[1]
                score = item[2] if len(item) >= 3 else 1.0
                iterable.append((bbox, text, score))
    else:
        iterable = []

    for bbox, text, score in iterable:
        try:
            pts = list(bbox)
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            score = float(score)
            if not math.isfinite(score) or not all(map(math.isfinite, xs + ys)):
                continue
            result.append(
                {
                    "text": _clean(text),
                    "score": score,
                    "x": sum(xs) / len(xs),
                    "y": sum(ys) / len(ys),
                }
            )
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    return result


def run_ocr(array):
    engine = get_engine()
    _stage("ocr_start", height=array.shape[0], width=array.shape[1])
    output = engine(array, use_cls=False)
    boxes = _normalize_output(output)
    _stage("ocr_done", boxes=len(boxes))
    return boxes

def run_arabic_ocr(array):
    engine = get_arabic_engine()
    _stage("arabic_ocr_start", height=array.shape[0], width=array.shape[1])
    output = engine(array, use_cls=False)
    boxes = _normalize_output(output)
    _stage("arabic_ocr_done", boxes=len(boxes))
    return boxes


def run_header_ocr(array):
    """Read the Golden Palace document title + recipient strip in Arabic.

    A focused crop is more reliable than sending the logo, phone numbers and most
    of the page to the Arabic recognizer. The supplied delivery note prints
    "مذكرة تسليم (إخراج مواد)" in this band.
    """
    global _engine
    _engine = None
    gc.collect()
    height, width = array.shape[:2]
    left, top = int(width * 0.04), int(height * 0.15)
    right, bottom = int(width * 0.96), int(height * 0.42)
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
    compact = re.sub(r"\s+", "", joined)

    def has_phrase(value):
        value = _arabic_search_text(value)
        return value in joined or re.sub(r"\s+", "", value) in compact

    movement = ""
    # Read the document title first. The compact comparison also catches OCR that
    # inserts/removes spaces between Arabic words.
    if any(has_phrase(token) for token in ("اخراج مواد", "اخراج مخازن", "حركة اخراج", "مذكرة تسليم")):
        movement = "OUT"
    elif any(has_phrase(token) for token in ("ادخال مواد", "ادخال مخازن", "حركة ادخال", "مذكرة استلام")):
        movement = "IN"
    elif has_phrase("اخراج"):
        movement = "OUT"
    elif has_phrase("ادخال"):
        movement = "IN"
    elif has_phrase("تسليم"):
        movement = "OUT"
    elif has_phrase("استلام"):
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


def _run_region(array, region, x0, y0, x1, y1):
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
    """Scan only item rows and the lower summary band; ignore phones and prices."""
    boxes = []
    boxes.extend(_run_region(array, "code", 0.70, 0.28, 1.00, 0.63))
    boxes.extend(_run_region(array, "qty", 0.17, 0.28, 0.44, 0.63))
    # Invoice number 8042 in the Golden Palace template sits above the printed
    # quantity total in the lower-left summary table. Start at 48% so the number
    # is not clipped by the old 58% crop.
    boxes.extend(_run_region(array, "summary", 0.00, 0.48, 0.55, 0.76))
    _stage("targeted_ocr_done", boxes=len(boxes))
    return boxes

def parse_codes(boxes, width, height):
    rows = []
    for box in sorted(boxes, key=lambda b: b["y"]):
        if box.get("region") not in (None, "code"):
            continue
        # Codes are in the right-side item-code column in the Golden Palace layout.
        if box["x"] < width * 0.72 or not (height * 0.28 <= box["y"] <= height * 0.67):
            continue
        text = re.sub(r"[^0-9]", "", _clean(box["text"]))
        if not re.fullmatch(r"[0-9]{4,12}", text) or box["score"] < _MIN_SCORE:
            continue
        row = {"code": text, "y": box["y"], "score": box["score"]}
        if rows and abs(row["y"] - rows[-1]["y"]) < height * 0.012:
            if row["score"] > rows[-1]["score"]:
                rows[-1] = row
        else:
            rows.append(row)
    if len(rows) > MAX_ROWS:
        raise ValueError("Too many candidate rows. Use a clearer image or manual entry.")
    return rows


def parse_quantity(boxes, row_y, width, height):
    candidates = []
    for box in boxes:
        if box.get("region") not in (None, "qty"):
            continue
        if not (width * 0.15 <= box["x"] <= width * 0.45):
            continue
        if abs(box["y"] - row_y) > height * 0.025:
            continue
        text = _clean(box["text"]).replace(" ", "").replace(",", ".")
        text = re.sub(r"[^0-9.]", "", text)
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
            continue
        try:
            value = float(text)
        except ValueError:
            continue
        if box["score"] < _MIN_SCORE or not math.isfinite(value) or not 0 < value < 100000:
            continue
        candidates.append((abs(box["y"] - row_y), value, box["score"]))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -item[2]))
    # If multiple distinct values are equally plausible, leave blank for review.
    close = [v for d, v, _ in candidates if d <= candidates[0][0] + height * 0.006]
    if len(set(close)) > 1:
        return None
    return candidates[0][1]


def parse_summary(boxes, width, height):
    reference_candidates = []
    total_candidates = []
    for box in boxes:
        if box.get("region") not in (None, "summary"):
            continue
        text = _clean(box["text"]).replace(" ", "").replace(",", ".")
        if box["score"] < _MIN_SCORE:
            continue
        # The invoice number is the upper numeric value in the left summary cells.
        # A score-first sort could incorrectly choose 9.00 (rendered as 900) when
        # OCR happened to score the total more strongly than invoice 8042.
        if box["x"] <= width * 0.30 and height * 0.48 <= box["y"] <= height * 0.72:
            digits = re.sub(r"[^0-9]", "", text)
            if re.fullmatch(r"[0-9]{3,8}", digits):
                reference_candidates.append((digits, box["score"], box["y"]))
            number_text = re.sub(r"[^0-9.]", "", text)
            if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", number_text):
                try:
                    value = float(number_text)
                    if math.isfinite(value) and value >= 0:
                        total_candidates.append((value, box["y"]))
                except ValueError:
                    pass

    reference = ""
    if reference_candidates:
        # Position is authoritative on this fixed template: invoice number is above
        # the total. Confidence only breaks ties on the same row.
        reference_candidates.sort(key=lambda x: (x[2], -x[1]))
        reference = reference_candidates[0][0]

    printed_total = None
    if reference:
        ref_y = next(y for text, _, y in reference_candidates if text == reference)
        totals = {v for v, y in total_candidates if y > ref_y + height * 0.01}
        if len(totals) == 1:
            printed_total = next(iter(totals))
    return reference, printed_total


def extract_invoice(image_path):
    image, array = _load_image(image_path)
    width, height = image.size
    _stage("image_ready", width=width, height=height)
    if width > height:
        raise ValueError("Use a portrait photo with the complete page upright.")

    boxes = run_targeted_ocr(array)
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
        warnings.append("نوع الحركة غير مؤكد؛ اختر نوع الحركة يدوياً في المراجعة.")
    if header_failed:
        warnings.append("تعذر قراءة بيانات رأس الفاتورة؛ يمكن اختيار نوع الحركة يدوياً في المراجعة.")

    items = []
    for index, row in enumerate(rows):
        quantity = parse_quantity(boxes, row["y"], width, height)
        if quantity is None:
            warnings.append(f"Row {index + 1}: quantity is uncertain; enter it manually.")
        items.append({"item_code": row["code"], "item_name": "", "quantity": quantity})

    reference, printed_total = parse_summary(boxes, width, height)
    if not reference:
        warnings.append("Reference is uncertain; retake a clearer invoice photo.")

    known_quantities = [item["quantity"] for item in items if item["quantity"] is not None]
    if printed_total is not None and len(known_quantities) == len(items):
        if not math.isclose(sum(known_quantities), printed_total, abs_tol=0.001):
            warnings.append("The row quantities do not match the candidate printed total. Review every row.")
    else:
        warnings.append("The printed total was not verified. Check row count and total manually.")

    if not items:
        warnings.append("No reliable item rows were found. Enter rows manually in the review table.")

    completeness = 0.4 * bool(items) + 0.2 * bool(reference)
    if items:
        completeness += 0.2 * len(known_quantities) / len(items)
    completeness += 0.1 * bool(movement_type) + 0.1 * bool(customer_name)

    del boxes, array, image
    gc.collect()
    _stage("extraction_done", rows=len(items))
    return {
        "invoice_number": reference,
        "movement_type": movement_type,
        "movement_detected": bool(movement_type),
        "customer_name": customer_name,
        "confidence": min(0.8, completeness),
        "items": items,
        "warnings": warnings,
        "printed_total_candidate": printed_total,
        "ocr_engine": BUILD,
        "ocr_text": "Warehouse code matching + Arabic header metadata mode.",
        "reference_ocr_text": reference,
    }


def main():
    faulthandler.enable()
    if len(sys.argv) != 3:
        print("Usage: invoice_ocr_worker.py INPUT_IMAGE OUTPUT_JSON", file=sys.stderr)
        return 2
    start = time.monotonic()
    try:
        data = extract_invoice(sys.argv[1])
        payload = {"ok": True, "data": data}
        exit_code = 0
    except Exception as error:
        traceback.print_exc()
        payload = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        exit_code = 1
    Path(sys.argv[2]).write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    _stage("worker_exit", code=exit_code, seconds=round(time.monotonic() - start, 2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
