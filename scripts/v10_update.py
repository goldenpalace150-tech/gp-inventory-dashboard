from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Missing update marker: {label}")
    return text.replace(old, new, 1)


# ---------------- gp_store.py ----------------
path = ROOT / "gp_store.py"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "    def replace_stock(self, token, password, df, request_key, expected_revision):",
    "    def replace_stock(self, token, password, df, request_key, expected_revision, source_name=\"\"):",
    "replace_stock source name",
)
text = replace_once(
    text,
    '''            c.execute(insert(self.tables["baseline_snapshots"]).values(operation_id=op,created_at=utcnow(),
                username=actor["username"],stock={"before":clean_json([dict(r) for r in old]),"after":clean_json(data)}))
            c.execute(delete(t)); c.execute(insert(t),rows)
            self._record_operation(c,actor,op,request_key,"BASELINE",fp,{"row_count":len(rows)})''',
    '''            source_name=str(source_name or "")[:240]
            c.execute(insert(self.tables["baseline_snapshots"]).values(operation_id=op,created_at=utcnow(),
                username=actor["username"],stock={"before":clean_json([dict(r) for r in old]),"after":clean_json(data),"source_name":source_name}))
            c.execute(delete(t)); c.execute(insert(t),rows)
            self._record_operation(c,actor,op,request_key,"BASELINE",fp,{"row_count":len(rows),"source_name":source_name})''',
    "baseline source metadata",
)

