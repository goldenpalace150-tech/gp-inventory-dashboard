from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_between(text, start_marker, end_marker, replacement, label):
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{label}: start marker not found")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"{label}: end marker not found")
    return text[:start] + replacement + text[end:]


# ---------------------------------------------------------------------------
# 1) Invoice UI: keep drafts as an internal recovery mechanism, not a workflow.
# ---------------------------------------------------------------------------
app_path = ROOT / "inventory_tracker.py"
app = app_path.read_text(encoding="utf-8")

old_dashboard = '''def dashboard_page(store,token,state,stock,daily,actor):
    """Zoho-inspired operational landing page: KPIs, quick actions and recent work."""
    section("Dashboard","Dashboard hint")
    alerts=int(daily["without_invoice"].sum()) if not daily.empty else 0
'''
new_dashboard = '''def dashboard_page(store,token,state,stock,daily,actor):
    """Zoho-inspired operational landing page: KPIs, quick actions and recent work."""
    section("Dashboard","Dashboard hint")
    # Without an active warehouse baseline there is no meaningful current-stock
    # dashboard. Historical movements remain in their own log, but do not masquerade
    # as a current warehouse balance.
    if stock.empty:
        st.info(t("No stock"))
        if actor["role"]=="admin" and st.button(t("Settings"),width="stretch",key="dash_open_settings"):
            st.session_state["nav_request"]="Settings"; st.rerun()
        return
    alerts=int(daily["without_invoice"].sum()) if not daily.empty else 0
'''
if new_dashboard not in app:
    if old_dashboard not in app:
        raise RuntimeError("dashboard empty-stock marker not found")
    app = app.replace(old_dashboard, new_dashboard, 1)

old_error = '''                        except Exception as error:
                            if isinstance(error,(RuntimeError,ValueError)):st.error(str(error)[:1000])
                            else:show_error(error)
        with preview:
'''
new_error = '''                        except Exception as error:
                            # A failed scan must not leave a blank technical "draft"
                            # behind. The operator can simply correct the photo and retry.
                            try:store.discard_draft(token,draft_id)
                            except Exception:pass
                            st.session_state.pop("selected_draft_id",None)
                            if isinstance(error,(RuntimeError,ValueError)):st.error(str(error)[:1000])
                            else:show_error(error)
        with preview:
'''
if new_error not in app:
    if old_error not in app:
        raise RuntimeError("invoice OCR cleanup marker not found")
    app = app.replace(old_error, new_error, 1)

