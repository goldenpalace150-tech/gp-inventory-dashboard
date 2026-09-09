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
# gp_store.py — invoice metadata, duplicate compare/overwrite, richer history
# ---------------------------------------------------------------------------
path = ROOT / "gp_store.py"
text = path.read_text(encoding="utf-8")

movement_history = r'''    def movement_history(self, token):
        with self.engine.connect() as c:
            self._actor(c,token)
            state=c.execute(select(self.tables["app_state"])).mappings().one()
            rows=c.execute(select(self.tables["imported_movement_history"])).mappings().all()
            l=self.tables["movement_ledger"]
            query=select(l)
            if state["history_as_of"]:
                query=query.where(l.c.created_at>state["history_as_of"])
            local=c.execute(query.order_by(l.c.ledger_id)).mappings().all()
            op_ids=sorted({r["operation_id"] for r in local})
            details_by_op={}
            if op_ids:
                o=self.tables["operations"]
                details_by_op={r["operation_id"]:(r["details"] if isinstance(r["details"],dict) else {})
                               for r in c.execute(select(o.c.operation_id,o.c.details).where(o.c.operation_id.in_(op_ids))).mappings().all()}
        result=[]
        for r in rows:
            result.append({COL_CODE:r["item_code"],COL_NAME:r["item_name"],COL_DATE:aware(r["movement_date"]).astimezone(self.tz).replace(tzinfo=None),
                COL_REF:r["reference"],COL_CUSTOMER:r["customer"],COL_IN:float(r["qty_in"]),COL_OUT:float(r["qty_out"]),
                COL_BAL:None if r["balance"] is None else float(r["balance"]),COL_USER:r["username"],COL_NOTE:r["statement"],
                COL_MATCH:r["match_key"],"السائق":""})
        for r in local:
            meta=details_by_op.get(r["operation_id"],{})
            result.append({COL_CODE:r["item_code"],COL_NAME:r["item_name"],COL_DATE:aware(r["created_at"]).astimezone(self.tz).replace(tzinfo=None),
                COL_REF:r["invoice_reference"],COL_CUSTOMER:str(meta.get("customer_name","") or ""),COL_IN:float(r["quantity"]) if r["movement_type"]=="IN" else 0,
                COL_OUT:float(r["quantity"]) if r["movement_type"]=="OUT" else 0,COL_BAL:float(r["quantity_after"]),
                COL_USER:r["username"],COL_NOTE:r["reason"],COL_MATCH:item_link_key(r["item_code"],r["item_name"]),
                "السائق":str(meta.get("driver","") or "")})
        return pd.DataFrame(result)

'''
text = regex_once(text, r"    def movement_history\(self, token\):.*?(?=    def post\()", movement_history, "movement_history")