if "    def deletion_catalog(self,token):" not in text:
    marker = "    def closure(self,token,day):\n"
    block = r'''    def deletion_catalog(self,token):
        """Admin-only list of current deletable business records and warehouse reports."""
        with self.engine.connect() as c:
            actor=self._actor(c,token)
            if actor["role"]!="admin":raise AppError("Administrator access required")
            today=self.today(); operations=self.tables["operations"]; ledger=self.tables["movement_ledger"]
            op_rows=c.execute(select(operations).where(
                operations.c.business_date==today,
                operations.c.source.in_(["MANUAL","INVOICE"])
            ).order_by(operations.c.created_at.desc())).mappings().all()
            op_ids=[r["operation_id"] for r in op_rows]
            line_rows=c.execute(select(ledger).where(ledger.c.operation_id.in_(op_ids)).order_by(ledger.c.ledger_id)).mappings().all() if op_ids else []
            by_op={}
            for row in line_rows:by_op.setdefault(row["operation_id"],[]).append(dict(row))
            posted=self.tables["posted_invoices"]
            invoice_rows=c.execute(select(posted).where(posted.c.operation_id.in_(op_ids))).mappings().all() if op_ids else []
            invoices_by_op={r["operation_id"]:dict(r) for r in invoice_rows}
            baselines=self.tables["baseline_snapshots"]
            baseline_rows=c.execute(select(baselines).order_by(baselines.c.created_at.desc()).limit(30)).mappings().all()

        invoices=[]; movements=[]
        for op in op_rows:
            lines=by_op.get(op["operation_id"],[])
            total=sum((decimal_qty(r["quantity"]) for r in lines),Decimal(0))
            if op["source"]=="INVOICE":
                inv=invoices_by_op.get(op["operation_id"],{})
                invoices.append(dict(operation_id=op["operation_id"],invoice_reference=inv.get("invoice_reference", ""),
                    created_at=op["created_at"],username=op["username"],line_count=len(lines),quantity=float(total),
                    items=[dict(item_code=r["item_code"],item_name=r["item_name"],movement_type=r["movement_type"],quantity=float(r["quantity"])) for r in lines]))
            else:
                first=lines[0] if lines else {}
                movements.append(dict(operation_id=op["operation_id"],created_at=op["created_at"],username=op["username"],
                    item_code=first.get("item_code", ""),item_name=first.get("item_name", ""),movement_type=first.get("movement_type", ""),
                    quantity=float(total),reference=first.get("invoice_reference", ""),reason=first.get("reason", "")))
        reports=[]
        for row in baseline_rows:
            payload=row["stock"] if isinstance(row["stock"],dict) else {}
            reports.append(dict(operation_id=row["operation_id"],created_at=row["created_at"],username=row["username"],
                source_name=str(payload.get("source_name", "") or ""),item_count=len(payload.get("after",[]) or [])))
        return {"invoices":invoices,"movements":movements,"stock_reports":reports}

    def _delete_posted_operation_tx(self,c,actor,operation_id,expected_source):
        operations=self.tables["operations"]; ledger=self.tables["movement_ledger"]
        op=c.execute(select(operations).where(operations.c.operation_id==str(operation_id)).with_for_update()).mappings().first()
        if not op or op["source"]!=expected_source:raise AppError("Record not found")
        today=self.today()
        if op["business_date"]!=today:raise AppError("Only today's invoices and movements can be deleted")
        self._open_day(c,today)
        target=c.execute(select(ledger).where(ledger.c.operation_id==op["operation_id"]).order_by(ledger.c.ledger_id).with_for_update()).mappings().all()
        if not target:raise AppError("Record not found")
        max_target_id=max(r["ledger_id"] for r in target)
        deltas={}
        for row in target:
            key=row["item_key"]
            delta=row["quantity"] if row["movement_type"]=="OUT" else -row["quantity"]
            deltas[key]=deltas.get(key,Decimal(0))+delta

        stock=self.tables["stock_state"]
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

        invoice_reference=""; image_hash=None
        if expected_source=="INVOICE":
            invoices=self.tables["posted_invoices"]
            inv=c.execute(select(invoices).where(invoices.c.operation_id==op["operation_id"]).with_for_update()).mappings().first()
            if inv:
                invoice_reference=inv["invoice_reference"]; image_hash=inv["image_hash"]
                c.execute(delete(invoices).where(invoices.c.operation_id==op["operation_id"]))
                if image_hash:
                    drafts=self.tables["invoice_drafts"]
                    c.execute(update(drafts).where(
                        drafts.c.username==inv["username"],drafts.c.image_hash==image_hash,drafts.c.status=="posted"
                    ).values(status="pending",updated_at=now,version=drafts.c.version+1))

        c.execute(delete(ledger).where(ledger.c.operation_id==op["operation_id"]))
        c.execute(delete(operations).where(operations.c.operation_id==op["operation_id"]))
        action="DELETE_INVOICE" if expected_source=="INVOICE" else "DELETE_MOVEMENT"
        self._audit(c,actor["username"],action,{"operation_id":op["operation_id"],"invoice_reference":invoice_reference,"line_count":len(target)})
        self._touch(c)
        return op["operation_id"]

    def delete_invoice(self,token,password,invoice_reference):
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token,password,admin=True)
            invoices=self.tables["posted_invoices"]
            inv=c.execute(select(invoices).where(invoices.c.invoice_reference==str(invoice_reference)).with_for_update()).mappings().first()
            if not inv:raise AppError("Record not found")
            return self._delete_posted_operation_tx(c,actor,inv["operation_id"],"INVOICE")

    def delete_movement(self,token,password,operation_id):
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token,password,admin=True)
            return self._delete_posted_operation_tx(c,actor,operation_id,"MANUAL")

    def delete_stock_report(self,token,password,operation_id):
        """Undo only the latest baseline when no later movement/closure depends on it."""
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token,password,admin=True)
            baselines=self.tables["baseline_snapshots"]; operations=self.tables["operations"]
            latest=c.execute(select(baselines).order_by(baselines.c.created_at.desc()).limit(1).with_for_update()).mappings().first()
            if not latest or latest["operation_id"]!=str(operation_id):
                raise AppError("Only the latest warehouse report can be deleted")
            op=c.execute(select(operations).where(operations.c.operation_id==latest["operation_id"]).with_for_update()).mappings().first()
            if not op or op["source"]!="BASELINE":raise AppError("Record not found")
            ledger=self.tables["movement_ledger"]
            if c.execute(select(ledger.c.ledger_id).where(ledger.c.created_at>latest["created_at"]).limit(1)).first():
                raise AppError("Delete later movements before deleting this warehouse report")
            closures=self.tables["daily_closures"]
            if c.execute(select(closures.c.business_date).where(closures.c.closed_at>=latest["created_at"]).limit(1)).first():
                raise AppError("A closed day depends on this warehouse report")
            payload=latest["stock"] if isinstance(latest["stock"],dict) else {}
            previous=payload.get("before",[]) or []
            rows=[]; now=utcnow()
            for row in previous:
                rows.append(dict(item_key=str(row.get("item_key", "")),item_code=normalize_item_code(row.get("item_code", "")),
                    item_name=str(row.get("item_name", "")),quantity=decimal_qty(row.get("quantity",0),normalize=True),
                    match_key=str(row.get("match_key", "")) or item_link_key(row.get("item_code", ""),row.get("item_name", "")),updated_at=now))
            stock=self.tables["stock_state"]
            c.execute(delete(stock))
            if rows:c.execute(insert(stock),rows)
            c.execute(delete(baselines).where(baselines.c.operation_id==latest["operation_id"]))
            c.execute(delete(operations).where(operations.c.operation_id==latest["operation_id"]))
            self._audit(c,actor["username"],"DELETE_STOCK_REPORT",{"operation_id":latest["operation_id"],"restored_items":len(rows),"source_name":payload.get("source_name","")})
            self._touch(c)
            return latest["operation_id"]

'''
    if marker not in text:
        raise RuntimeError("Missing update marker: deletion methods")
    text = text.replace(marker, block + marker, 1)