review_block = '''    # Pending invoice_drafts remain an internal safety/recovery layer. Do not expose
    # the database concept as a separate operator workflow.
    drafts=store.drafts(token)
    failed_empty=[d for d in drafts if d.get("image_hash") and not (d.get("payload") or {})]
    if failed_empty:
        for stale in failed_empty:
            try:store.discard_draft(token,stale["draft_id"])
            except Exception:pass
        drafts=store.drafts(token)

    if drafts:
        section("Invoice review")
        choices={d["draft_id"]:d for d in drafts}
        selected=st.session_state.get("selected_draft_id")
        if selected not in choices:selected=drafts[0]["draft_id"]
        if len(choices)>1:
            selected=st.selectbox(t("Unfinished invoices"),list(choices),index=list(choices).index(selected),
                format_func=lambda k: (choices[k]["payload"].get("invoice_number") or choices[k]["source_name"] or k[:8]),
                key="draft_selector")
        st.session_state["selected_draft_id"]=selected
        draft=choices[selected];payload=draft["payload"];suffix=selected+"_"+str(draft["version"])
        rows=payload.get("items") or []
        try:rows,ignored_saved=canonicalize_invoice_rows(rows,stock,drop_unknown=True)
        except AppError:rows,ignored_saved=[],[]
        rows=rows or [{"item_code":"","item_name":"","quantity":None}]
        frame=pd.DataFrame(rows)[["item_code","item_name","quantity"]]
        frame["item_code"]=frame["item_code"].fillna("").astype(str)
        frame["item_name"]=frame["item_name"].fillna("").astype(str)
        frame["quantity"]=pd.to_numeric(frame["quantity"],errors="coerce")
        with st.form("review_"+suffix):
            a,b,c,d=st.columns([1.15,1.5,1.15,1])
            reference=a.text_input(t("Reference"),value=str(payload.get("invoice_number","")),key="reference_"+suffix)
            customer=b.text_input(t("Customer name"),value=str(payload.get("customer_name","")),key="customer_"+suffix)
            driver=c.text_input(t("Driver"),value=str(payload.get("driver","")),key="driver_"+suffix)
            kinds=["","OUT","IN"]
            current_kind=payload.get("movement_type","") if payload.get("movement_type","") in kinds else ""
            kind=d.selectbox(t("Movement type"),kinds,index=kinds.index(current_kind),format_func=lambda k:t(k or "Select"),key="kind_"+suffix)
            st.markdown('<div class="gp-form-gap"></div>',unsafe_allow_html=True)
            edited=st.data_editor(frame,hide_index=True,num_rows="dynamic",width="stretch",key="lines_"+suffix,disabled=["item_name"],
                column_config={"item_code":st.column_config.TextColumn(COL_CODE),"item_name":st.column_config.TextColumn(COL_NAME),
                               "quantity":st.column_config.NumberColumn(COL_QTY,min_value=0,step=0.1,format="%.1f")})
            total=float(pd.to_numeric(edited["quantity"],errors="coerce").fillna(0).sum())
            st.caption(f"{t('Items')}: {len(edited)}   |   {t('Total quantity')}: {total:.1f}")
            st.markdown('<div class="gp-form-gap"></div>',unsafe_allow_html=True)
            duplicate_action=st.selectbox(t("Duplicate action"),["ignore","overwrite"],format_func=lambda x:t("Ignore duplicate" if x=="ignore" else "Overwrite if changed"),key="duplicate_"+suffix,help=t("Duplicate invoice hint"))
            password=st.text_input(t("Approval password"),type="password",key="password_invoice_"+suffix)
            a,b=st.columns(2)
            save=a.form_submit_button(t("Save changes"),width="stretch")
            post=b.form_submit_button(t("Post invoice"),type="primary",width="stretch")
            if save or post:
                try:
                    canonical_rows,_=canonicalize_invoice_rows(edited.to_dict("records"),stock,drop_unknown=False)
                    updated=dict(payload);updated.update(invoice_number=reference.strip(),movement_type=kind,
                        customer_name=customer.strip(),driver=driver.strip(),items=clean_json(canonical_rows))
                    if save:
                        store.save_draft(token,selected,updated,draft["version"]);success()
                    else:
                        changes=match_invoice_lines(updated["items"],store.stock(token),kind)
                        duplicate=store.invoice_duplicate(token,reference,changes,updated)
                        if duplicate.get("exists"):
                            if duplicate.get("identical") or duplicate_action=="ignore":
                                store.discard_draft(token,selected);success(message="Duplicate ignored")
                            else:
                                store.replace_invoice(token,password,changes,nonce("invoice_update_"+selected),reference=reference,
                                    image_hash=draft["image_hash"],reviewed=updated,draft_id=selected,expected_draft_version=draft["version"],
                                    customer_name=customer,driver=driver)
                                success("invoice_update_"+selected,message="Invoice updated")
                        else:
                            store.post(token,password,changes,nonce("invoice_"+selected),source="INVOICE",reference=reference,
                                image_hash=draft["image_hash"],reason=t("Invoices"),delivery_note=True,reviewed=updated,draft_id=selected,
                                expected_draft_version=draft["version"],customer_name=customer,driver=driver)
                            success("invoice_"+selected)
                except Exception as error:show_error(error)
        with st.expander(t("Cancel invoice")):
            if st.button(t("Cancel invoice"),key="discard_"+suffix):
                store.discard_draft(token,selected);success()

'''
app = replace_between(app, '    section("Drafts")\n', '    section("Posted invoices")\n', review_block, "invoice review block")
app_path.write_text(app, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2) Invoice number OCR: the real Golden Palace template prints invoice number
#    around the lower-left summary band, above the printed quantity total.
# ---------------------------------------------------------------------------
worker_path = ROOT / "invoice_ocr_worker.py"
worker = worker_path.read_text(encoding="utf-8")
worker = worker.replace('BUILD = "GP-OCR-WAREHOUSE-v14"', 'BUILD = "GP-OCR-WAREHOUSE-v16"', 1)