invoice_methods = r'''    @staticmethod
    def _normalize_changes(changes):
        if not changes:
            raise AppError("No valid movement lines")
        grouped={}
        for r in changes:
            if r["movement_type"] not in ("IN","OUT"):
                raise AppError("Select IN or OUT")
            qty=decimal_qty(r["quantity"],positive=True)
            key=(str(r["item_key"]),r["movement_type"])
            grouped[key]=grouped.get(key,Decimal(0))+qty
        return [dict(item_key=k,movement_type=d,quantity=decimal_qty(q,positive=True))
                for (k,d),q in sorted(grouped.items())]

    @staticmethod
    def _line_signature(rows):
        unit=Decimal("0.0001")
        return sorted((str(r["item_key"]),str(r["movement_type"]),str(decimal_qty(r["quantity"]).quantize(unit))) for r in rows)

    @staticmethod
    def _review_payload(reviewed, customer_name="", driver=""):
        payload=dict(reviewed) if isinstance(reviewed,dict) else {}
        payload["customer_name"]=str(customer_name or "").strip()
        payload["driver"]=str(driver or "").strip()
        return clean_json(payload)

    def post(self, token, password, changes, request_key, *, source="MANUAL", reference="", image_hash=None,
             reason="", delivery_note=False, reviewed=None, draft_id=None, expected_draft_version=None,
             customer_name="", driver=""):
        if source not in ("MANUAL","INVOICE"):
            raise AppError("No valid movement lines")
        normalized=self._normalize_changes(changes)
        reference=str(reference).strip(); customer_name=str(customer_name or "").strip(); driver=str(driver or "").strip()
        if len(reference)>160:raise AppError("Reference is too long")
        if len(customer_name)>180:raise AppError("Customer name is too long")
        if len(driver)>120:raise AppError("Driver name is too long")
        if source=="INVOICE" and not reference:raise AppError("Invoice reference is required")
        if source=="MANUAL" and not str(reason).strip():raise AppError("A movement reason is required")
        if source=="MANUAL" and any(r["movement_type"]=="OUT" for r in normalized) and not delivery_note:
            raise AppError("Confirm the delivery note before stock OUT")
        review_payload=self._review_payload(reviewed,customer_name,driver)
        data=dict(lines=normalized,reference=reference,image_hash=image_hash,reason=reason,delivery_note=bool(delivery_note),
                  draft_id=draft_id,customer_name=customer_name,driver=driver)
        with self.engine.begin() as c:
            actor,op,again,fp=self._operation(c,token,password,request_key,source,data)
            if again:return op
            day=self.today(); self._open_day(c,day)
            inv=self.tables["posted_invoices"]
            if source=="INVOICE":
                q=select(inv.c.invoice_reference).where(inv.c.invoice_reference==reference)
                if c.execute(q).first() or (image_hash and c.execute(select(inv).where(inv.c.image_hash==image_hash)).first()):
                    raise AppError("This invoice or image was already posted")
            if draft_id:
                d=self._owned_draft(c,actor,draft_id)
                if d["status"]!="pending":raise AppError("This draft is no longer pending")
                if expected_draft_version is None or d["version"]!=expected_draft_version:
                    raise AppError("Draft changed in another window. Reload it")
            t=self.tables["stock_state"]
            keys=[r["item_key"] for r in normalized]
            locked=c.execute(select(t).where(t.c.item_key.in_(keys)).order_by(t.c.item_key).with_for_update()).mappings().all()
            balances={r["item_key"]:dict(r) for r in locked}
            if set(keys)!=set(balances):raise AppError("An item is missing from the current stock")
            now=utcnow(); ledger=[]
            for n,line in enumerate(normalized,1):
                r=balances[line["item_key"]]; before=decimal_qty(r["quantity"])
                after=before+line["quantity"] if line["movement_type"]=="IN" else before-line["quantity"]
                decimal_qty(after)
                if line["movement_type"]=="OUT" and after<0:raise AppError("Insufficient stock: "+r["item_code"]+" "+r["item_name"])
                r["quantity"]=after
                ledger.append(dict(operation_id=op,line_no=n,created_at=now,business_date=day,username=actor["username"],source=source,
                    movement_type=line["movement_type"],item_key=r["item_key"],item_code=r["item_code"],item_name=r["item_name"],quantity=line["quantity"],
                    quantity_before=before,quantity_after=after,invoice_reference=reference,without_invoice=not bool(reference),
                    delivery_note=bool(delivery_note),reason=str(reason)))
            details={"reference":reference,"lines":len(ledger),"customer_name":customer_name,"driver":driver}
            self._record_operation(c,actor,op,request_key,source,fp,details)
            c.execute(insert(self.tables["movement_ledger"]),ledger)
            for key,r in balances.items():
                c.execute(update(t).where(t.c.item_key==key).values(quantity=r["quantity"],updated_at=now))
            if source=="INVOICE":
                c.execute(insert(inv).values(invoice_reference=reference,image_hash=image_hash,operation_id=op,posted_at=now,
                    username=actor["username"],recognized_json=review_payload))
            if draft_id:
                d=self.tables["invoice_drafts"]
                c.execute(update(d).where(d.c.draft_id==draft_id).values(status="posted",updated_at=now,version=d.c.version+1))
            return op

    def invoice_duplicate(self,token,reference,changes,reviewed=None):
        reference=str(reference or "").strip()
        if not reference:return {"exists":False,"identical":False}
        normalized=self._normalize_changes(changes)
        new_payload=reviewed if isinstance(reviewed,dict) else {}
        with self.engine.connect() as c:
            self._actor(c,token); inv=self.tables["posted_invoices"]
            row=c.execute(select(inv).where(inv.c.invoice_reference==reference)).mappings().first()
            if not row:return {"exists":False,"identical":False}
            l=self.tables["movement_ledger"]
            lines=c.execute(select(l).where(l.c.operation_id==row["operation_id"]).order_by(l.c.line_no)).mappings().all()
            old_payload=row["recognized_json"] if isinstance(row["recognized_json"],dict) else {}
        same_lines=self._line_signature(lines)==self._line_signature(normalized)
        same_meta=(str(old_payload.get("customer_name","") or "").strip()==str(new_payload.get("customer_name","") or "").strip()
                   and str(old_payload.get("driver","") or "").strip()==str(new_payload.get("driver","") or "").strip())
        return {"exists":True,"identical":bool(same_lines and same_meta),"operation_id":row["operation_id"],
                "posted_at":row["posted_at"],"customer_name":str(old_payload.get("customer_name","") or ""),
                "driver":str(old_payload.get("driver","") or "")}

    def _reverse_invoice_balances_tx(self,c,operation_id):
        operations=self.tables["operations"]; ledger=self.tables["movement_ledger"]
        old=c.execute(select(operations).where(operations.c.operation_id==str(operation_id)).with_for_update()).mappings().first()
        if not old or old["source"]!="INVOICE":raise AppError("Record not found")
        day=self.today()
        if old["business_date"]!=day:raise AppError("Only today's invoices can be updated")
        self._open_day(c,day)
        target=c.execute(select(ledger).where(ledger.c.operation_id==old["operation_id"]).order_by(ledger.c.ledger_id).with_for_update()).mappings().all()
        if not target:raise AppError("Record not found")
        max_target=max(r["ledger_id"] for r in target); deltas={}
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
            if new_current<0:raise AppError("Cannot update because later movements depend on this quantity")
            subsequent=c.execute(select(ledger).where(ledger.c.item_key==key,ledger.c.ledger_id>max_target).order_by(ledger.c.ledger_id).with_for_update()).mappings().all()
            for row in subsequent:
                new_before=decimal_qty(row["quantity_before"])+delta; new_after=decimal_qty(row["quantity_after"])+delta
                if new_before<0 or new_after<0:raise AppError("Cannot update because later movements depend on this quantity")
                c.execute(update(ledger).where(ledger.c.ledger_id==row["ledger_id"]).values(quantity_before=new_before,quantity_after=new_after))
            c.execute(update(stock).where(stock.c.item_key==key).values(quantity=new_current,updated_at=now))
        return dict(old),[dict(r) for r in target]

    def replace_invoice(self,token,password,changes,request_key,*,reference,image_hash=None,reviewed=None,
                        draft_id=None,expected_draft_version=None,customer_name="",driver=""):
        normalized=self._normalize_changes(changes)
        reference=str(reference or "").strip(); customer_name=str(customer_name or "").strip(); driver=str(driver or "").strip()
        if not reference:raise AppError("Invoice reference is required")
        if len(reference)>160 or len(customer_name)>180 or len(driver)>120:raise AppError("Invoice details are too long")
        review_payload=self._review_payload(reviewed,customer_name,driver)
        data=dict(lines=normalized,reference=reference,image_hash=image_hash,draft_id=draft_id,
                  customer_name=customer_name,driver=driver,overwrite=True)
        with self.engine.begin() as c:
            actor,op,again,fp=self._operation(c,token,password,request_key,"INVOICE",data)
            if again:return op
            inv=self.tables["posted_invoices"]
            previous=c.execute(select(inv).where(inv.c.invoice_reference==reference).with_for_update()).mappings().first()
            if not previous:raise AppError("Record not found")
            if image_hash:
                clash=c.execute(select(inv.c.invoice_reference).where(inv.c.image_hash==image_hash,inv.c.invoice_reference!=reference)).first()
                if clash:raise AppError("This image was already posted under another invoice number")
            if draft_id:
                d=self._owned_draft(c,actor,draft_id)
                if d["status"]!="pending":raise AppError("This draft is no longer pending")
                if expected_draft_version is None or d["version"]!=expected_draft_version:
                    raise AppError("Draft changed in another window. Reload it")
            old_op,old_lines=self._reverse_invoice_balances_tx(c,previous["operation_id"])
            ledger=self.tables["movement_ledger"]; operations=self.tables["operations"]
            c.execute(delete(inv).where(inv.c.invoice_reference==reference))
            c.execute(delete(ledger).where(ledger.c.operation_id==previous["operation_id"]))
            c.execute(delete(operations).where(operations.c.operation_id==previous["operation_id"]))
            day=self.today(); t=self.tables["stock_state"]
            keys=[r["item_key"] for r in normalized]
            locked=c.execute(select(t).where(t.c.item_key.in_(keys)).order_by(t.c.item_key).with_for_update()).mappings().all()
            balances={r["item_key"]:dict(r) for r in locked}
            if set(keys)!=set(balances):raise AppError("An item is missing from the current stock")
            now=utcnow(); new_ledger=[]
            for n,line in enumerate(normalized,1):
                r=balances[line["item_key"]]; before=decimal_qty(r["quantity"])
                after=before+line["quantity"] if line["movement_type"]=="IN" else before-line["quantity"]
                decimal_qty(after)
                if line["movement_type"]=="OUT" and after<0:raise AppError("Insufficient stock: "+r["item_code"]+" "+r["item_name"])
                r["quantity"]=after
                new_ledger.append(dict(operation_id=op,line_no=n,created_at=now,business_date=day,username=actor["username"],source="INVOICE",
                    movement_type=line["movement_type"],item_key=r["item_key"],item_code=r["item_code"],item_name=r["item_name"],quantity=line["quantity"],
                    quantity_before=before,quantity_after=after,invoice_reference=reference,without_invoice=False,delivery_note=True,reason="Invoices"))
            details={"reference":reference,"lines":len(new_ledger),"customer_name":customer_name,"driver":driver,
                     "overwritten_from":previous["operation_id"]}
            self._record_operation(c,actor,op,request_key,"INVOICE",fp,details)
            c.execute(insert(ledger),new_ledger)
            for key,r in balances.items():c.execute(update(t).where(t.c.item_key==key).values(quantity=r["quantity"],updated_at=now))
            c.execute(insert(inv).values(invoice_reference=reference,image_hash=image_hash,operation_id=op,posted_at=now,
                username=actor["username"],recognized_json=review_payload))
            if draft_id:
                drafts=self.tables["invoice_drafts"]
                c.execute(update(drafts).where(drafts.c.draft_id==draft_id).values(status="posted",updated_at=now,version=drafts.c.version+1))
            self._audit(c,actor["username"],"UPDATE_INVOICE",{"invoice_reference":reference,
                "old_operation_id":previous["operation_id"],"new_operation_id":op,"old_lines":len(old_lines),"new_lines":len(new_ledger),
                "customer_name":customer_name,"driver":driver})
            return op

    def recent_invoices(self,token,limit=100):
        limit=max(1,min(500,int(limit)))
        with self.engine.connect() as c:
            self._actor(c,token); inv=self.tables["posted_invoices"]
            invoices=c.execute(select(inv).order_by(inv.c.posted_at.desc()).limit(limit)).mappings().all()
            op_ids=[r["operation_id"] for r in invoices]
            ledger=self.tables["movement_ledger"]; operations=self.tables["operations"]
            lines=c.execute(select(ledger).where(ledger.c.operation_id.in_(op_ids)).order_by(ledger.c.ledger_id)).mappings().all() if op_ids else []
            op_rows=c.execute(select(operations.c.operation_id,operations.c.details).where(operations.c.operation_id.in_(op_ids))).mappings().all() if op_ids else []
        by_op={}; details={r["operation_id"]:(r["details"] if isinstance(r["details"],dict) else {}) for r in op_rows}
        for line in lines:by_op.setdefault(line["operation_id"],[]).append(line)
        result=[]
        for row in invoices:
            items=by_op.get(row["operation_id"],[]); meta=details.get(row["operation_id"],{})
            recognized=row["recognized_json"] if isinstance(row["recognized_json"],dict) else {}
            kinds=sorted({x["movement_type"] for x in items})
            result.append({"invoice_reference":row["invoice_reference"],"customer_name":str(recognized.get("customer_name",meta.get("customer_name","")) or ""),
                "driver":str(recognized.get("driver",meta.get("driver","")) or ""),"movement_type":kinds[0] if len(kinds)==1 else " / ".join(kinds),
                "line_count":len(items),"total_quantity":float(sum((decimal_qty(x["quantity"]) for x in items),Decimal(0))),
                "posted_at":row["posted_at"],"username":row["username"],"operation_id":row["operation_id"]})
        return result

'''
text = regex_once(text, r"    def post\(self, token, password, changes, request_key, \*, source=\"MANUAL\".*?(?=    def _owned_draft\()", invoice_methods, "invoice methods")

