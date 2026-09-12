"""Golden Palace cloud inventory, v5.
Entry point: streamlit run inventory_tracker.py
Python 3.11 / Supabase PostgreSQL. No local inventory fallback.
"""
from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import logging
import uuid

import pandas as pd
import streamlit as st
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

from gp_core import (
    COL_CODE,COL_NAME,COL_QTY,COL_KEY,COL_MATCH,COL_DATE,
    read_stock_report,read_movement_report,build_inventory_analysis,
)
from gp_store import Store, AppError, clean_json, utcnow, aware
from gp_ui import (BUILD, ROOT, t, css, brand_html, status_html, kpis_html, section_html,
                   set_language, loading_html, language_marker)
from gp_ocr import free_ocr_status, extract_invoice_data
from gp_invoice import match_invoice_lines, canonicalize_invoice_rows
from gp_reports import visible_frame, excel_bytes, day_report_sheets

st.set_page_config(page_title="Golden Palace | Inventory",
                   page_icon=Image.open(ROOT/"assets/favicon.png"),layout="wide",initial_sidebar_state="auto")
st.markdown("<style>"+css()+"</style>",unsafe_allow_html=True)
LOG=logging.getLogger("golden_palace")


def show_error(error):
    if isinstance(error,AppError):
        st.error(t(str(error)))
    else:
        reference=str(uuid.uuid4())[:8]
        sqlstate=getattr(getattr(error,"orig",None),"sqlstate","")
        # No repr/traceback of a database error: it may include secrets or invoice data.
        LOG.error("App failure id=%s type=%s sqlstate=%s",reference,type(error).__name__,sqlstate)
        st.error("Save/connection not confirmed. Refresh the data before retrying. "
                 "No local database is used. Reference: "+reference)


@st.cache_resource(show_spinner=False)
def get_store(settings_json):
    return Store.from_settings(json.loads(settings_json))


@st.cache_data(show_spinner=False,ttl=15,max_entries=24)
def get_shell(database_id,token_hash,_store,_token):
    actor=_store.actor(_token)
    state=_store.state(_token)
    stock=_store.stock(_token)
    daily=_store.ledger(_token,_store.today())
    return actor,state,stock,daily


@st.cache_data(show_spinner=False,max_entries=6)
def parse_stock_report(raw):
    return read_stock_report(raw)


@st.cache_data(show_spinner=False,max_entries=6)
def parse_history_report(raw):
    return read_movement_report(raw)


@contextmanager
def branded_wait(message="Loading"):
    holder=st.empty()
    holder.markdown(loading_html(message),unsafe_allow_html=True)
    try:
        yield
    finally:
        holder.empty()


@st.cache_data(show_spinner=False,ttl=120,max_entries=2)
def get_analysis(revision,settings_json,database_id,_store,_token):
    settings=json.loads(settings_json)
    stock=_store.stock(_token)
    history=_store.movement_history(_token)
    if stock.empty or history.empty:return pd.DataFrame()
    return build_inventory_analysis(stock,history,settings["lead_days"],settings["safety_days"],settings["slow_days"],
                                    settings["demand_window_days"],settings["review_days"],settings["purchase_prefixes"])


def analysis_now(store,token,state):
    return get_analysis(state["revision"],json.dumps(state["settings"],sort_keys=True),
                        str(store.engine.url.render_as_string(hide_password=True)),store,token)


def section(title,note=""):
    st.markdown(section_html(title,note),unsafe_allow_html=True)


def nonce(name):
    key="operation_"+name
    if key not in st.session_state:st.session_state[key]=str(uuid.uuid4())
    return st.session_state[key]


def success(name=None,message="Saved"):
    if name:st.session_state.pop("operation_"+name,None)
    get_shell.clear(); get_analysis.clear()
    st.session_state["flash"]=t(message)
    st.session_state["wipe_passwords"]=True
    st.rerun()


