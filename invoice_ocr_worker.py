"""Isolated, CPU-only invoice reader for the Golden Palace numeric template.

No Streamlit/database imports and no paid API. Only printed 0-9 item codes,
quantities and the numeric reference are read. Names and IN/OUT are reviewed
in the app. Model weights may be downloaded from EasyOCR's official releases;
invoice bytes are never sent to a remote OCR service.
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

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
              "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"
os.environ["MALLOC_ARENA_MAX"] = "2"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

BUILD = "GP-OCR-CPU-LITE-v4"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_SOURCE_SIDE = 2000
MAX_CANVAS = 768
MAX_ROWS = 60
_MIN_CONFIDENCE = 0.40
_reader = None
_np = None
_torch = None


def _stage(name: str, **details) -> None:
    """Log stages/resources, never item codes, document text or invoice names."""
    suffix = " ".join(f"{key}={value}" for key, value in details.items())
    print(f"[{BUILD}] {name} {suffix}".rstrip(), flush=True)


def get_reader():
    global _reader, _np, _torch
    if _reader is not None:
        return _reader
    _stage("import_start")
    import numpy as np
    import torch
    import cv2
    import easyocr
    _np, _torch = np, torch
    _stage("dependencies", torch=torch.__version__, cuda=torch.version.cuda,
           easyocr=easyocr.__version__, numpy=np.__version__)
    if torch.version.cuda is not None:
        raise RuntimeError(
            "The installed torch build still contains CUDA. Install the supplied "
            "CPU-only requirements.txt and reboot before scanning."
        )
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    cv2.setNumThreads(1)
    _stage("model_load_start")
    # English gen2 handles the printed 0-9 digits in the sample without loading
    # the Arabic recognizer. The stock catalogue provides Arabic product names.
    _reader = easyocr.Reader(
        ["en"], gpu=False, quantize=False, verbose=False,
        download_enabled=True,
    )
    _stage("model_load_done")
    return _reader


def _clean(value) -> str:
    return str(value or "").strip().replace("\u200e", "").replace("\u200f", "")


def _prepare_crop(image, rect, max_side=MAX_CANVAS):
    """Crop before enlarging. Both dimensions are strictly bounded."""
    from PIL import Image, ImageEnhance, ImageOps
    left, top, right, bottom = rect
    left, top = max(0, int(left)), max(0, int(top))
    right, bottom = min(image.width, int(right)), min(image.height, int(bottom))
    if right <= left or bottom <= top:
        raise ValueError("Empty invoice crop; use a clear photo of the entire page.")
    crop = image.crop((left, top, right, bottom))
    gray = ImageOps.autocontrast(ImageOps.grayscale(crop), cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.20)
    limit = min(MAX_CANVAS, max(32, int(max_side)))
    scale = min(3.0, limit / max(gray.size))
    width = max(1, min(limit, round(gray.width * scale)))
    height = max(1, min(limit, round(gray.height * scale)))
    prepared = gray.resize((width, height), Image.Resampling.LANCZOS)
    # Keep separate exact scales because rounded dimensions may differ slightly.
    return prepared, (left, top, width / crop.width, height / crop.height)


def read_region(image, rect, allowlist="0123456789.,", stage="region"):
    prepared, (left, top, scale_x, scale_y) = _prepare_crop(image, rect)
    reader = get_reader()
    array = _np.asarray(prepared)
    _stage(stage + "_start", width=prepared.width, height=prepared.height)
    with _torch.inference_mode():
        raw = reader.readtext(
            array, detail=1, paragraph=False, decoder="greedy",
            allowlist=allowlist, batch_size=1, workers=0,
            canvas_size=MAX_CANVAS, mag_ratio=1.0,
            rotation_info=None, contrast_ths=0.0,
        )
    result = []
    for entry in raw:
        if not isinstance(entry, (tuple, list)) or len(entry) != 3:
            continue
        bbox, text, confidence = entry
        try:
            confidence = float(confidence)
            xs = [float(point[0]) / scale_x + left for point in bbox]
            ys = [float(point[1]) / scale_y + top for point in bbox]
            if not math.isfinite(confidence) or not all(map(math.isfinite, xs + ys)):
                continue
            result.append({"text": _clean(text), "confidence": confidence,
                           "x": sum(xs) / len(xs), "y": sum(ys) / len(ys)})
        except (ValueError, TypeError, ZeroDivisionError):
            continue
    del raw, array, prepared
    gc.collect()
    _stage(stage + "_done", boxes=len(result))
    return result


def parse_codes(boxes, height):
    rows = []
    for box in sorted(boxes, key=lambda box: box["y"]):
        code = _clean(box["text"]).replace(" ", "")
        # Preserve leading zeros. No fuzzy matching or made-up missing digits.
        if not re.fullmatch(r"[0-9]{4,12}", code):
            continue
        if box["confidence"] < _MIN_CONFIDENCE:
            continue
        row = {"code": code, "y": box["y"], "confidence": box["confidence"]}
        if rows and abs(row["y"] - rows[-1]["y"]) < height * 0.009:
            if row["confidence"] > rows[-1]["confidence"]:
                rows[-1] = row
        else:
            rows.append(row)
    if len(rows) > MAX_ROWS:
        raise ValueError("Too many candidate rows. Use a clearer image or manual entry.")
    return rows


def parse_quantity(boxes, row_y, half_height):
    candidates = []
    for box in boxes:
        text = _clean(box["text"]).replace(" ", "").replace(",", ".")
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
            continue
        value = float(text)
        distance = abs(box["y"] - row_y)
        if (not math.isfinite(value) or not 0 < value < 100000
                or box["confidence"] < _MIN_CONFIDENCE
                or distance > half_height):
            continue
        candidates.append((distance, value))
    # Ambiguity stays blank for review; do not pick a convenient quantity.
    if not candidates or len({value for _, value in candidates}) != 1:
        return None
    return candidates[0][1]


def parse_summary(boxes):
    references = []
    for box in boxes:
        text = _clean(box["text"]).replace(" ", "")
        if (re.fullmatch(r"[0-9]{3,8}", text)
                and box["confidence"] >= _MIN_CONFIDENCE):
            references.append((text, box["y"]))
    values = {text for text, _ in references}
    reference = next(iter(values)) if len(values) == 1 else ""
    total = None
    if reference:
        ref_y = min(y for text, y in references if text == reference)
        totals = set()
        for box in boxes:
            text = _clean(box["text"]).replace(" ", "").replace(",", ".")
            if (box["y"] > ref_y and box["confidence"] >= _MIN_CONFIDENCE
                    and re.fullmatch(r"[0-9]+\.[0-9]+", text)):
                number = float(text)
                if math.isfinite(number) and number >= 0:
                    totals.add(number)
        if len(totals) == 1:
            total = next(iter(totals))
    return reference, total


def extract_invoice(image_path):
    from PIL import Image, ImageOps
    source = Path(image_path)
    if source.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 12 MB. Upload a smaller JPEG/PNG.")
    with Image.open(source) as original:
        if original.width * original.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds 24 megapixels. Resize it before scanning.")
        # JPEG draft reduces decoder memory before resizing; PNG still has the
        # explicit pixel/file-size limits above.
        original.draft("RGB", (MAX_SOURCE_SIDE, MAX_SOURCE_SIDE))
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((MAX_SOURCE_SIDE, MAX_SOURCE_SIDE), Image.Resampling.LANCZOS)
    width, height = image.size
    _stage("image_ready", width=width, height=height)
    if width > height:
        raise ValueError("Use a portrait photo with the complete page upright.")

    # This is the existing Golden Palace page layout, not a general invoice OCR.
    code_boxes = read_region(image, (width * .76, height * .28, width, height * .66),
                             "0123456789", "codes")
    rows = parse_codes(code_boxes, height)
    warnings = [
        "\u0647\u0630\u0647 \u0642\u0631\u0627\u0621\u0629 \u0644\u0644\u0631\u0645\u0648\u0632 \u0648\u0627\u0644\u0643\u0645\u064a\u0627\u062a \u0641\u0642\u0637. \u0631\u0627\u062c\u0639 \u0627\u0644\u0635\u0648\u0631\u0629 \u0648\u0643\u0644 \u0633\u0637\u0631 \u0642\u0628\u0644 \u0627\u0644\u0627\u0639\u062a\u0645\u0627\u062f.",
        "\u0646\u0648\u0639 \u0627\u0644\u062d\u0631\u0643\u0629 \u0644\u0645 \u064a\u064f\u0642\u0631\u0623 \u062a\u0644\u0642\u0627\u0626\u064a\u0627\u064b. \u0627\u062e\u062a\u0631 \u0625\u062f\u062e\u0627\u0644 \u0623\u0648 \u0625\u062e\u0631\u0627\u062c \u064a\u062f\u0648\u064a\u0627\u064b.",
    ]
    items = []
    for index, row in enumerate(rows):
        gaps = [abs(row["y"] - other["y"]) for other in rows if other is not row]
        half_height = max(8, min(height * .025, min(gaps, default=height * .06) * .4))
        boxes = read_region(image, (width * .20, row["y"] - half_height,
                                    width * .37, row["y"] + half_height),
                            stage=f"quantity_{index + 1}")
        quantity = parse_quantity(boxes, row["y"], half_height)
        if quantity is None:
            warnings.append(f"Row {index + 1}: quantity is uncertain; enter it manually.")
        items.append({"item_code": row["code"], "item_name": "", "quantity": quantity})
    reference, printed_total = "", None
    if rows:
        last_y = rows[-1]["y"]
        summary = read_region(image, (0, last_y + height * .020,
                                      width * .22, min(height * .79, last_y + height * .18)),
                              stage="summary")
        reference, printed_total = parse_summary(summary)
    if not reference:
        warnings.append("Reference is uncertain; enter the reference from the document.")
    known_quantities = [item["quantity"] for item in items if item["quantity"] is not None]
    if printed_total is not None and len(known_quantities) == len(items):
        if not math.isclose(sum(known_quantities), printed_total, abs_tol=.001):
            warnings.append("The row quantities do not match the candidate printed total. Review every row.")
    else:
        warnings.append("The printed total was not verified. Check row count and total manually.")
    if not items:
        warnings.append("No reliable item rows were found. Enter rows manually in the review table.")
    # This is a completeness indicator, never a calibrated OCR accuracy claim.
    completeness = .4 * bool(items) + .2 * bool(reference)
    if items:
        completeness += .2 * len(known_quantities) / len(items)
    _stage("extraction_done", rows=len(items))
    return {"invoice_number": reference, "movement_type": "OUT",
            "movement_detected": False, "confidence": min(.8, completeness),
            "items": items, "warnings": warnings, "printed_total_candidate": printed_total,
            "ocr_engine": BUILD, "ocr_text": "Numeric-only mode: Arabic names come from stock.",
            "reference_ocr_text": reference}


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
    Path(sys.argv[2]).write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    _stage("worker_exit", code=exit_code, seconds=round(time.monotonic() - start, 2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
