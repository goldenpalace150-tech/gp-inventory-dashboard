from pathlib import Path
from datetime import datetime
import ast
import io
import pandas as pd
import pytest
from gp_core import *
from gp_store import Store,utcnow
from gp_reports import excel_bytes
from gp_ocr import _run_ocr_worker,_ocr_scan_lock
from invoice_ocr_worker import parse_codes,parse_quantity,parse_summary,_prepare_crop
from PIL import Image


def test_stock_reader_preserves_string_codes():
    df=pd.DataFrame({COL_CODE:["010716"],COL_NAME:["Camera"],COL_QTY:[3]})
    b=io.BytesIO();df.to_excel(b,index=False)
    parsed=read_stock_report(b.getvalue())
    assert parsed.iloc[0][COL_CODE]=="010716"


def test_analysis_and_zero_previous_rate():
    stock=ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:"A",COL_NAME:"Test",COL_QTY:10}]))
    history=pd.DataFrame([{COL_CODE:"A",COL_NAME:"Test",COL_MATCH:"test",COL_DATE:pd.Timestamp("2026-09-01"),
                          COL_REF:"sale",COL_IN:0,COL_OUT:10}])
    output=build_inventory_analysis(stock,history,30,15,90)
    assert len(output)==1


def test_ambiguous_enrichment_does_not_guess():
    stock=ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:"",COL_NAME:"Camera",COL_QTY:1}]))
    history=pd.DataFrame([{COL_CODE:"A",COL_MATCH:"camera"},{COL_CODE:"B",COL_MATCH:"camera"}])
    assert enrich_stock_codes(stock,history).iloc[0][COL_CODE]==""


def test_report_export_blocks_formula_injection():
    from openpyxl import load_workbook
    data=excel_bytes({"Test":pd.DataFrame({"name":["=HYPERLINK(\"https://example.com\")"],"qty":[2]})})
    book=load_workbook(io.BytesIO(data));cell=book.active["A2"]
    assert cell.data_type!="f" and cell.value.startswith("'")
    assert book.active.freeze_panes=="A2"


def test_history_import_no_stock_deduction():
    s=Store.for_tests();pw="Test-Password-2026";s.initialize(password=pw);t=s.login("admin",pw)
    stock=ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:"",COL_NAME:"Camera",COL_QTY:10}]))
    s.replace_stock(t,pw,stock,"base",s.state(t)["revision"])
    history=pd.DataFrame([{COL_CODE:"010716",COL_NAME:"Camera",COL_MATCH:"camera",COL_DATE:pd.Timestamp("2026-01-01"),
                          COL_REF:"R1",COL_IN:100,COL_OUT:90,COL_BAL:10}])
    s.import_history(t,pw,history,"a"*64,utcnow(),"history")
    assert s.stock(t).iloc[0][COL_QTY]==10
    assert s.stock(t).iloc[0][COL_CODE]=="010716"
    assert len(s.movement_history(t))==1


def test_crop_strict_pixel_bound():
    image=Image.new("RGB",(3000,4000),"white")
    prepared,_=_prepare_crop(image,(0,0,3000,4000))
    assert max(prepared.size)<=768


def test_codes_no_fuzzy_padding():
    boxes=[{"text":"010716","confidence":.9,"y":100},
           {"text":"abc","confidence":.9,"y":200}]
    rows=parse_codes(boxes,1000)
    assert len(rows)==1 and rows[0]["code"]=="010716"


def test_quantity_ambiguity_blank():
    boxes=[{"text":"3.00","confidence":.9,"y":100},{"text":"4.00","confidence":.9,"y":101}]
    assert parse_quantity(boxes,100,20) is None


def test_quantity_parser():
    assert parse_quantity([{"text":"3.00","confidence":.9,"y":100}],100,20)==3


def test_reference_ambiguity_blank():
    boxes=[{"text":"8042","confidence":.9,"y":100},{"text":"8043","confidence":.9,"y":120}]
    assert parse_summary(boxes)[0]==""


def test_scan_lock_is_shared():
    assert _ocr_scan_lock() is _ocr_scan_lock()


def test_worker_invalid_upload():
    with pytest.raises(ValueError):_run_ocr_worker(b"")


def test_worker_missing_file(tmp_path):
    with pytest.raises(RuntimeError):_run_ocr_worker(b"image",worker_path=tmp_path/"missing.py")


def test_worker_success_without_model(tmp_path,monkeypatch):
    import gp_ocr
    monkeypatch.setattr(gp_ocr,"_ocr_memory_state",lambda:(None,None))
    worker=tmp_path/"worker.py"
    worker.write_text('import sys,json\nfrom pathlib import Path\nPath(sys.argv[2]).write_text(json.dumps({"ok":True,"data":{"items":[]}}))')
    assert _run_ocr_worker(b"image",worker_path=worker,timeout=3)=={"items":[]}


def test_worker_timeout(tmp_path,monkeypatch):
    import gp_ocr
    monkeypatch.setattr(gp_ocr,"_ocr_memory_state",lambda:(None,None))
    worker=tmp_path/"worker.py";worker.write_text('import time\ntime.sleep(30)')
    with pytest.raises(RuntimeError,match="timed out"):_run_ocr_worker(b"image",worker_path=worker,timeout=.15)


def test_ui_has_no_sidebar_or_global_rtl_rule():
    root=Path(__file__).resolve().parents[1]
    source=(root/"inventory_tracker.py").read_text()
    assert "st.sidebar" not in source and "use_container_width" not in source
    stylesheet=(root/"assets/style.css").read_text()
    assert "h1, h2, h3, h4, p, span, label, div" not in stylesheet
    for f in root.glob("*.py"):ast.parse(f.read_text())


def test_web_process_has_no_neural_network_imports():
    root=Path(__file__).resolve().parents[1]
    for file in ("inventory_tracker.py","gp_ocr.py","gp_store.py","gp_core.py"):
        tree=ast.parse((root/file).read_text())
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports += [n.name for n in node.names]
            if isinstance(node,ast.ImportFrom):imports.append(node.module or "")
        assert not any(x.split(".")[0] in ("torch","easyocr","torchvision") for x in imports)


def test_daily_report_preserves_sections_and_totals():
    from gp_reports import day_report_sheets
    from decimal import Decimal
    ledger=pd.DataFrame([
        {'ledger_id':1,'item_key':'A','item_code':'010716','item_name':'Camera',
         'movement_type':'OUT','quantity':Decimal('3'),'quantity_before':Decimal('10'),
         'quantity_after':Decimal('7'),'without_invoice':True},
        {'ledger_id':2,'item_key':'A','item_code':'010716','item_name':'Camera',
         'movement_type':'IN','quantity':Decimal('1'),'quantity_before':Decimal('7'),
         'quantity_after':Decimal('8'),'without_invoice':False}])
    stock=ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:'010716',COL_NAME:'Camera',COL_QTY:8}]))
    sheets=day_report_sheets('2026-09-08',ledger,stock,pd.DataFrame(),True)
    assert len(sheets)==7
    assert sheets['Daily_Summary'].iloc[0]['total_out']==3
    assert sheets['Daily_Summary'].iloc[0]['total_in']==1
    assert len(sheets['No_Invoice_Alerts'])==1
    row=sheets['Affected_Items'].iloc[0]
    assert row['opening']==10 and row['closing']==8
    assert len(excel_bytes(sheets))>1000


def test_daily_report_empty_is_valid():
    from gp_reports import day_report_sheets
    sheets=day_report_sheets('2026-09-08',pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),False)
    assert sheets['Daily_Summary'].iloc[0]['movements']==0
    assert len(excel_bytes(sheets))>1000