path.write_text(text, encoding="utf-8")


# ---------------- inventory_tracker.py ----------------
path = ROOT / "inventory_tracker.py"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''                            store.replace_stock(token,password,df,nonce("baseline"),state["revision"])''',
    '''                            store.replace_stock(token,password,df,nonce("baseline"),state["revision"],source_name=uploaded.name)''',
    "stock source name UI",
)

if "def deletion_panel(store,token):" not in text:
    marker = "\ndef settings_page(store,token,state,stock,actor):\n"
    block = r'''
def _local_stamp(store,value):
    try:return aware(value).astimezone(store.tz).strftime("%Y-%m-%d %H:%M")
    except Exception:return str(value)


def deletion_panel(store,token):
    catalog=store.deletion_catalog(token)
    st.warning(t("Delete data warning"))

    st.markdown("#### "+t("Delete invoice"))
    invoices=catalog["invoices"]
    if invoices:
        by_ref={row["invoice_reference"]:row for row in invoices if row["invoice_reference"]}
        refs=list(by_ref)
        selected=st.selectbox(t("Invoices"),refs,format_func=lambda ref:
            f"{ref} | {_local_stamp(store,by_ref[ref]['created_at'])} | {by_ref[ref]['line_count']} {t('Items')}",key="delete_invoice_select")
        with st.form("delete_invoice_form"):
            st.caption(t("Delete reverses warehouse quantity"))
            confirmed=st.checkbox(t("Confirm delete"),key="delete_invoice_confirm")
            password=st.text_input(t("Approval password"),type="password",key="password_delete_invoice")
            if st.form_submit_button(t("Delete invoice"),type="primary",disabled=not confirmed):
                try:store.delete_invoice(token,password,selected);success(message="Deleted")
                except Exception as error:show_error(error)
    else:st.info(t("No deletable invoices"))

    st.divider()
    st.markdown("#### "+t("Delete movement"))
    movements=catalog["movements"]
    if movements:
        by_id={row["operation_id"]:row for row in movements}; ids=list(by_id)
        selected=st.selectbox(t("Movements"),ids,format_func=lambda op:
            f"{_local_stamp(store,by_id[op]['created_at'])} | {by_id[op]['movement_type']} | {by_id[op]['item_code']} | {by_id[op]['item_name']} | {by_id[op]['quantity']:g}",key="delete_movement_select")
        with st.form("delete_movement_form"):
            st.caption(t("Delete reverses warehouse quantity"))
            confirmed=st.checkbox(t("Confirm delete"),key="delete_movement_confirm")
            password=st.text_input(t("Approval password"),type="password",key="password_delete_movement")
            if st.form_submit_button(t("Delete movement"),type="primary",disabled=not confirmed):
                try:store.delete_movement(token,password,selected);success(message="Deleted")
                except Exception as error:show_error(error)
    else:st.info(t("No deletable movements"))

    st.divider()
    st.markdown("#### "+t("Delete warehouse report"))
    reports=catalog["stock_reports"]
    if reports:
        by_id={row["operation_id"]:row for row in reports}; ids=list(by_id)
        selected=st.selectbox(t("Warehouse reports"),ids,format_func=lambda op:
            f"{by_id[op]['source_name'] or t('Warehouse report')} | {_local_stamp(store,by_id[op]['created_at'])} | {by_id[op]['item_count']} {t('Items')}",key="delete_stock_report_select")
        latest=ids[0]
        if selected!=latest:st.info(t("Only latest warehouse report can be deleted"))
        with st.form("delete_stock_report_form"):
            st.caption(t("Warehouse report delete hint"))
            confirmed=st.checkbox(t("Confirm delete"),key="delete_stock_report_confirm")
            password=st.text_input(t("Approval password"),type="password",key="password_delete_stock")
            if st.form_submit_button(t("Delete warehouse report"),type="primary",disabled=not (confirmed and selected==latest)):
                try:store.delete_stock_report(token,password,selected);success(message="Deleted")
                except Exception as error:show_error(error)
    else:st.info(t("No warehouse reports"))

