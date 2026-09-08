"""Exact invoice matching against the current warehouse code master."""
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
