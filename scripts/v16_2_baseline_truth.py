from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
store_path=ROOT/'gp_store.py'
text=store_path.read_text(encoding='utf-8')

old='''    def _audit(self, conn, username, action, details=None):
        conn.execute(insert(self.tables["audit_log"]).values(event_id=str(uuid.uuid4()),
            created_at=utcnow(), username=username, action=action, details=clean_json(details or {})))

    def initialize(self, username="admin", password="", timezone_name="Asia/Damascus"):
'''
new='''    def _audit(self, conn, username, action, details=None):
        conn.execute(insert(self.tables["audit_log"]).values(event_id=str(uuid.uuid4()),
            created_at=utcnow(), username=username, action=action, details=clean_json(details or {})))

    def _repair_orphan_stock_without_baseline(self, conn):
        baselines=self.tables["baseline_snapshots"]
        stock=self.tables["stock_state"]
        if conn.execute(select(baselines.c.operation_id).limit(1)).first():
            return False
        stale_count=conn.execute(select(func.count()).select_from(stock)).scalar_one()
        if not stale_count:
            return False
        conn.execute(delete(stock))
        self._audit(conn,"system","REPAIR_ORPHAN_STOCK_WITHOUT_BASELINE",{"rows_removed":int(stale_count)})
        self._touch(conn)
        return True

    def initialize(self, username="admin", password="", timezone_name="Asia/Damascus"):
'''
if new not in text:
    if old not in text: raise RuntimeError('audit marker not found')
    text=text.replace(old,new,1)

old='''                self.tz = ZoneInfo(timezone_name)
                self._audit(c, username, "ADMIN_BOOTSTRAP")

    def login(self, username, password, session_hours=12):
'''
new='''                self.tz = ZoneInfo(timezone_name)
                self._audit(c, username, "ADMIN_BOOTSTRAP")
            self._repair_orphan_stock_without_baseline(c)

    def login(self, username, password, session_hours=12):
'''
if new not in text:
    if old not in text: raise RuntimeError('initialize marker not found')
    text=text.replace(old,new,1)

old='''    def stock(self, token):
        with self.engine.connect() as c:
            self._actor(c,token)
            rows=c.execute(select(self.tables["stock_state"]).order_by(self.tables["stock_state"].c.item_name)).mappings().all()
            return self.stock_frame(rows)
'''
new='''    def stock(self, token):
        with self.engine.connect() as c:
            self._actor(c,token)
            baselines=self.tables["baseline_snapshots"]
            if not c.execute(select(baselines.c.operation_id).limit(1)).first():
                return self.stock_frame([])
            rows=c.execute(select(self.tables["stock_state"]).order_by(self.tables["stock_state"].c.item_name)).mappings().all()
            return self.stock_frame(rows)
'''
if new not in text:
    if old not in text: raise RuntimeError('stock marker not found')
    text=text.replace(old,new,1)
store_path.write_text(text,encoding='utf-8')

ui_path=ROOT/'gp_ui.py'
ui=ui_path.read_text(encoding='utf-8')
if 'BUILD = "GP-CLOUD-v16.2"' not in ui:
    if 'BUILD = "GP-CLOUD-v16.1"' not in ui: raise RuntimeError('build marker not found')
    ui=ui.replace('BUILD = "GP-CLOUD-v16.1"','BUILD = "GP-CLOUD-v16.2"',1)
ui_path.write_text(ui,encoding='utf-8')

p=ROOT/'tests/test_core_and_ocr.py'
t=p.read_text(encoding='utf-8')
extra='''\n\ndef test_stock_reader_hides_orphan_balance_without_warehouse_report():\n    from sqlalchemy import delete\n    s=Store.for_tests();pw="Test-Password-2026";s.initialize(password=pw);t=s.login("admin",pw)\n    stock=ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:"010716",COL_NAME:"Camera",COL_QTY:10}]))\n    s.replace_stock(t,pw,stock,"base-orphan-read",s.state(t)["revision"],source_name="orphan.xlsx")\n    with s.engine.begin() as c:c.execute(delete(s.tables["baseline_snapshots"]))\n    assert s.stock(t).empty\n\n\ndef test_initialize_repairs_orphan_stock_left_by_old_delete_behavior():\n    from sqlalchemy import delete,select,func\n    s=Store.for_tests();pw="Test-Password-2026";s.initialize(password=pw);t=s.login("admin",pw)\n    stock=ensure_unique_stock_keys(pd.DataFrame([{COL_CODE:"010716",COL_NAME:"Camera",COL_QTY:10}]))\n    s.replace_stock(t,pw,stock,"base-orphan-repair",s.state(t)["revision"],source_name="orphan.xlsx")\n    with s.engine.begin() as c:\n        c.execute(delete(s.tables["baseline_snapshots"]))\n        assert c.execute(select(func.count()).select_from(s.tables["stock_state"])).scalar_one()==1\n    s.initialize(password=pw)\n    with s.engine.connect() as c:\n        assert c.execute(select(func.count()).select_from(s.tables["stock_state"])).scalar_one()==0\n        assert c.execute(select(func.count()).select_from(s.tables["audit_log"]).where(s.tables["audit_log"].c.action=="REPAIR_ORPHAN_STOCK_WITHOUT_BASELINE")).scalar_one()==1\n'''
if 'def test_stock_reader_hides_orphan_balance_without_warehouse_report()' not in t:
    marker='\ndef test_invoice_ui_hides_draft_workflow_and_cleans_failed_scans():'
    pos=t.find(marker)
    if pos<0: raise RuntimeError('test marker not found')
    t=t[:pos]+extra+t[pos:]
p.write_text(t,encoding='utf-8')
print('v16.2 baseline truth repair applied')