'''
    if marker not in text:
        raise RuntimeError("Missing update marker: deletion panel")
    text = text.replace(marker, block + marker, 1)

text = replace_once(
    text,
    '''        section("Import data")
        imports_panel(store,token,state,stock)
        with st.expander(t("Reorder settings")):''',
    '''        section("Import data")
        imports_panel(store,token,state,stock)
        st.divider()
        with st.expander(t("Delete data")):
            deletion_panel(store,token)
        st.divider()
        with st.expander(t("Reorder settings")):''',
    "settings delete section",
)
text = replace_once(
    text,
    '''                lead=a.number_input(t("Lead days"),min_value=1,max_value=730,value=int(settings["lead_days"]))
                safety=b.number_input(t("Safety days"),min_value=0,max_value=365,value=int(settings["safety_days"]))
                slow=c.number_input(t("Slow days"),min_value=30,max_value=730,value=int(settings["slow_days"]))
                a,b=st.columns(2)
                demand=a.number_input(t("Demand days"),min_value=7,max_value=730,value=int(settings["demand_window_days"]))
                review=b.number_input(t("Review days"),min_value=1,max_value=365,value=int(settings["review_days"]))
                prefixes=st.text_input(t("Purchase prefixes"),value=", ".join(settings["purchase_prefixes"]))
                password=st.text_input(t("Approval password"),type="password",key="password_settings")''',
    '''                lead=a.number_input(t("Lead days"),min_value=1,max_value=730,value=int(settings["lead_days"]))
                safety=b.number_input(t("Safety days"),min_value=0,max_value=365,value=int(settings["safety_days"]))
                slow=c.number_input(t("Slow days"),min_value=30,max_value=730,value=int(settings["slow_days"]))
                st.divider()
                a,b=st.columns(2)
                demand=a.number_input(t("Demand days"),min_value=7,max_value=730,value=int(settings["demand_window_days"]))
                review=b.number_input(t("Review days"),min_value=1,max_value=365,value=int(settings["review_days"]))
                st.divider()
                prefixes=st.text_input(t("Purchase prefixes"),value=", ".join(settings["purchase_prefixes"]))
                st.divider()
                password=st.text_input(t("Approval password"),type="password",key="password_settings")''',
    "settings divider lines",
)
path.write_text(text, encoding="utf-8")


# ---------------- gp_ui.py ----------------
path = ROOT / "gp_ui.py"
text = path.read_text(encoding="utf-8")
text = text.replace('BUILD = "GP-CLOUD-v9"', 'BUILD = "GP-CLOUD-v10"')
text = replace_once(
    text,
    '''def loading_html(message="Loading"):
    d = language_dir()
    return f'''<div class="gp-loading-backdrop"><div class="gp-loading-card" dir="{d}">
      <img src="data:image/png;base64,{_icon_data()}" alt="Golden Palace">
      <div class="gp-loading-ring"></div><strong>{html.escape(t(message))}</strong>
    </div></div>''' ''',
    '''def loading_html(message="Loading"):
    d = language_dir()
    return f'''<div class="gp-loading-backdrop" role="status" aria-live="polite"><div class="gp-loading-card" dir="{d}">
      <img class="gp-loading-logo" src="data:image/jpeg;base64,{_logo_data()}" alt="Golden Palace">
      <div class="gp-loading-ring"></div><strong>{html.escape(t(message))}</strong>
    </div></div>''' ''',
    "center loading popup html",
)
if "Delete data warning" not in text:
    text += '''\n\n# ---- v10 deletion controls / centered loading popup ----\nAR.update({\n    "Delete data": "حذف البيانات",\n    "Delete invoice": "حذف فاتورة",\n    "Delete movement": "حذف حركة",\n    "Delete warehouse report": "حذف تقرير المستودع",\n    "Warehouse reports": "تقارير المستودع",\n    "Warehouse report": "تقرير المستودع",\n    "Confirm delete": "أؤكد الحذف",\n    "Deleted": "تم الحذف",\n    "Delete data warning": "الحذف متاح للمدير فقط ويعكس تأثير العملية على رصيد المستودع مع الاحتفاظ بسجل تدقيق.",\n    "Delete reverses warehouse quantity": "سيتم عكس تأثير هذه العملية على رصيد المستودع وإعادة احتساب الحركات اللاحقة.",\n    "Warehouse report delete hint": "يمكن حذف أحدث تقرير مستودع فقط، بشرط ألا توجد حركات أو إقفالات لاحقة تعتمد عليه.",\n    "Only latest warehouse report can be deleted": "يمكن حذف أحدث تقرير مستودع فقط.",\n    "No deletable invoices": "لا توجد فواتير قابلة للحذف اليوم.",\n    "No deletable movements": "لا توجد حركات قابلة للحذف اليوم.",\n    "No warehouse reports": "لا توجد تقارير مستودع محفوظة.",\n    "Record not found": "السجل غير موجود أو تم حذفه مسبقاً.",\n    "Only today's invoices and movements can be deleted": "يمكن حذف فواتير وحركات اليوم المفتوح فقط.",\n    "Cannot delete because later movements depend on this quantity": "لا يمكن الحذف لأن حركات لاحقة تعتمد على هذه الكمية.",\n    "Only the latest warehouse report can be deleted": "يمكن حذف أحدث تقرير مستودع فقط.",\n    "Delete later movements before deleting this warehouse report": "احذف الحركات اللاحقة أولاً قبل حذف تقرير المستودع.",\n    "A closed day depends on this warehouse report": "لا يمكن حذف التقرير لأن يوماً مقفلاً يعتمد عليه.",\n})\n'''
