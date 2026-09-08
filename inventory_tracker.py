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
                   page_icon=Image.open(ROOT/"assets/favicon.png"),layout="wide",initial_sidebar_state="collapsed")
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
                content=uploaded.getvalue()
                image_hash=hashlib.sha256(content).hexdigest()
                # Persist the draft identity before starting a potentially failing model.
                draft_id=store.create_draft(token,source_name=uploaded.name,image_hash=image_hash)
                st.session_state["selected_draft_id"]=draft_id
                pending={d["draft_id"]:d for d in store.drafts(token)}
                if draft_id not in pending:
                    st.warning(t("This invoice or image was already posted"))
                elif pending[draft_id]["payload"].get("items"):
                    st.info("This image already has a saved draft. Review it below; OCR was not repeated.")
                else:
                    with branded_wait("Reading"):
                        try:
                            result=extract_invoice_data(uploaded,stock)
                            result["movement_type"]=""  # the numeric reader cannot determine direction
                            store.save_draft(token,draft_id,result,pending[draft_id]["version"])
                            success(message="Saved")
                        except Exception as error:
                            # Worker messages are bounded; the worker has no database credentials in its logs.
                            if isinstance(error,(RuntimeError,ValueError)):
                                st.error(str(error)[:1000])
                            else:show_error(error)
        with right:
            if uploaded:
                st.image(uploaded.getvalue(),width="stretch")
            else:
                st.markdown(section_html("Review","Draft hint"),unsafe_allow_html=True)
    section("Drafts")
    drafts=store.drafts(token)
    if not drafts:
        st.info(t("No drafts"));return
    choices={d["draft_id"]:d for d in drafts}
    selected=st.session_state.get("selected_draft_id")
    if selected not in choices:selected=drafts[0]["draft_id"]
    selected=st.selectbox(t("Drafts"),list(choices),index=list(choices).index(selected),
        format_func=lambda k: (choices[k]["payload"].get("invoice_number") or choices[k]["source_name"] or k[:8])+" / "+choices[k]["username"],
        key="draft_selector")
    st.session_state["selected_draft_id"]=selected
    draft=choices[selected];payload=draft["payload"]
    # Versioned widget identity prevents stale edits from overwriting a newer revision.
    suffix=selected+"_"+str(draft["version"])
    for message in payload.get("warnings",[])[:6]:st.warning(str(message))
    st.caption(t("Draft hint"))
    rows=payload.get("items") or []
    try:
        rows, ignored_saved = canonicalize_invoice_rows(rows, stock, drop_unknown=True)
    except AppError:
        rows, ignored_saved = [], []
    if ignored_saved:
        st.warning(t("Ignored non-item numbers")+": "+", ".join(ignored_saved[:8]))
    rows=rows or [{"item_code":"","item_name":"","quantity":None}]
    frame=pd.DataFrame(rows)[["item_code","item_name","quantity"]]
    frame["item_code"]=frame["item_code"].fillna("").astype(str)
    frame["item_name"]=frame["item_name"].fillna("").astype(str)
    frame["quantity"]=pd.to_numeric(frame["quantity"],errors="coerce")
    with st.form("review_"+suffix):
        a,b=st.columns([1.3,1])
        reference=a.text_input(t("Reference"),value=str(payload.get("invoice_number", "")),key="reference_"+suffix)
        kinds=["","OUT","IN"]
        kind=b.selectbox(t("Movement type"),kinds,index=kinds.index(payload.get("movement_type","")) if payload.get("movement_type","") in kinds else 0,
                         format_func=lambda k:t(k or "Select"),key="kind_"+suffix)
        edited=st.data_editor(frame,hide_index=True,num_rows="dynamic",width="stretch",key="lines_"+suffix,disabled=["item_name"],
            column_config={"item_code":st.column_config.TextColumn(COL_CODE),"item_name":st.column_config.TextColumn(COL_NAME),
                           "quantity":st.column_config.NumberColumn(COL_QTY,min_value=0,format="%.4f")})
        review_checked=st.checkbox(t("Confirm review"),key="checked_"+suffix)
        password=st.text_input(t("Approval password"),type="password",key="password_invoice_"+suffix)
        a,b=st.columns(2)
        save=a.form_submit_button(t("Save draft"),width="stretch")
        post=b.form_submit_button(t("Post invoice"),type="primary",width="stretch")
        if save or post:
            try:
                canonical_rows, _ = canonicalize_invoice_rows(edited.to_dict("records"), stock, drop_unknown=False)
                updated=dict(payload)
                updated.update(invoice_number=reference.strip(),movement_type=kind,
                               items=clean_json(canonical_rows))
                if save:
                    store.save_draft(token,selected,updated,draft["version"])
                    success()
                else:
                    if not review_checked:raise AppError("Confirm review")
                    changes=match_invoice_lines(updated["items"],store.stock(token),kind)
                    store.post(token,password,changes,nonce("invoice_"+selected),source="INVOICE",reference=reference,
                        image_hash=draft["image_hash"],reason=t("Invoices"),delivery_note=True,reviewed=updated,draft_id=selected,expected_draft_version=draft["version"])
                    success("invoice_"+selected)
            except Exception as error:show_error(error)
    with st.expander(t("Discard")):
        discard_ok=st.checkbox(t("Discard"),key="discard_check_"+suffix)
        if st.button(t("Discard"),disabled=not discard_ok,key="discard_"+suffix):
            store.discard_draft(token,selected);success()


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
        qty=b.number_input(t("Quantity"),min_value=0.0,step=1.0,format="%.4f")
        a,b=st.columns(2)
        reference=a.text_input(t("Reference optional"))
        reason=b.text_input(t("Reason"))
        delivered=st.checkbox(t("Delivery confirmed")) if kind=="OUT" else False
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
                a,b=st.columns(2)
                demand=a.number_input(t("Demand days"),min_value=7,max_value=730,value=int(settings["demand_window_days"]))
                review=b.number_input(t("Review days"),min_value=1,max_value=365,value=int(settings["review_days"]))
                st.divider()
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