old_create = '''            if image_hash:
                previous=c.execute(select(t).where(t.c.username==actor["username"],t.c.image_hash==image_hash)).mappings().first()
                if previous:return previous["draft_id"]
            draft_id=str(uuid.uuid4())'''
new_create = '''            if image_hash:
                previous=c.execute(select(t).where(t.c.username==actor["username"],t.c.image_hash==image_hash)).mappings().first()
                if previous:
                    if previous["status"]!="pending":
                        c.execute(update(t).where(t.c.draft_id==previous["draft_id"]).values(status="pending",updated_at=now,version=t.c.version+1))
                        self._touch(c)
                    return previous["draft_id"]
            draft_id=str(uuid.uuid4())'''
text = replace_once(text, old_create, new_create, "reopen duplicate draft")

old_invoice_catalog = '''                invoices.append(dict(operation_id=op["operation_id"],invoice_reference=inv.get("invoice_reference", ""),
                    created_at=op["created_at"],username=op["username"],line_count=len(lines),quantity=float(total),
                    items=[dict(item_code=r["item_code"],item_name=r["item_name"],movement_type=r["movement_type"],quantity=float(r["quantity"])) for r in lines]))'''
new_invoice_catalog = '''                meta=op["details"] if isinstance(op["details"],dict) else {}
                recognized=inv.get("recognized_json",{}) if isinstance(inv.get("recognized_json",{}),dict) else {}
                invoices.append(dict(operation_id=op["operation_id"],invoice_reference=inv.get("invoice_reference", ""),
                    created_at=op["created_at"],username=op["username"],line_count=len(lines),quantity=float(total),
                    customer_name=str(recognized.get("customer_name",meta.get("customer_name","")) or ""),
                    driver=str(recognized.get("driver",meta.get("driver","")) or ""),
                    items=[dict(item_code=r["item_code"],item_name=r["item_name"],movement_type=r["movement_type"],quantity=float(r["quantity"])) for r in lines]))'''