path.write_text(text, encoding="utf-8")


# ---------------- assets/style.css ----------------
path = ROOT / "assets/style.css"
text = path.read_text(encoding="utf-8")
if ".gp-loading-backdrop" not in text:
    text += r'''

/* v10: centered modal loading state, independent of the widget that started the work. */
.gp-loading-backdrop {
 position:fixed; inset:0; z-index:999999; display:flex; align-items:center; justify-content:center;
 background:rgba(18,38,62,.26); backdrop-filter:blur(2px); -webkit-backdrop-filter:blur(2px);
}
.gp-loading-card {
 width:min(360px,calc(100vw - 42px)); background:#fff; border:1px solid var(--gp-line); border-top:4px solid var(--gp-gold);
 border-radius:20px; padding:24px 28px 22px; box-shadow:0 24px 70px #0b1a2d40; text-align:center;
 display:flex; flex-direction:column; align-items:center; gap:14px;
}
.gp-loading-logo { display:block; width:min(250px,78%); height:auto; border-radius:10px; }
.gp-loading-ring { width:32px; height:32px; border:4px solid #dce3eb; border-top-color:var(--gp-navy); border-radius:50%; animation:gp-spin .8s linear infinite; }
.gp-loading-card strong { color:var(--gp-ink); font-size:1rem; }
@keyframes gp-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion:reduce) { .gp-loading-ring { animation-duration:1.8s; } }
'''
path.write_text(text, encoding="utf-8")

print("v10 update applied")