def table(frame,**kwargs):
    if frame is None or frame.empty:
        st.info(t("Empty"));return
    st.dataframe(frame,hide_index=True,width="stretch",**kwargs)


def export_button(name,sheets):
    # Do not keep large XLSX objects in the session across OCR scans.
    if st.button(t("Prepare export"),key="prepare_"+name):
        data=excel_bytes(sheets)
        st.download_button(t("Download"),data,file_name=name+".xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key="download_"+name)


def dashboard_page(store,token,state,stock,daily,actor):
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
    available=int((stock[COL_QTY]>0).sum()) if not stock.empty else 0
    out_count=int((stock[COL_QTY]<=0).sum()) if not stock.empty else 0
    st.markdown(kpis_html([
        ("Items",f"{len(stock):,}","Stock"),
        ("Available",f"{available:,}","Items"),
        ("Movements",f"{len(daily):,}","Today"),
        ("Without invoice",f"{alerts:,}","Today"),
    ]),unsafe_allow_html=True)

    st.markdown("### "+t("Quick actions"))
    q1,q2,q3,q4=st.columns(4)
    if q1.button(t("Read invoice"),type="primary",width="stretch",key="dash_invoice"):
        st.session_state["nav_request"]="Invoices"; st.rerun()
    if q2.button(t("New movement"),width="stretch",key="dash_movement"):
        st.session_state["nav_request"]="Movements"; st.rerun()
    if q3.button(t("Stock"),width="stretch",key="dash_stock"):
        st.session_state["nav_request"]="Stock"; st.rerun()
    if q4.button(t("Analysis"),width="stretch",key="dash_analysis"):
        st.session_state["nav_request"]="Analysis"; st.rerun()

    left,right=st.columns([1.15,1])
    with left:
        with st.container(border=True):
            st.markdown("#### "+t("Today's activity"))
            if daily.empty:
                st.info(t("Empty"))
            else:
                cols=[c for c in ["created_at","movement_type","item_code","item_name","quantity","invoice_reference","username"] if c in daily.columns]
                table(daily.tail(10)[cols].iloc[::-1],height=320)
    with right:
        with st.container(border=True):
            st.markdown("#### "+t("Warehouse status"))
            a,b=st.columns(2)
            a.metric(t("Out of stock"),f"{out_count:,}")
            b.metric(t("Available"),f"{available:,}")
            if not stock.empty:
                watch=stock.sort_values(COL_QTY,ascending=True).head(8)
                table(visible_frame(watch),height=245)
            else:
                st.info(t("No stock"))

    with st.container(border=True):
        st.markdown("#### "+t("Recent invoices"))
        posted=store.recent_invoices(token,8)
        if posted:
            frame=pd.DataFrame(posted)
            frame["total_quantity"]=pd.to_numeric(frame["total_quantity"],errors="coerce").fillna(0).map(lambda x:f"{x:.1f}")
            frame["posted_at"]=frame["posted_at"].map(lambda x:aware(x).astimezone(store.tz).strftime("%Y-%m-%d %H:%M"))
            shown=frame[["invoice_reference","customer_name","driver","movement_type","total_quantity","posted_at"]].rename(columns={
                "invoice_reference":t("Invoice number"),"customer_name":t("Customer name"),"driver":t("Driver"),
                "movement_type":t("Movement type"),"total_quantity":t("Total quantity"),"posted_at":t("Date")})
            table(shown,height=270)
        else:
            st.info(t("No posted invoices"))


def stock_page(store,token,state,stock):
    section("Stock")
    if stock.empty:
        st.info(t("No stock"));return
    with st.container(border=True):
        a,b=st.columns([3,1])
        search=a.text_input(t("Search"),key="stock_search")
        category=b.selectbox(t("Stock"),["All","Available","Out of stock"],format_func=t,label_visibility="collapsed")
        shown=stock
        if search:
            mask=stock[COL_CODE].astype(str).str.contains(search,case=False,regex=False,na=False)|stock[COL_NAME].astype(str).str.contains(search,case=False,regex=False,na=False)
            shown=shown[mask]
        if category=="Available":shown=shown[shown[COL_QTY]>0]
        if category=="Out of stock":shown=shown[shown[COL_QTY]<=0]
        table(visible_frame(shown),height=470)
        st.caption(f"{len(shown):,} / {len(stock):,}")
        export_button("GoldenPalace_Stock",{"Stock":visible_frame(shown)})


def invoices_page(store,token,state,stock):
    section("Invoices","OCR hint")
    ok,_,detail=free_ocr_status()
    code_master_ready = (not stock.empty and stock[COL_CODE].fillna("").astype(str).str.strip().ne("").all())
    with st.container(border=True,key="invoice_workspace"):
        preview,tools=st.columns([1.0,1.25])
        with tools:
            st.markdown("#### "+t("New invoice"))
            mode=st.radio(t("Invoice entry"),["AUTO","MANUAL"],horizontal=True,
                format_func=lambda x:t("Automatic" if x=="AUTO" else "Manual"),key="invoice_entry_mode")
            uploaded=None
            if mode=="AUTO":
                uploaded=st.file_uploader(t("Invoice image"),type=["png","jpg","jpeg"],key="invoice_upload")
                camera_enabled=st.toggle(t("Camera"),key="camera_enabled")
                if camera_enabled:
                    capture=st.camera_input(t("Invoice image"),key="camera_capture")
                    if capture:uploaded=capture
                read=st.button(t("Read invoice"),type="primary",disabled=not (uploaded and ok and code_master_ready),width="stretch")
                if not ok:st.info("OCR is unavailable on this host. Manual invoice entry remains available.")
                if not code_master_ready:st.warning(t("Warehouse code master required"))
            else:
                read=False
                if st.button(t("Start manual invoice"),type="primary",width="stretch",key="start_manual_invoice"):
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
                            result=extract_invoice_data(uploaded,stock)
                            if result.get("movement_type") not in ("IN","OUT"): result["movement_type"]=""
                            result.setdefault("customer_name",""); result.setdefault("driver","")
                            store.save_draft(token,draft_id,result,pending[draft_id]["version"])
                            success(message="Saved")
                        except Exception as error:
                            # A failed scan must not leave a blank technical "draft"
                            # behind. The operator can simply correct the photo and retry.
                            try:store.discard_draft(token,draft_id)
                            except Exception:pass
                            st.session_state.pop("selected_draft_id",None)
                            if isinstance(error,(RuntimeError,ValueError)):st.error(str(error)[:1000])
                            else:show_error(error)
        with preview:
            st.markdown("#### "+t("Invoice preview"))
            if uploaded:
                st.image(uploaded.getvalue(),width="stretch")
            else:
                st.markdown('<div class="gp-invoice-empty">'+t("Invoice preview hint")+'</div>',unsafe_allow_html=True)

    # Pending invoice_drafts remain an internal safety/recovery layer. Do not expose
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
        # Keep the operator flow simple: Auto / Manual are the only entry choices.
        # If multiple unfinished drafts exist from older versions, continue the
        # currently selected one (or newest one) without exposing a technical draft picker.
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


def movements_page(store,token,state,stock):
    section("Movements")
    if stock.empty:
        st.info(t("No stock"));return
    request=nonce("manual")
    # Direction is outside the form so delivery-note controls update immediately.
    kind=st.segmented_control(t("Movement type"),["IN","OUT"],default="OUT",format_func=t,key="manual_kind") or "OUT"
    with st.form("manual_"+request):
        a,b=st.columns([3,1])
        indexed=stock.set_index(COL_KEY)
        item=a.selectbox(t("Item"),indexed.index.tolist(),format_func=lambda k:f"{indexed.at[k,COL_CODE]} | {indexed.at[k,COL_NAME]}")
        qty=b.number_input(t("Quantity"),min_value=0.0,step=1.0,format="%.1f")
        st.markdown('<div class="gp-form-gap"></div>',unsafe_allow_html=True)
        a,b=st.columns(2)
        reference=a.text_input(t("Reference optional"))
        reason=b.text_input(t("Reason"))
        delivered=st.checkbox(t("Delivery confirmed")) if kind=="OUT" else False
        st.markdown('<div class="gp-form-gap"></div>',unsafe_allow_html=True)
        password=st.text_input(t("Approval password"),type="password",key="password_manual_"+request)
        if st.form_submit_button(t("Post movement"),type="primary",width="stretch"):
            try:
                store.post(token,password,[dict(item_key=item,movement_type=kind,quantity=qty)],request,
                           reference=reference,reason=reason,delivery_note=delivered)
                success("manual")
            except Exception as error:show_error(error)
    section("Movement log")
    day=st.date_input(t("Date"),value=store.today(),key="manual_log_day")
    ledger=store.ledger(token,day)
    if not ledger.empty:
        table(ledger[["created_at","username","source","movement_type","item_code","item_name","quantity","quantity_before","quantity_after","invoice_reference","without_invoice"]])
        export_button("GoldenPalace_Movements",{"Movements":ledger})
    else:st.info(t("Empty"))


def analysis_page(store,token,state,stock):
    section("Analysis")
    data=analysis_now(store,token,state)
    if data.empty:
        st.info(t("Empty")+". "+t("Upload history"));return
    priority="\u0623\u0648\u0644\u0648\u064a\u0629 \u0627\u0644\u0637\u0644\u0628"
    reorder="\u062d\u0627\u0644\u0629 \u0627\u0644\u0637\u0644\u0628"
    speed="\u0633\u0631\u0639\u0629 \u0627\u0644\u062d\u0631\u0643\u0629"
    clearance="\u0627\u0642\u062a\u0631\u0627\u062d \u0627\u0644\u062a\u0635\u0631\u064a\u0641"
    critical=data[data[priority]=="\u062d\u0631\u062c\u0629"]
    reorders=data[data[reorder]=="\u0625\u0639\u0627\u062f\u0629 \u0637\u0644\u0628"]
    fast=data[data[speed]=="\u0633\u0631\u064a\u0639\u0629"]
    slow=data[data[clearance]=="\u0645\u0631\u0634\u062d \u0644\u0644\u062a\u0635\u0631\u064a\u0641"]
    st.markdown(kpis_html([("Critical",len(critical),"Items"),("Reorder",len(reorders),"Items"),("Fast",len(fast),"Items"),("Clearance",len(slow),"Items")]),unsafe_allow_html=True)
    selected=st.segmented_control(t("Analysis"),["Reorder","Fast","Clearance","All"],default="Reorder",format_func=t,key="analysis_filter") or "Reorder"
    selected_data={"Reorder":reorders,"Fast":fast,"Clearance":slow,"All":data}[selected]
    columns=[COL_CODE,COL_NAME,COL_QTY,priority,"تغطية المستودع بالأيام",
             "\u0643\u0645\u064a\u0629 \u0627\u0644\u0637\u0644\u0628 \u0627\u0644\u0645\u0642\u062a\u0631\u062d\u0629","\u0627\u062a\u062c\u0627\u0647 \u0627\u0644\u0637\u0644\u0628","\u0633\u0628\u0628 \u0627\u0644\u0642\u0631\u0627\u0631"]
    table(selected_data[columns],height=460)
    with st.expander(t("Analysis")):
        table(visible_frame(selected_data))
    st.caption("Analysis retains the report-based demand windows. Recommendations require review; they do not place orders.")
    export_button("GoldenPalace_Analysis",{"Analysis":visible_frame(data),"Reorder":visible_frame(reorders),"Clearance":visible_frame(slow)})


def closing_page(store,token,state,stock,actor):
    section("Closing")
    day=st.date_input(t("Date"),value=store.today(),max_value=store.today(),key="closing_day")
    closure=store.closure(token,day)
    ledger=store.ledger(token,day)
    if closure:st.success(t("Closed")+" / "+closure["username"]+" / "+aware(closure["closed_at"]).astimezone(store.tz).strftime("%Y-%m-%d %H:%M"))
    else:st.info(t("Open"))
    sum_in=float(ledger.loc[ledger["movement_type"]=="IN","quantity"].sum()) if not ledger.empty else 0
    sum_out=float(ledger.loc[ledger["movement_type"]=="OUT","quantity"].sum()) if not ledger.empty else 0
    alerts=int(ledger["without_invoice"].sum()) if not ledger.empty else 0
    st.markdown(kpis_html([("Movements",len(ledger),"Today"),("IN",f"{sum_in:g}","Quantity"),("OUT",f"{sum_out:g}","Quantity"),("Without invoice",alerts,"Today")]),unsafe_allow_html=True)
    table(ledger)
    day_stock=store.day_stock(token,day) if closure else (stock if day==store.today() else pd.DataFrame())
    if not closure and day!=store.today():st.warning(t("Past stock unavailable"))
    analysis=pd.DataFrame(closure["analysis"]) if closure else (analysis_now(store,token,state) if day==store.today() else pd.DataFrame())
    report=day_report_sheets(day,ledger,day_stock,analysis,closure)
    export_button("GoldenPalace_Day_"+day.isoformat(),report)
    if not closure and actor["role"]=="admin" and day==store.today():
        with st.form("close_day"):
            st.warning(t("Close warning"))
            confirm=st.checkbox(t("Confirm closing"))
            password=st.text_input(t("Approval password"),type="password",key="password_close")
            if st.form_submit_button(t("Close day"),type="primary",disabled=stock.empty):
                try:
                    if not confirm:raise AppError("Confirm closing")
                    store.close_day(token,password,day,analysis,state["revision"])
                    success()
                except Exception as error:show_error(error)


def imports_panel(store,token,state,stock):
    with st.expander(t("Upload stock"),expanded=stock.empty):
        uploaded=st.file_uploader(t("Upload stock"),type=["xlsx","xls"],key="stock_report")
        if uploaded:
            try:
                raw=uploaded.getvalue()
                with branded_wait("Reading report"):
                    df=parse_stock_report(raw)
                # The warehouse report is now the master source for both item code and item name.
                table(visible_frame(df.head(12)))
                st.caption(f"{len(df):,} "+t("Items"))
                with st.form("stock_import"):
                    st.warning(t("Baseline warning"))
                    confirmed=st.checkbox(t("Confirm baseline"))
                    password=st.text_input(t("Approval password"),type="password",key="password_stock")
                    if st.form_submit_button(t("Import"),type="primary"):
                        if not confirmed:raise AppError("Confirm baseline")
                        with branded_wait("Importing stock"):
                            store.replace_stock(token,password,df,nonce("baseline"),state["revision"],source_name=uploaded.name)
                        success("baseline")
            except Exception as error:show_error(error)
    with st.expander(t("Upload history")):
        uploaded=st.file_uploader(t("Upload history"),type=["xlsx","xls"],key="history_report")
        if uploaded:
            try:
                raw=uploaded.getvalue()
                with branded_wait("Reading report"):
                    df=parse_history_report(raw)
                table(df.head(12));st.caption(f"{len(df):,} "+t("Movements"))
                st.info(t("History hint"))
                now=utcnow().astimezone(store.tz)
                with st.form("history_import"):
                    a,b=st.columns(2)
                    day=a.date_input(t("History cutoff"),value=now.date(),max_value=now.date())
                    clock=b.time_input(t("Time"),value=now.time().replace(second=0,microsecond=0),step=60)
                    password=st.text_input(t("Approval password"),type="password",key="password_history")
                    if st.form_submit_button(t("Import"),type="primary"):
                        as_of=datetime.combine(day,clock,tzinfo=store.tz)
                        with branded_wait("Importing history"):
                            store.import_history(token,password,df,hashlib.sha256(raw).hexdigest(),as_of,nonce("history"))
                        success("history")
            except Exception as error:show_error(error)


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
        with st.form("delete_stock_report_form"):
            st.caption(t("Warehouse report delete hint"))
            password=st.text_input(t("Approval password"),type="password",key="password_delete_stock")
            if st.form_submit_button(t("Delete warehouse report"),type="primary"):
                try:store.delete_stock_report(token,password,selected);success(message="Deleted")
                except Exception as error:show_error(error)
    else:st.info(t("No warehouse reports"))

    st.divider()
    st.markdown("#### "+t("Delete movement history report"))
    history_report=catalog.get("history_report")
    if history_report:
        details=f"{history_report['row_count']:,} {t('Rows')}"
        if history_report.get("as_of"):details += " | "+t("History cutoff")+": "+_local_stamp(store,history_report["as_of"])
        st.caption(details)
        with st.form("delete_history_report_form"):
            st.caption(t("Movement history delete hint"))
            confirmed=st.checkbox(t("Confirm delete"),key="delete_history_report_confirm")
            password=st.text_input(t("Approval password"),type="password",key="password_delete_history")
            if st.form_submit_button(t("Delete movement history report"),type="primary",disabled=not confirmed):
                try:store.delete_movement_history(token,password);success(message="Deleted")
                except Exception as error:show_error(error)
    else:st.info(t("No movement history report"))


def settings_page(store,token,state,stock,actor):
    section("Settings")
    with st.container(border=True):
        section("Cloud storage","Cloud hint")
        st.caption("Supabase PostgreSQL | "+state["timezone"]+" | revision "+str(state["revision"]))
        st.caption("Independent scheduled backups must be enabled separately using the included workflow. Cloud saving is not itself an off-site backup.")
    if actor["role"]=="admin":
        section("Import data")
        imports_panel(store,token,state,stock)
        st.divider()
        with st.expander(t("Delete data")):
            deletion_panel(store,token)
        st.divider()
        with st.expander(t("Reorder settings")):
            settings=state["settings"]
            with st.form("settings_form"):
                a,b,c=st.columns(3)
                lead=a.number_input(t("Lead days"),min_value=1,max_value=730,value=int(settings["lead_days"]))
                safety=b.number_input(t("Safety days"),min_value=0,max_value=365,value=int(settings["safety_days"]))
                slow=c.number_input(t("Slow days"),min_value=30,max_value=730,value=int(settings["slow_days"]))
                st.divider()
                st.markdown('<div class="gp-form-gap"></div>',unsafe_allow_html=True)
                a,b=st.columns(2)
                demand=a.number_input(t("Demand days"),min_value=7,max_value=730,value=int(settings["demand_window_days"]))
                review=b.number_input(t("Review days"),min_value=1,max_value=365,value=int(settings["review_days"]))
                st.divider()
                st.markdown('<div class="gp-form-gap"></div>',unsafe_allow_html=True)
                prefixes=st.text_input(t("Purchase prefixes"),value=", ".join(settings["purchase_prefixes"]))
                st.divider()
                password=st.text_input(t("Approval password"),type="password",key="password_settings")
                if st.form_submit_button(t("Save"),type="primary"):
                    try:
                        store.save_settings(token,password,dict(lead_days=lead,safety_days=safety,slow_days=slow,demand_window_days=demand,review_days=review,
                            purchase_prefixes=[p.strip() for p in prefixes.replace("\u060c",",").split(",") if p.strip()]))
                        success()
                    except Exception as error:show_error(error)
        with st.expander(t("Users")):
            users=store.list_users(token);table(pd.DataFrame(users))
            with st.form("new_user",clear_on_submit=True):
                section("New user")
                a,b=st.columns(2)
                username=a.text_input(t("Username"),key="new_username")
                display=b.text_input(t("Display name"),key="new_display")
                role=st.selectbox(t("Role"),["store","admin"],format_func=t,key="new_role")
                newpass=st.text_input(t("New password"),type="password",key="password_newuser")
                password=st.text_input(t("Approval password"),type="password",key="password_useradmin")
                if st.form_submit_button(t("Save"),type="primary"):
                    try:store.create_user(token,password,username,newpass,role,display);success()
                    except Exception as error:show_error(error)
            other_users=[r["username"] for r in users if r["username"]!=actor["username"]]
            if other_users:
                with st.form("user_status"):
                    username=st.selectbox(t("Username"),other_users,key="status_username")
                    active=st.checkbox(t("Active"),value=True)
                    password=st.text_input(t("Approval password"),type="password",key="password_status")
                    if st.form_submit_button(t("Save")):
                        try:store.set_user_active(token,password,username,active);success()
                        except Exception as error:show_error(error)
        with st.expander(t("Snapshot")):
            st.caption("This export includes business data and password hashes, not login sessions. Keep it private. The scheduled backup uses encryption.")
            if st.button(t("Prepare export"),key="snapshot_export"):
                snapshot=store.export_snapshot(token)
                data=gzip.compress(json.dumps(snapshot,ensure_ascii=False,allow_nan=False).encode(),compresslevel=6)
                st.download_button(t("Download"),data,file_name="GoldenPalace_"+store.today().isoformat()+".json.gz",mime="application/gzip",key="snapshot_download")
        with st.expander(t("Audit")):
            if st.button(t("Refresh"),key="audit_load"):
                table(store.audit(token))
    with st.expander(t("Change password")):
        with st.form("change_password",clear_on_submit=True):
            old=st.text_input(t("Password"),type="password",key="password_old")
            new=st.text_input(t("New password"),type="password",key="password_new")
            confirm=st.text_input(t("Confirm password"),type="password",key="password_confirm")
            if st.form_submit_button(t("Save"),type="primary"):
                try:
                    if new!=confirm:raise AppError("Passwords do not match")
                    store.change_password(token,old,new);success()
                except Exception as error:show_error(error)


def _language_picker(key):
    selected=st.segmented_control("Language / اللغة",["ar","en"],
        default=st.session_state.get("ui_language","ar"),
        format_func=lambda x:"العربية" if x=="ar" else "English",
        key=key,label_visibility="collapsed") or st.session_state.get("ui_language","ar")
    if selected!=st.session_state.get("ui_language","ar"):
        st.session_state["ui_language"]=selected
        st.rerun()


def sidebar_navigation(store,token,actor,stamp):
    nav=["Dashboard","Stock","Invoices","Movements","Analysis","Closing","Settings"]
    # Streamlit updates sidebar_nav before each rerun when the user clicks the radio.
    # Never overwrite that click from the older page value. Programmatic navigation
    # uses nav_request and is consumed here before the radio widget is created.
    requested=st.session_state.pop("nav_request",None)
    desired=requested if requested in nav else st.session_state.get("page","Dashboard")
    if desired not in nav:desired="Dashboard"
    if "sidebar_nav" not in st.session_state or requested in nav:
        st.session_state["sidebar_nav"]=desired
    icons={"Dashboard":"⌂","Stock":"▦","Invoices":"▤","Movements":"⇄","Analysis":"◫","Closing":"✓","Settings":"⚙"}
    with st.sidebar:
        st.image(ROOT/"assets/golden_palace.jpg",width=220)
        st.markdown('<div class="gp-sidebar-title">'+t("Inventory")+'</div>',unsafe_allow_html=True)
        st.caption(t("Warehouse workspace"))
        page=st.radio(t("Navigation"),nav,key="sidebar_nav",label_visibility="collapsed",
            format_func=lambda value:f"{icons[value]}  {t(value)}")
        if page!=st.session_state.get("page"):
            st.session_state["page"]=page
        st.divider()
        st.markdown(status_html(actor,stamp),unsafe_allow_html=True)
        _language_picker("sidebar_language")
        if st.button(t("Refresh"),width="stretch",key="sidebar_refresh"):
            get_shell.clear();get_analysis.clear();st.rerun()
        if st.button(t("Sign out"),width="stretch",key="sidebar_signout"):
            try:store.logout(token)
            finally:
                st.session_state.clear();st.rerun()
    return page


def main():
    if "ui_language" not in st.session_state:
        st.session_state["ui_language"]="ar"
    set_language(st.session_state["ui_language"])
    st.markdown(language_marker(),unsafe_allow_html=True)

    if st.session_state.pop("wipe_passwords",False):
        for key in list(st.session_state):
            if key.startswith("password_") or key=="login_password":st.session_state.pop(key,None)

    try:
        config=dict(st.secrets.get("database",{}))
        auth=dict(st.secrets.get("auth",{}))
        app_config=dict(st.secrets.get("app",{}))
        if not config:raise AppError("Complete the database settings in Streamlit Secrets")
        store=get_store(json.dumps(config,sort_keys=True))
        store.initialize(auth.get("bootstrap_username","admin"),auth.get("bootstrap_password",""),app_config.get("timezone","Asia/Damascus"))
    except Exception as error:
        st.markdown(brand_html(),unsafe_allow_html=True)
        if isinstance(error,AppError):st.warning(t(str(error)))
        else:show_error(error)
        st.info("Setup: run sql/setup.sql in Supabase, then copy secrets.example.toml into Streamlit Secrets and fill your own database credentials. No local fallback is enabled.")
        st.code("database.host / database.user / database.password / database.dbname\nauth.bootstrap_username / auth.bootstrap_password",language="text")
        return

    token=st.session_state.get("token")
    if not token:
        with st.sidebar:
            st.markdown("### Language / اللغة")
            _language_picker("login_language")
        st.markdown(brand_html(),unsafe_allow_html=True)
        with st.container(key="login"):
            section("Sign in")
            with st.form("login"):
                username=st.text_input(t("Username"),key="login_username")
                password=st.text_input(t("Password"),type="password",key="login_password")
                if st.form_submit_button(t("Sign in"),type="primary",width="stretch"):
                    try:
                        st.session_state["token"]=store.login(username,password,int(auth.get("session_hours",12)))
                        st.session_state["wipe_passwords"]=True
                        st.rerun()
                    except Exception as error:show_error(error)
            st.caption(t("Cloud hint"))
        return

    try:
        database_id=str(store.engine.url.render_as_string(hide_password=True))
        token_hash=hashlib.sha256(token.encode()).hexdigest()[:24]
        with branded_wait("Loading data"):
            actor,state,stock,daily=get_shell(database_id,token_hash,store,token)
    except AppError as error:
        st.session_state.pop("token",None);st.error(t(str(error)))
        if st.button(t("Sign in")):st.rerun()
        return
    except Exception as error:
        show_error(error)
        if st.button(t("Refresh")):st.rerun()
        return

    stamp=aware(state["updated_at"]).astimezone(store.tz).strftime("%Y-%m-%d %H:%M:%S")
    page=sidebar_navigation(store,token,actor,stamp)

    flash=st.session_state.pop("flash",None)
    if flash:st.success(flash)

    try:
        if page=="Dashboard":dashboard_page(store,token,state,stock,daily,actor)
        elif page=="Stock":stock_page(store,token,state,stock)
        elif page=="Invoices":invoices_page(store,token,state,stock)
        elif page=="Movements":movements_page(store,token,state,stock)
        elif page=="Analysis":analysis_page(store,token,state,stock)
        elif page=="Closing":closing_page(store,token,state,stock,actor)
        elif page=="Settings":settings_page(store,token,state,stock,actor)
    except Exception as error:show_error(error)
    st.markdown('<div class="gp-foot">GOLDEN PALACE / '+BUILD+'</div>',unsafe_allow_html=True)


if __name__=="__main__":
    main()