text = replace_once(text, old_invoice_catalog, new_invoice_catalog, "deletion invoice metadata")
path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# inventory_tracker.py — detailed invoice review, duplicate policy, spacing
# ---------------------------------------------------------------------------
path = ROOT / "inventory_tracker.py"
app = path.read_text(encoding="utf-8")

new_invoices_page = r'''def invoices_page(store,token,state,stock):
    section("Invoices","OCR hint")
    ok,_,detail=free_ocr_status()
    code_master_ready = (not stock.empty and stock[COL_CODE].fillna("").astype(str).str.strip().ne("").all())
    with st.container(border=True):
        left,right=st.columns([1.6,1])
        with left:
            uploaded=st.file_uploader(t("Invoice image"),type=["png","jpg","jpeg"],key="invoice_upload")
            if st.checkbox(t("Camera"),key="camera_enabled"):
                capture=st.camera_input(t("Invoice image"),key="camera_capture")
                if capture:uploaded=capture
            a,b=st.columns(2)
            read=a.button(t("Read invoice"),type="primary",disabled=not (uploaded and ok and code_master_ready),width="stretch")
            manual=b.button(t("Manual invoice"),width="stretch")
            if not ok:st.info("OCR is unavailable on this host. Manual invoice entry remains available.")
            if not code_master_ready:st.warning(t("Warehouse code master required"))
            if manual:
                st.session_state["selected_draft_id"]=store.create_draft(token,source_name=t("Manual invoice"))
                st.rerun()
            if read:
                content=uploaded.getvalue(); image_hash=hashlib.sha256(content).hexdigest()
                draft_id=store.create_draft(token,source_name=uploaded.name,image_hash=image_hash)
                st.session_state["selected_draft_id"]=draft_id
                pending={d["draft_id"]:d for d in store.drafts(token)}
                if draft_id not in pending:
                    st.warning(t("This invoice or image was already posted"))
                elif pending[draft_id]["payload"].get("items"):
                    st.info(t("Saved invoice draft found"))
                else:
                    with branded_wait("Reading"):
                        try:
                            result=extract_invoice_data(uploaded,stock); result["movement_type"]=""
                            result.setdefault("customer_name",""); result.setdefault("driver","")
                            store.save_draft(token,draft_id,result,pending[draft_id]["version"])
                            success(message="Saved")
                        except Exception as error:
                            if isinstance(error,(RuntimeError,ValueError)):st.error(str(error)[:1000])
                            else:show_error(error)
        with right:
            if uploaded:st.image(uploaded.getvalue(),width="stretch")
            else:st.markdown(section_html("Review","Draft hint"),unsafe_allow_html=True)

    section("Drafts")
    drafts=store.drafts(token)
    if drafts:
        choices={d["draft_id"]:d for d in drafts}
        selected=st.session_state.get("selected_draft_id")
        if selected not in choices:selected=drafts[0]["draft_id"]
        selected=st.selectbox(t("Drafts"),list(choices),index=list(choices).index(selected),
            format_func=lambda k: (choices[k]["payload"].get("invoice_number") or choices[k]["source_name"] or k[:8])+" / "+choices[k]["username"],
            key="draft_selector")
        st.session_state["selected_draft_id"]=selected
        draft=choices[selected];payload=draft["payload"];suffix=selected+"_"+str(draft["version"])
        for message in payload.get("warnings",[])[:6]:st.warning(str(message))
        st.caption(t("Draft hint"))
        rows=payload.get("items") or []
        try:rows,ignored_saved=canonicalize_invoice_rows(rows,stock,drop_unknown=True)
        except AppError:rows,ignored_saved=[],[]
        if ignored_saved:st.warning(t("Ignored non-item numbers")+": "+", ".join(ignored_saved[:8]))
        rows=rows or [{"item_code":"","item_name":"","quantity":None}]
        frame=pd.DataFrame(rows)[["item_code","item_name","quantity"]]
        frame["item_code"]=frame["item_code"].fillna("").astype(str)
        frame["item_name"]=frame["item_name"].fillna("").astype(str)
        frame["quantity"]=pd.to_numeric(frame["quantity"],errors="coerce")
        with st.form("review_"+suffix):
            st.markdown("#### "+t("Invoice details"))
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
            duplicate_action=st.selectbox(t("Duplicate action"),["ignore","overwrite"],format_func=lambda x:t("Ignore duplicate" if x=="ignore" else "Overwrite if changed"),key="duplicate_"+suffix)
            st.caption(t("Duplicate invoice hint"))
            review_checked=st.checkbox(t("Confirm review"),key="checked_"+suffix)
            password=st.text_input(t("Approval password"),type="password",key="password_invoice_"+suffix)
            a,b=st.columns(2)
            save=a.form_submit_button(t("Save draft"),width="stretch")
            post=b.form_submit_button(t("Post invoice"),type="primary",width="stretch")
            if save or post:
                try:
                    canonical_rows,_=canonicalize_invoice_rows(edited.to_dict("records"),stock,drop_unknown=False)
                    updated=dict(payload);updated.update(invoice_number=reference.strip(),movement_type=kind,
                        customer_name=customer.strip(),driver=driver.strip(),items=clean_json(canonical_rows))
                    if save:
                        store.save_draft(token,selected,updated,draft["version"]);success()
                    else:
                        if not review_checked:raise AppError("Confirm review")
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
        with st.expander(t("Discard")):
            discard_ok=st.checkbox(t("Discard"),key="discard_check_"+suffix)
            if st.button(t("Discard"),disabled=not discard_ok,key="discard_"+suffix):
                store.discard_draft(token,selected);success()
    else:
        st.info(t("No drafts"))

    section("Posted invoices")
    posted=store.recent_invoices(token,100)
    if posted:
        history=pd.DataFrame(posted)
        history["total_quantity"]=pd.to_numeric(history["total_quantity"],errors="coerce").fillna(0).map(lambda x:f"{x:.1f}")
        history["posted_at"]=history["posted_at"].map(lambda x:aware(x).astimezone(store.tz).strftime("%Y-%m-%d %H:%M"))
        shown=history[["invoice_reference","customer_name","driver","movement_type","line_count","total_quantity","posted_at","username"]].rename(columns={
            "invoice_reference":t("Invoice number"),"customer_name":t("Customer name"),"driver":t("Driver"),"movement_type":t("Movement type"),
            "line_count":t("Items"),"total_quantity":t("Total quantity"),"posted_at":t("Date"),"username":t("Username")})
        table(shown,height=320)
    else:st.info(t("No posted invoices"))


'''
app = regex_once(app, r"def invoices_page\(store,token,state,stock\):.*?(?=def movements_page\()", new_invoices_page, "invoices_page")

