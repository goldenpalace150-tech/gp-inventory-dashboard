from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

p=ROOT/'gp_store.py'
s=p.read_text(encoding='utf-8')
old='''            baselines=self.tables["baseline_snapshots"]
            baseline_rows=c.execute(select(baselines).order_by(baselines.c.created_at.desc()).limit(30)).mappings().all()

        invoices=[]; movements=[]
'''
new='''            baselines=self.tables["baseline_snapshots"]
            baseline_rows=c.execute(select(baselines).order_by(baselines.c.created_at.desc()).limit(30)).mappings().all()
            state_row=c.execute(select(self.tables["app_state"]).where(self.tables["app_state"].c.id==1)).mappings().one()
            history_count=c.execute(select(func.count()).select_from(self.tables["imported_movement_history"])).scalar_one()

        invoices=[]; movements=[]
'''
if new not in s:
    if old not in s: raise RuntimeError('catalog query marker not found')
    s=s.replace(old,new,1)
old='''        return {"invoices":invoices,"movements":movements,"stock_reports":reports}

    def _delete_posted_operation_tx(self,c,actor,operation_id,expected_source):
'''
new='''        history_report=None
        if history_count or state_row.get("history_hash"):
            history_report={"row_count":int(history_count),"as_of":state_row.get("history_as_of")}
        return {"invoices":invoices,"movements":movements,"stock_reports":reports,"history_report":history_report}

    def _delete_posted_operation_tx(self,c,actor,operation_id,expected_source):
'''
if new not in s:
    if old not in s: raise RuntimeError('catalog return marker not found')
    s=s.replace(old,new,1)
old='''    def delete_stock_report(self,token,password,operation_id):
'''
new='''    def delete_movement_history(self,token,password):
        """Delete imported movement history without changing current stock."""
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token,password,admin=True)
            history=self.tables["imported_movement_history"]
            count=c.execute(select(func.count()).select_from(history)).scalar_one()
            state=self.tables["app_state"]
            current=c.execute(select(state.c.history_hash,state.c.history_as_of).where(state.c.id==1).with_for_update()).mappings().one()
            if not count and not current["history_hash"]:raise AppError("Record not found")
            c.execute(delete(history))
            c.execute(update(state).where(state.c.id==1).values(history_as_of=None,history_hash=None))
            self._audit(c,actor["username"],"DELETE_MOVEMENT_HISTORY",{"rows_removed":int(count)})
            self._touch(c)
            return int(count)

    def delete_stock_report(self,token,password,operation_id):
'''
if new not in s:
    if old not in s: raise RuntimeError('delete stock marker not found')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

p=ROOT/'inventory_tracker.py'
s=p.read_text(encoding='utf-8')
old='''    else:st.info(t("No warehouse reports"))


def settings_page(store,token,state,stock,actor):
'''
new='''    else:st.info(t("No warehouse reports"))

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
'''
if new not in s:
    if old not in s: raise RuntimeError('deletion UI marker not found')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

p=ROOT/'gp_ui.py'
s=p.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.3"' not in s:
    if 'BUILD = "GP-CLOUD-v16.2"' not in s: raise RuntimeError('build marker not found')
    s=s.replace('BUILD = "GP-CLOUD-v16.2"','BUILD = "GP-CLOUD-v16.3"',1)
labels='''\n\n# ---- v16.3 movement-history cleanup ----\nAR.update({\n    "Delete movement history report": "حذف ملف حركة المادة",\n    "Movement history delete hint": "يحذف ملف حركة المادة المستورد وبيانات التحليل التاريخية فقط، ولا يغيّر رصيد المستودع الحالي.",\n    "No movement history report": "لا يوجد ملف حركة مادة مستورد.",\n    "Rows": "سطر",\n})\n'''
if '"Delete movement history report": "حذف ملف حركة المادة"' not in s:
    marker='\ndef set_language('
    pos=s.find(marker)
    if pos<0: raise RuntimeError('language marker not found')
    s=s[:pos]+labels+s[pos:]
p.write_text(s,encoding='utf-8')

print('v16.3 movement history deletion applied')
