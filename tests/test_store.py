from datetime import timedelta
from decimal import Decimal
import hashlib
import uuid
import pandas as pd
import pytest
from sqlalchemy import select,update,insert,func
from sqlalchemy.dialects import postgresql
from gp_store import Store,AppError,decimal_qty,password_hash,password_matches,utcnow,clean_json
from gp_core import *
from gp_invoice import match_invoice_lines
from gp_backup import encrypt_snapshot,decrypt_snapshot
from cryptography.fernet import Fernet

PASS="Test-Admin-Password-2026"


def sample_stock():
    rows=[{COL_CODE:"010716",COL_NAME:"Camera",COL_QTY:10.0},
          {COL_CODE:"010732",COL_NAME:"Card 128",COL_QTY:20.0},
          {COL_CODE:"010733",COL_NAME:"Card 256",COL_QTY:5.0}]
    return ensure_unique_stock_keys(pd.DataFrame(rows))


@pytest.fixture
def env():
    s=Store.for_tests();s.initialize(password=PASS)
    token=s.login("admin",PASS)
    s.replace_stock(token,PASS,sample_stock(),"baseline",s.state(token)["revision"])
    yield s,token
    s.engine.dispose()


def change(q=1,d="OUT",key="CODE:010716"):
    return [{"item_key":key,"quantity":q,"movement_type":d}]


def qty(s,t):
    stock=s.stock(t).set_index(COL_CODE)
    return stock.at["010716",COL_QTY]


@pytest.mark.parametrize("bad",[None,True,0,-1,"NaN","Infinity",1.12345,10**13,"text"])
def test_invalid_quantities(bad):
    with pytest.raises(AppError):decimal_qty(bad,positive=True)


def test_password_hash_unique():
    a=password_hash(PASS);b=password_hash(PASS)
    assert a!=b and PASS not in a and password_matches(PASS,a)
    assert not password_matches("wrong",a)


def test_simple_passwords_are_allowed_for_users():
    s=Store.for_tests();s.initialize(password="admin-bootstrap")
    t=s.login("admin","admin-bootstrap")
    s.create_user(t,"a","1","store","A")
    assert s.login("a","1")
    s.create_user(t,"user name","","store","Blank Password")
    assert s.login("user name","")


def test_post_atomic_and_reload(env):
    s,t=env
    op=s.post(t,PASS,change(3),"op1",reason="test",delivery_note=True)
    assert qty(s,t)==7
    log=s.ledger(t);assert len(log)==1
    assert float(log.iloc[0]["quantity_before"])==10
    assert float(log.iloc[0]["quantity_after"])==7
    # Simulate a new app/session using the same durable storage.
    second=Store(s.engine,schema=None);other=second.login("admin",PASS)
    assert qty(second,other)==7
    assert op==log.iloc[0]["operation_id"]


def test_idempotent_retry(env):
    s,t=env
    first=s.post(t,PASS,change(3),"same",reason="test",delivery_note=True)
    second=s.post(t,PASS,change(3),"same",reason="test",delivery_note=True)
    assert first==second and qty(s,t)==7 and len(s.ledger(t))==1


def test_reused_key_changed_payload_rejected(env):
    s,t=env;s.post(t,PASS,change(3),"same",reason="test",delivery_note=True)
    with pytest.raises(AppError):s.post(t,PASS,change(4),"same",reason="test",delivery_note=True)
    assert qty(s,t)==7


def test_multi_line_failure_rolls_back_everything(env):
    s,t=env;rev=s.state(t)["revision"]
    changes=change(1)+change(999,"OUT","CODE:010733")
    with pytest.raises(AppError):s.post(t,PASS,changes,"bad",reason="test",delivery_note=True)
    assert qty(s,t)==10 and s.ledger(t).empty and s.state(t)["revision"]==rev


def test_negative_line_not_net_cancelled(env):
    s,t=env
    with pytest.raises(AppError):s.post(t,PASS,change(5)+change(-2),"bad",reason="test",delivery_note=True)
    assert qty(s,t)==10


def test_invalid_movement_type(env):
    s,t=env
    with pytest.raises(AppError):s.post(t,PASS,change(2,"BAD"),"bad",reason="test",delivery_note=True)


def test_wrong_password_no_write(env):
    s,t=env
    with pytest.raises(AppError):s.post(t,"wrong",change(),"bad",reason="test",delivery_note=True)
    assert s.ledger(t).empty


def test_delivery_required(env):
    s,t=env
    with pytest.raises(AppError):s.post(t,PASS,change(),"bad",reason="test")
    s.post(t,PASS,change(2,"IN"),"good",reason="test")
    assert qty(s,t)==12


def test_server_balance_not_stale_client(env):
    s,t=env
    stale=s.stock(t)
    s.post(t,PASS,change(7),"first",reason="test",delivery_note=True)
    assert stale.set_index(COL_CODE).at["010716",COL_QTY]==10
    with pytest.raises(AppError):s.post(t,PASS,change(4),"second",reason="test",delivery_note=True)
    assert qty(s,t)==3