app = app.replace('qty=b.number_input(t("Quantity"),min_value=0.0,step=1.0,format="%.4f")',
                  'qty=b.number_input(t("Quantity"),min_value=0.0,step=1.0,format="%.1f")')
app = app.replace('        a,b=st.columns(2)\n        reference=a.text_input(t("Reference optional"))',
                  '        st.markdown(\'<div class="gp-form-gap"></div>\',unsafe_allow_html=True)\n        a,b=st.columns(2)\n        reference=a.text_input(t("Reference optional"))')
app = app.replace('        password=st.text_input(t("Approval password"),type="password",key="password_manual_"+request)',
                  '        st.markdown(\'<div class="gp-form-gap"></div>\',unsafe_allow_html=True)\n        password=st.text_input(t("Approval password"),type="password",key="password_manual_"+request)')
# Keep the existing divider lines, but give logical settings groups breathing room without extra bordered boxes.
app = app.replace('                st.divider()\n                a,b=st.columns(2)',
                  '                st.divider()\n                st.markdown(\'<div class="gp-form-gap"></div>\',unsafe_allow_html=True)\n                a,b=st.columns(2)',1)
app = app.replace('                st.divider()\n                prefixes=st.text_input',
                  '                st.divider()\n                st.markdown(\'<div class="gp-form-gap"></div>\',unsafe_allow_html=True)\n                prefixes=st.text_input',1)
