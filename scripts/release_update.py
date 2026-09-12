from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

store_path=ROOT/'gp_store.py'
store=store_path.read_text(encoding='utf-8')
old='''        stock=self.tables["stock_state"]
        stock_rows=c.execute(select(stock).where(stock.c.item_key.in_(list(deltas))).order_by(stock.c.item_key).with_for_update()).mappings().all()
        current={r["item_key"]:dict(r) for r in stock_rows}
        if set(current)!=set(deltas):raise AppError("An item is missing from the current stock")
        now=utcnow()
        for key,delta in deltas.items():
            new_current=decimal_qty(current[key]["quantity"])+delta
            if new_current<0:raise AppError("Cannot delete because later movements depend on this quantity")
            subsequent=c.execute(select(ledger).where(
                ledger.c.item_key==key,ledger.c.ledger_id>max_target_id
            ).order_by(ledger.c.ledger_id).with_for_update()).mappings().all()
            for row in subsequent:
                new_before=decimal_qty(row["quantity_before"])+delta
                new_after=decimal_qty(row["quantity_after"])+delta
                if new_before<0 or new_after<0:
                    raise AppError("Cannot delete because later movements depend on this quantity")
                c.execute(update(ledger).where(ledger.c.ledger_id==row["ledger_id"]).values(
                    quantity_before=new_before,quantity_after=new_after))
            c.execute(update(stock).where(stock.c.item_key==key).values(quantity=new_current,updated_at=now))
'''
new='''        stock=self.tables["stock_state"]
        baselines=self.tables["baseline_snapshots"]
        has_baseline=bool(c.execute(select(baselines.c.operation_id).limit(1)).first())
        now=utcnow()
        if has_baseline:
            stock_rows=c.execute(select(stock).where(stock.c.item_key.in_(list(deltas))).order_by(stock.c.item_key).with_for_update()).mappings().all()
            current={r["item_key"]:dict(r) for r in stock_rows}
            if set(current)!=set(deltas):raise AppError("An item is missing from the current stock")
            for key,delta in deltas.items():
                new_current=decimal_qty(current[key]["quantity"])+delta
                if new_current<0:raise AppError("Cannot delete because later movements depend on this quantity")
                subsequent=c.execute(select(ledger).where(
                    ledger.c.item_key==key,ledger.c.ledger_id>max_target_id
                ).order_by(ledger.c.ledger_id).with_for_update()).mappings().all()
                for row in subsequent:
                    new_before=decimal_qty(row["quantity_before"])+delta
                    new_after=decimal_qty(row["quantity_after"])+delta
                    if new_before<0 or new_after<0:
                        raise AppError("Cannot delete because later movements depend on this quantity")
                    c.execute(update(ledger).where(ledger.c.ledger_id==row["ledger_id"]).values(
                        quantity_before=new_before,quantity_after=new_after))
                c.execute(update(stock).where(stock.c.item_key==key).values(quantity=new_current,updated_at=now))
        else:
            # If every warehouse baseline has already been removed, there is no
            # current stock truth to reverse. The remaining ledger rows are only
            # historical cleanup records, so allow deleting them without requiring
            # stock_state rows that intentionally no longer exist.
            c.execute(delete(stock))
'''
if new not in store:
    if old not in store:raise RuntimeError('delete stock reversal marker not found')
    store=store.replace(old,new,1)

old='''        self._audit(c,actor["username"],action,{"operation_id":op["operation_id"],"invoice_reference":invoice_reference,"line_count":len(target)})
'''
new='''        self._audit(c,actor["username"],action,{"operation_id":op["operation_id"],"invoice_reference":invoice_reference,
            "line_count":len(target),"stock_adjusted":bool(has_baseline)})
'''
if new not in store:
    if old not in store:raise RuntimeError('delete audit marker not found')
    store=store.replace(old,new,1)
store_path.write_text(store,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.14"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.13"' not in ui:raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.13"','BUILD = "GP-CLOUD-v16.14"',1)
ui_path.write_text(ui,encoding='utf-8')

test_path=ROOT/'tests/test_store.py'
test=test_path.read_text(encoding='utf-8')
extra='''\n\ndef test_delete_invoice_after_last_baseline_removed():\n    s=Store.for_tests();s.initialize(password=PASS);t=s.login("admin",PASS)\n    s.replace_stock(t,PASS,sample_stock(),"baseline-cleanup",s.state(t)["revision"])\n    s.post(t,PASS,change(3),"invoice-cleanup",source="INVOICE",reference="112233",image_hash="c"*64)\n    catalog=s.deletion_catalog(t)\n    assert catalog["stock_reports"]\n    baseline_id=catalog["stock_reports"][0]["operation_id"]\n    s.delete_stock_report(t,PASS,baseline_id)\n    assert s.stock(t).empty\n    assert not s.ledger(t).empty\n    s.delete_invoice(t,PASS,"112233")\n    assert s.ledger(t).empty\n    assert s.recent_invoices(t)==[]\n\ndef test_delete_manual_movement_after_last_baseline_removed():\n    s=Store.for_tests();s.initialize(password=PASS);t=s.login("admin",PASS)\n    s.replace_stock(t,PASS,sample_stock(),"baseline-cleanup-manual",s.state(t)["revision"])\n    op=s.post(t,PASS,change(1),"movement-cleanup",reason="cleanup",delivery_note=True)\n    baseline_id=s.deletion_catalog(t)["stock_reports"][0]["operation_id"]\n    s.delete_stock_report(t,PASS,baseline_id)\n    assert s.stock(t).empty\n    s.delete_movement(t,PASS,op)\n    assert s.ledger(t).empty\n'''
if 'def test_delete_invoice_after_last_baseline_removed()' not in test:
    test += extra
test_path.write_text(test,encoding='utf-8')

print('v16.14 delete without active baseline applied')