targeted = '''def run_targeted_ocr(array):
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

'''
worker = replace_between(worker, 'def run_targeted_ocr(array):\n', 'def parse_codes(boxes, width, height):\n', targeted, "targeted OCR")

summary = '''def parse_summary(boxes, width, height):
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


'''
worker = replace_between(worker, 'def parse_summary(boxes, width, height):\n', 'def extract_invoice(image_path):\n', summary, "summary parser")
worker_path.write_text(worker, encoding="utf-8")

ocr_path = ROOT / "gp_ocr.py"
ocr = ocr_path.read_text(encoding="utf-8")
ocr = ocr.replace('OCR_BUILD = "GP-OCR-WAREHOUSE-v14"', 'OCR_BUILD = "GP-OCR-WAREHOUSE-v16"', 1)
ocr_path.write_text(ocr, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3) Deleting a warehouse report must affect current stock. Rebuild from the
#    newest remaining baseline; if no baseline remains, current stock is empty.
# ---------------------------------------------------------------------------
store_path = ROOT / "gp_store.py"
store = store_path.read_text(encoding="utf-8")
new_delete = '''    def delete_stock_report(self,token,password,operation_id):
        """Delete a warehouse baseline and rebuild the current stock truth.

        The newest remaining baseline becomes authoritative. Later movements are
        replayed on top of it and their before/after balances are recalculated. If
        no warehouse baseline remains, current stock is cleared; historical ledger
        rows remain available as history but cannot act as a stock baseline.
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

            stock_table=self.tables["stock_state"]
            ledger=self.tables["movement_ledger"]
            remaining=c.execute(select(baselines).order_by(baselines.c.created_at.desc()).limit(1).with_for_update()).mappings().first()
            c.execute(delete(stock_table))

            active_source=""
            rebuilt={}
            replayed=0
            now=utcnow()
            if remaining:
                base_payload=remaining["stock"] if isinstance(remaining["stock"],dict) else {}
                active_source=str(base_payload.get("source_name","") or "")
                for raw in base_payload.get("after",[]) or []:
                    key=str(raw.get("item_key","") or "").strip()
                    code=normalize_item_code(raw.get("item_code",""))
                    name=str(raw.get("item_name","") or "").strip()
                    if not key or not name or key in rebuilt:
                        raise AppError("Cannot rebuild stock from the remaining warehouse report")
                    rebuilt[key]=dict(item_key=key,item_code=code,item_name=name,
                        quantity=decimal_qty(raw.get("quantity"),normalize=True),
                        match_key=str(raw.get("match_key","") or item_link_key(code,name)),updated_at=now)

                later=c.execute(select(ledger).where(
                    ledger.c.created_at>remaining["created_at"]
                ).order_by(ledger.c.ledger_id).with_for_update()).mappings().all()
                for row in later:
                    key=row["item_key"]
                    if key not in rebuilt:
                        raise AppError("Cannot delete this report because later movements use an item missing from the previous warehouse report")
                    before=decimal_qty(rebuilt[key]["quantity"])
                    qty=decimal_qty(row["quantity"],positive=True)
                    after=before+qty if row["movement_type"]=="IN" else before-qty
                    if after<0:
                        raise AppError("Cannot delete this report because later OUT movements would make stock negative")
                    rebuilt[key]["quantity"]=after
                    c.execute(update(ledger).where(ledger.c.ledger_id==row["ledger_id"]).values(
                        quantity_before=before,quantity_after=after))
                    replayed+=1

                if rebuilt:
                    c.execute(insert(stock_table),list(rebuilt.values()))

            self._audit(c,actor["username"],"DELETE_STOCK_REPORT",{
                "operation_id":target["operation_id"],
                "source_name":payload.get("source_name",""),
                "current_stock_rebuilt":True,
                "active_source":active_source,
                "remaining_items":len(rebuilt),
                "replayed_movements":replayed,
            })
            self._touch(c)
            return target["operation_id"]

'''
store = replace_between(store, '    def delete_stock_report(self,token,password,operation_id):\n', '    def closure(self,token,day):\n', new_delete, "stock report deletion")
store_path.write_text(store, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4) Labels/build number.
# ---------------------------------------------------------------------------
ui_path = ROOT / "gp_ui.py"
ui = ui_path.read_text(encoding="utf-8")
ui = ui.replace('BUILD = "GP-CLOUD-v15.1"', 'BUILD = "GP-CLOUD-v16"', 1)
old_hint = '"Warehouse report delete hint": "اختر تقرير المستودع وأدخل كلمة مرور الاعتماد ثم اضغط حذف. الحذف متاح للمدير فقط ولا يغيّر الرصيد الحالي أو الحركات اللاحقة."'
new_hint = '"Warehouse report delete hint": "حذف التقرير يعيد بناء الرصيد من آخر تقرير مستودع متبقٍ، وإذا لم يبقَ أي تقرير يتم تفريغ الرصيد الحالي."'
if old_hint in ui:
    ui = ui.replace(old_hint, new_hint, 1)