path.write_text(app, encoding="utf-8")


# ---------------------------------------------------------------------------
# gp_ui.py — v11 build + Arabic labels
# ---------------------------------------------------------------------------
path = ROOT / "gp_ui.py"
ui = path.read_text(encoding="utf-8")
ui = re.sub(r'BUILD = "GP-CLOUD-v\d+"', 'BUILD = "GP-CLOUD-v11"', ui, count=1)
if "v11 invoice workflow" not in ui:
    ui += '''\n\n# ---- v11 invoice workflow / warehouse update ----\nAR.update({\n    "Invoice details": "تفاصيل الفاتورة",\n    "Invoice number": "رقم الفاتورة",\n    "Customer name": "اسم الزبون",\n    "Driver": "السائق",\n    "Total quantity": "إجمالي الكمية",\n    "Duplicate action": "عند تكرار رقم الفاتورة",\n    "Ignore duplicate": "تجاهل المكرر",\n    "Overwrite if changed": "تحديث إذا تغيرت البنود",\n    "Duplicate invoice hint": "إذا كان رقم الفاتورة موجوداً: يتم تجاهله عند التطابق، أو يمكن تحديثه بأمان عند تعديل البنود أو الكميات.",\n    "Duplicate ignored": "الفاتورة موجودة مسبقاً ولم يتم إنشاء حركة جديدة.",\n    "Invoice updated": "تم تحديث الفاتورة وإعادة احتساب أثرها على المستودع.",\n    "Posted invoices": "الفواتير المعتمدة",\n    "No posted invoices": "لا توجد فواتير معتمدة.",\n    "Saved invoice draft found": "تم العثور على مسودة محفوظة لهذه الصورة. راجعها أدناه.",\n    "Customer name is too long": "اسم الزبون طويل جداً.",\n    "Driver name is too long": "اسم السائق طويل جداً.",\n    "Invoice details are too long": "إحدى بيانات الفاتورة طويلة جداً.",\n    "Only today's invoices can be updated": "يمكن تحديث فواتير اليوم المفتوح فقط.",\n    "Cannot update because later movements depend on this quantity": "لا يمكن تحديث الفاتورة لأن حركات لاحقة تعتمد على هذه الكمية.",\n    "This image was already posted under another invoice number": "تم اعتماد هذه الصورة سابقاً تحت رقم فاتورة آخر.",\n})\n'''
path.write_text(ui, encoding="utf-8")


# ---------------------------------------------------------------------------
# assets/style.css — consistent whitespace without new borders
# ---------------------------------------------------------------------------
path = ROOT / "assets/style.css"
css = path.read_text(encoding="utf-8")
if ".gp-form-gap" not in css:
    css += '''\n\n/* v11: visual separation between logical form groups without extra bordered cards. */\n.gp-form-gap { height: 22px; width: 100%; }\n@media (max-width: 800px) { .gp-form-gap { height: 14px; } }\n'''
path.write_text(css, encoding="utf-8")

print("v11 warehouse update applied")