def test_duplicate_invoice_reference(env):
    s,t=env
    s.post(t,PASS,change(1),"a",source="INVOICE",reference="8042",image_hash="a"*64)
    with pytest.raises(AppError):s.post(t,PASS,change(1),"b",source="INVOICE",reference="8042",image_hash="b"*64)
    assert qty(s,t)==9


def test_duplicate_image(env):
    s,t=env
    s.post(t,PASS,change(1),"a",source="INVOICE",reference="8042",image_hash="a"*64)
    with pytest.raises(AppError):s.post(t,PASS,change(1),"b",source="INVOICE",reference="8043",image_hash="a"*64)
    assert qty(s,t)==9


def test_draft_survives_signout(env):
    s,t=env;d=s.create_draft(t,"sample.jpg","b"*64)
    payload={"items":[{"item_code":"010716","item_name":"Camera","quantity":3}],"invoice_number":"8042","movement_type":"OUT"}
    s.save_draft(t,d,payload,1);s.logout(t)
    with pytest.raises(AppError):s.stock(t)
    t2=s.login("admin",PASS)
    assert s.drafts(t2)[0]["payload"]==payload and qty(s,t2)==10


def test_duplicate_upload_reuses_draft(env):
    s,t=env
    a=s.create_draft(t,"test","a"*64);b=s.create_draft(t,"test","a"*64)
    assert a==b and len(s.drafts(t))==1


def test_draft_version_conflict(env):
    s,t=env;d=s.create_draft(t)
    s.save_draft(t,d,{"items":[]},1)
    with pytest.raises(AppError):s.save_draft(t,d,{"items":[]},1)


def test_stale_draft_cannot_post(env):
    s,t=env;d=s.create_draft(t)
    s.save_draft(t,d,{"items":[]},1)
    with pytest.raises(AppError):s.post(t,PASS,change(),"draft",source="INVOICE",reference="d",draft_id=d,expected_draft_version=1)
    assert qty(s,t)==10


def test_draft_post_atomic(env):
    s,t=env;d=s.create_draft(t)
    s.post(t,PASS,change(3),"draft",source="INVOICE",reference="d",draft_id=d,expected_draft_version=1)
    assert len(s.drafts(t))==0 and qty(s,t)==7


def test_staff_cannot_replace_stock_or_create_user(env):
    s,t=env;s.create_user(t,"store",PASS,"store")
    staff=s.login("store",PASS)
    with pytest.raises(AppError):s.replace_stock(staff,PASS,sample_stock(),"bad",s.state(t)["revision"])
    with pytest.raises(AppError):s.create_user(staff,PASS,"hacker",PASS,"admin")
    with pytest.raises(AppError):s.list_users(staff)
    with pytest.raises(AppError):s.export_snapshot(staff)


def test_drafts_are_owner_scoped(env):
    s,t=env;s.create_user(t,"store",PASS,"store")
    staff=s.login("store",PASS);d=s.create_draft(t)
    assert s.drafts(staff)==[]
    with pytest.raises(AppError):s.save_draft(staff,d,{"items":[]},1)


def test_deactivation_revokes_sessions(env):
    s,t=env;s.create_user(t,"store",PASS,"store");staff=s.login("store",PASS)
    s.set_user_active(t,PASS,"store",False)
    with pytest.raises(AppError):s.actor(staff)


def test_cannot_disable_self(env):
    s,t=env
    with pytest.raises(AppError):s.set_user_active(t,PASS,"admin",False)


def test_password_change_revokes_other_sessions(env):
    s,t=env;other=s.login("admin",PASS)
    s.change_password(t,PASS,PASS+"-new")
    with pytest.raises(AppError):s.actor(other)
    assert s.actor(t)["username"]=="admin"
    assert s.login("admin",PASS+"-new")


def test_expired_session(env):
    s,t=env
    with s.engine.begin() as c:c.execute(update(s.tables["auth_sessions"]).values(expires_at=utcnow()-timedelta(seconds=1)))
    with pytest.raises(AppError):s.stock(t)


def test_login_rate_limit(env):
    s,t=env
    for _ in range(5):
        with pytest.raises(AppError):s.login("admin","wrong")
    with pytest.raises(AppError):s.login("admin",PASS)


def test_closure_snapshot_and_write_lock(env):
    s,t=env;s.post(t,PASS,change(2),"a",reason="test",delivery_note=True)
    day=s.today();s.close_day(t,PASS,day,pd.DataFrame(),s.state(t)["revision"])
    assert float(s.closure(t,day)["total_out"])==2
    assert s.day_stock(t,day).set_index(COL_CODE).at["010716",COL_QTY]==8
    with pytest.raises(AppError):s.post(t,PASS,change(1),"b",reason="test",delivery_note=True)
    with pytest.raises(AppError):s.close_day(t,PASS,day,pd.DataFrame(),s.state(t)["revision"])


def test_cannot_close_past_day(env):
    s,t=env
    with pytest.raises(AppError):s.close_day(t,PASS,s.today()-timedelta(days=1),pd.DataFrame(),s.state(t)["revision"])