labels = '''
# ---- v16 operator wording ----
AR.update({
    "Invoice review": "مراجعة الفاتورة",
    "Unfinished invoices": "فواتير غير مكتملة",
    "Save changes": "حفظ التعديلات",
    "Cancel invoice": "إلغاء الفاتورة",
})

'''
if '"Invoice review": "مراجعة الفاتورة"' not in ui:
    marker='\ndef set_language('
    pos=ui.find(marker)
    if pos<0:raise RuntimeError("gp_ui set_language marker not found")
    ui=ui[:pos]+"\n"+labels+ui[pos:]
ui_path.write_text(ui, encoding="utf-8")


# ---------------------------------------------------------------------------
# 5) Regression tests for the three reported failures.
# ---------------------------------------------------------------------------
test_path = ROOT / "tests/test_core_and_ocr.py"
test = test_path.read_text(encoding="utf-8")

old_ref = '''def test_reference_parser_prefers_strong_candidate():
    boxes=[{"text":"8042","score":.95,"x":100,"y":760},{"text":"9.00","score":.9,"x":100,"y":850}]
    reference,total=parse_summary(boxes,1000,1200)
    assert reference=="8042"
'''
new_ref = '''def test_reference_parser_prefers_template_position_over_total_score():
    # Real Golden Palace layout: invoice number is above the lower printed total.
    # The total may have a higher OCR confidence and must still not become "900".
    boxes=[{"text":"8042","score":.72,"x":110,"y":620,"region":"summary"},
           {"text":"9.00","score":.98,"x":110,"y":690,"region":"summary"}]
    reference,total=parse_summary(boxes,1000,1200)
    assert reference=="8042" and total==9.0
'''
if new_ref not in test:
    if old_ref not in test:raise RuntimeError("reference test marker not found")
    test=test.replace(old_ref,new_ref,1)

extra = '''

def test_delete_stock_report_rebuilds_then_clears_current_stock():
    s=Store.for_tests();pw="Test-Password-2026";s.initialize(password=pw);t=s.login("admin",pw)
    first=ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:"010716",COL_NAME:"Camera",COL_QTY:10}]))
    first_op=s.replace_stock(t,pw,first,"base-delete-1",s.state(t)["revision"],source_name="first.xlsx")
    second=ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:"010716",COL_NAME:"Camera",COL_QTY:25}]))
    second_op=s.replace_stock(t,pw,second,"base-delete-2",s.state(t)["revision"],source_name="second.xlsx")
    assert s.stock(t).iloc[0][COL_QTY]==25
    s.delete_stock_report(t,pw,second_op)
    assert s.stock(t).iloc[0][COL_QTY]==10
    s.delete_stock_report(t,pw,first_op)
    assert s.stock(t).empty


def test_invoice_ui_hides_draft_workflow_and_cleans_failed_scans():
    source=(Path(__file__).resolve().parents[1]/"inventory_tracker.py").read_text()
    assert 'section("Drafts")' not in source
    assert 'section("Invoice review")' in source
    assert 't("Save changes")' in source
    assert 'failed_empty=[d for d in drafts' in source
    assert 'store.discard_draft(token,draft_id)' in source

'''
if 'def test_delete_stock_report_rebuilds_then_clears_current_stock()' not in test:
    insert_at=test.find('\ndef test_scan_lock_is_shared():')
    if insert_at<0:raise RuntimeError("test insertion marker not found")
    test=test[:insert_at]+extra+test[insert_at:]

test_path.write_text(test, encoding="utf-8")

print("v16 invoice cleanup, reference OCR and stock-report rebuild applied")