def main():
    if "ui_language" not in st.session_state:
        st.session_state["ui_language"]="ar"
    selected_lang=st.segmented_control("Language / اللغة",["ar","en"],
        default=st.session_state["ui_language"],format_func=lambda x:"العربية" if x=="ar" else "English",
        key="language_switch",label_visibility="collapsed") or st.session_state["ui_language"]
    if selected_lang!=st.session_state["ui_language"]:
        st.session_state["ui_language"]=selected_lang
        st.rerun()
    set_language(st.session_state["ui_language"])
    st.markdown(language_marker(),unsafe_allow_html=True)
    st.markdown(brand_html(),unsafe_allow_html=True)
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
        if isinstance(error,AppError):st.warning(t(str(error)))
        else:show_error(error)
        st.info("Setup: run sql/setup.sql in Supabase, then copy secrets.example.toml into Streamlit Secrets and fill your own database credentials. No local fallback is enabled.")
        st.code("database.host / database.user / database.password / database.dbname\nauth.bootstrap_username / auth.bootstrap_password",language="text")
        return
    token=st.session_state.get("token")
    if not token:
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
    a,b,c=st.columns([5,1,1])
    stamp=aware(state["updated_at"]).astimezone(store.tz).strftime("%Y-%m-%d %H:%M:%S")
    a.markdown(status_html(actor,stamp),unsafe_allow_html=True)
    if b.button(t("Refresh"),width="stretch",key="global_refresh"):
        get_shell.clear(); get_analysis.clear(); st.rerun()
    with c.popover(t("Account"),width="stretch"):
        st.write(actor["display_name"]+" / "+t(actor["role"]))
        if st.button(t("Sign out"),width="stretch"):
            try:store.logout(token)
            finally:
                st.session_state.clear()
                st.rerun()
    flash=st.session_state.pop("flash",None)
    if flash:st.success(flash)
    nav=["Stock","Invoices","Movements","Analysis","Closing","Settings"]
    with st.container(key="navigation"):
        page=st.segmented_control(t("Inventory"),nav,default="Stock",format_func=t,key="page",label_visibility="collapsed",width="stretch") or "Stock"
    if page not in ("Analysis",):
        alerts=int(daily["without_invoice"].sum()) if not daily.empty else 0
        st.markdown(kpis_html([("Items",f"{len(stock):,}","Stock"),("Available",f"{int((stock[COL_QTY]>0).sum()):,}","Items"),
                               ("Movements",len(daily),"Today"),("Without invoice",alerts,"Today")]),unsafe_allow_html=True)
    try:
        if page=="Stock":stock_page(store,token,state,stock)
        elif page=="Invoices":invoices_page(store,token,state,stock)
        elif page=="Movements":movements_page(store,token,state,stock)
        elif page=="Analysis":analysis_page(store,token,state,stock)
        elif page=="Closing":closing_page(store,token,state,stock,actor)
        elif page=="Settings":settings_page(store,token,state,stock,actor)
    except Exception as error:show_error(error)
    st.markdown('<div class="gp-foot">GOLDEN PALACE / '+BUILD+'</div>',unsafe_allow_html=True)


if __name__=="__main__":
    main()
