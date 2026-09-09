from pathlib import Path
import pandas as pd
from rapidocr import LangDet, LangRec, OCRVersion
from gp_core import COL_CODE, COL_NAME, COL_QTY, ensure_unique_stock_keys
from gp_store import Store
from invoice_ocr_worker import parse_header_metadata
import gp_ui

assert hasattr(LangRec, 'ARABIC')
assert hasattr(LangDet, 'MULTI')
assert hasattr(OCRVersion, 'PPOCRV5')
movement, customer = parse_header_metadata([
    {'text':'مذكرة تسليم (إخراج مخازن)','score':0.95,'x':500,'y':100,'region':'header'},
    {'text':'للسيد / محمد احمد','score':0.95,'x':400,'y':150,'region':'header'},
], 1000, 1200)
assert movement == 'OUT'
assert 'محمد' in customer

s = Store.for_tests()
pw = 'WarehouseTest_2026'
s.initialize(password=pw)
token = s.login('admin', pw)
stock1 = ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:'A', COL_NAME:'Item A', COL_QTY:5}]))
op1 = s.replace_stock(token, pw, stock1, 'base1', s.state(token)['revision'], source_name='r1.xlsx')
stock2 = ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:'A', COL_NAME:'Item A', COL_QTY:9}]))
op2 = s.replace_stock(token, pw, stock2, 'base2', s.state(token)['revision'], source_name='r2.xlsx')
k = s.stock(token).iloc[0]['مفتاح المخزون']
s.post(token, pw, [dict(item_key=k, movement_type='OUT', quantity=1)], 'm1', reference='M1', reason='manual', delivery_note=True)
assert float(s.stock(token).iloc[0][COL_QTY]) == 8.0
s.delete_stock_report(token, pw, op1)
assert float(s.stock(token).iloc[0][COL_QTY]) == 8.0
remaining = {r['operation_id'] for r in s.deletion_catalog(token)['stock_reports']}
assert op1 not in remaining and op2 in remaining

assert gp_ui.BUILD == 'GP-CLOUD-v12'
app = Path('inventory_tracker.py').read_text()
assert 'result=extract_invoice_data(uploaded,stock)' in app
css = Path('assets/style.css').read_text()
assert 'v12: accessible form cells' in css
print('v12 validation passed')
