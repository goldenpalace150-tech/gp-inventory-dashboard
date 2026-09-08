"""Exact invoice matching. No fuzzy item substitution and no silent rounding."""
import pandas as pd
from gp_core import COL_CODE, COL_NAME, COL_KEY, COL_MATCH, normalize_item_code, normalize_item_name
from gp_store import AppError, decimal_qty


def match_invoice_lines(items, stock, movement_type):
    if movement_type not in ("IN","OUT"):
        raise AppError("Select IN or OUT")
    if stock.empty:
        raise AppError("No stock")
    changes=[]
    for position,item in enumerate(items,1):
        code=normalize_item_code(item.get("item_code", ""))
        name=normalize_item_name(item.get("item_name", ""))
        value=item.get("quantity")
        # A genuinely blank placeholder row can be omitted; half-filled rows cannot.
        if not code and not name and (value is None or pd.isna(value)):
            continue
        qty=decimal_qty(value,positive=True)
        if code:
            matches=stock[stock[COL_CODE].map(normalize_item_code)==code]
        elif name:
            matches=stock[stock[COL_MATCH]==name]
        else:
            raise AppError(f"Row {position}: choose an item code or exact name")
        if len(matches)!=1:
            raise AppError(f"Row {position}: no unique exact stock match for {code or name}")
        changes.append({"item_key":str(matches.iloc[0][COL_KEY]),"movement_type":movement_type,"quantity":qty})
    if not changes:
        raise AppError("No valid movement lines")
    return changes