def test_stale_revision_cannot_close(env):
    s,t=env;old=s.state(t)["revision"];s.create_draft(t)
    with pytest.raises(AppError):s.close_day(t,PASS,s.today(),pd.DataFrame(),old)


def test_baseline_after_post_refused(env):
    s,t=env;s.post(t,PASS,change(1),"a",reason="test",delivery_note=True)
    with pytest.raises(AppError):s.replace_stock(t,PASS,sample_stock(),"b",s.state(t)["revision"])


def test_bad_snapshot_restore_refused(env):
    s,t=env;doc=s.export_snapshot(t);doc["tables"].pop("posted_invoices")
    with pytest.raises(AppError):Store.for_tests().restore_empty(doc)


def test_encrypt_restore_roundtrip(env):
    s,t=env;s.post(t,PASS,change(3),"a",source="INVOICE",reference="8042",image_hash="a"*64)
    s.close_day(t,PASS,s.today(),pd.DataFrame(),s.state(t)["revision"])
    doc=s.export_snapshot(t)
    assert "auth_sessions" not in doc["tables"]
    key=Fernet.generate_key();blob=encrypt_snapshot(doc,key)
    assert b"8042" not in blob and b"password_hash" not in blob
    recovered=decrypt_snapshot(blob,key);fresh=Store.for_tests();fresh.restore_empty(recovered)
    t2=fresh.login("admin",PASS)
    assert qty(fresh,t2)==7 and len(fresh.ledger(t2))==1
    assert fresh.closure(t2,fresh.today())
    with pytest.raises(AppError):fresh.restore_empty(recovered)


def test_wrong_key_and_tampering(env):
    s,t=env;key=Fernet.generate_key();blob=encrypt_snapshot(s.export_snapshot(t),key)
    with pytest.raises(AppError):decrypt_snapshot(blob,Fernet.generate_key())
    with pytest.raises(AppError):decrypt_snapshot(blob[:-4]+b"xxxx",key)


def test_exact_code_matching_leading_zero(env):
    s,t=env
    result=match_invoice_lines([dict(item_code="010716",item_name="",quantity=3)],s.stock(t),"OUT")
    assert result[0]["item_key"]=="CODE:010716"
    with pytest.raises(AppError):match_invoice_lines([dict(item_code="10716",item_name="Camera",quantity=3)],s.stock(t),"OUT")


def test_ambiguous_name_refused(env):
    s,t=env;stock=s.stock(t);stock.loc[1,COL_NAME]="Camera";stock.loc[1,COL_MATCH]="camera"
    with pytest.raises(AppError):match_invoice_lines([dict(item_code="",item_name="Camera",quantity=1)],stock,"OUT")


def test_post_requires_direction(env):
    s,t=env
    with pytest.raises(AppError):match_invoice_lines([dict(item_code="010716",quantity=1)],s.stock(t),"")


def test_postgres_lock_compiles():
    s=Store.for_tests()
    q=select(s.tables["stock_state"]).with_for_update()
    assert "FOR UPDATE" in str(q.compile(dialect=postgresql.dialect()))


def test_cloud_configuration_never_allows_sqlite():
    with pytest.raises(AppError):Store.from_settings({"url":"sqlite:///inventory.db"})
    with pytest.raises(AppError):Store.from_settings({"host":"x","user":"x","password":"x","dbname":"x","sslmode":"disable"})


def test_usernames_have_no_character_or_minimum_length_rule():
    s=Store.for_tests();s.initialize(password="bootstrap")
    t=s.login("admin","bootstrap")
    for username in ["x","موظف مخزن","user name","@"]:
        s.create_user(t,username,"p","store",username)
        assert s.login(username,"p")


def test_delete_invoice_after_last_baseline_removed():
    s=Store.for_tests();s.initialize(password=PASS);t=s.login("admin",PASS)
    s.replace_stock(t,PASS,sample_stock(),"baseline-cleanup",s.state(t)["revision"])
    s.post(t,PASS,change(3),"invoice-cleanup",source="INVOICE",reference="112233",image_hash="c"*64)
    catalog=s.deletion_catalog(t)
    assert catalog["stock_reports"]
    baseline_id=catalog["stock_reports"][0]["operation_id"]
    s.delete_stock_report(t,PASS,baseline_id)
    assert s.stock(t).empty
    assert not s.ledger(t).empty
    s.delete_invoice(t,PASS,"112233")
    assert s.ledger(t).empty
    assert s.recent_invoices(t)==[]

def test_delete_manual_movement_after_last_baseline_removed():
    s=Store.for_tests();s.initialize(password=PASS);t=s.login("admin",PASS)
    s.replace_stock(t,PASS,sample_stock(),"baseline-cleanup-manual",s.state(t)["revision"])
    op=s.post(t,PASS,change(1),"movement-cleanup",reason="cleanup",delivery_note=True)
    baseline_id=s.deletion_catalog(t)["stock_reports"][0]["operation_id"]
    s.delete_stock_report(t,PASS,baseline_id)
    assert s.stock(t).empty
    s.delete_movement(t,PASS,op)
    assert s.ledger(t).empty
