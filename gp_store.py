"""Transactional cloud storage for Golden Palace (PostgreSQL / Supabase).

All business writes lock the singleton state row before reading balances.
The app never falls back to a local database when the cloud is unavailable.
The SQLite path exists ONLY in Store.for_tests(), for offline regression tests.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import base64
import hashlib
import hmac
import json
import re
import secrets
import uuid
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import (
    MetaData, Table, Column, String, Text, Integer, BigInteger, Numeric,
    Boolean, Date, DateTime, JSON, ForeignKey, UniqueConstraint, CheckConstraint,
    Index, select, insert, update, delete, func, create_engine,
)
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool

from gp_core import (
    COL_CODE, COL_NAME, COL_QTY, COL_KEY, COL_MATCH, COL_DATE, COL_REF,
    COL_IN, COL_OUT, COL_BAL, COL_USER, COL_CUSTOMER, COL_NOTE,
    normalize_item_name, normalize_item_code, ensure_unique_stock_keys,
)

SCHEMA_VERSION = 5
SCHEMA = "gp_inventory"
PBKDF_ROUNDS = 600_000
MAX_QTY = Decimal("1000000000000")
DEFAULT_SETTINGS = {
    "lead_days": 30, "safety_days": 15, "slow_days": 90,
    "demand_window_days": 90, "review_days": 30,
    "purchase_prefixes": ["\u0625\u062f.\u0645. \u0645. \u0645."],
}


class AppError(ValueError):
    """Safe, actionable business validation error, never a connection string."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def decimal_qty(value, *, positive=False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise AppError("Invalid quantity")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise AppError("Invalid quantity") from None
    if not number.is_finite() or abs(number) > MAX_QTY or (positive and number <= 0):
        raise AppError("Invalid quantity")
    if number != number.quantize(Decimal("0.0001")):
        raise AppError("Use at most four decimal places")
    return number


def password_hash(password: str, *, enforce_policy=True) -> str:
    if enforce_policy and (len(password) < 12 or len(password) > 256):
        raise AppError("Use a password of 12 to 256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF_ROUNDS)
    return "pbkdf2_sha256$%d$%s$%s" % (
        PBKDF_ROUNDS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, target = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 2_000_000 or len(password) > 256:
            return False
        value = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(value, base64.b64decode(target))
    except (ValueError, TypeError):
        return False


def clean_json(value):
    """Portable, strict JSON; never pickle/unpickle backups or user uploads."""
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if value is None:
        return None
    if isinstance(value, float) and not pd.notna(value):
        return None
    if hasattr(value, "item"):
        return clean_json(value.item())
    return value


def make_tables(schema=SCHEMA):
    m = MetaData(schema=schema)
    state = Table("app_state", m,
        Column("id", Integer, primary_key=True),
        Column("schema_version", Integer, nullable=False),
        Column("revision", BigInteger, nullable=False, default=0),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Column("settings", JSON, nullable=False),
        Column("history_as_of", DateTime(timezone=True)),
        Column("history_hash", String(64)),
        Column("timezone", String(64), nullable=False),
        CheckConstraint("id = 1"))
    users = Table("app_users", m,
        Column("username", String(80), primary_key=True),
        Column("display_name", String(120), nullable=False),
        Column("role", String(16), nullable=False),
        Column("password_hash", Text, nullable=False),
        Column("active", Boolean, nullable=False, default=True),
        Column("failed_attempts", Integer, nullable=False, default=0),
        Column("locked_until", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False),
        CheckConstraint("role IN ('admin', 'store')"))
    sessions = Table("auth_sessions", m,
        Column("token_hash", String(64), primary_key=True),
        Column("username", String(80), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("expires_at", DateTime(timezone=True), nullable=False))
    stock = Table("stock_state", m,
        Column("item_key", Text, primary_key=True),
        Column("item_code", String(160), nullable=False),
        Column("item_name", Text, nullable=False),
        Column("quantity", Numeric(20, 4), nullable=False),
        Column("match_key", Text, nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False))
    operations = Table("operations", m,
        Column("operation_id", String(36), primary_key=True),
        Column("request_key", String(100), nullable=False, unique=True),
        Column("payload_hash", String(64), nullable=False),
        Column("username", String(80), nullable=False),
        Column("source", String(30), nullable=False),
        Column("business_date", Date, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("details", JSON, nullable=False))
    ledger = Table("movement_ledger", m,
        Column("ledger_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
        Column("operation_id", String(36), nullable=False),
        Column("line_no", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("business_date", Date, nullable=False),
        Column("username", String(80), nullable=False),
        Column("source", String(16), nullable=False),
        Column("movement_type", String(3), nullable=False),
        Column("item_key", Text, nullable=False),
        Column("item_code", String(160), nullable=False),
        Column("item_name", Text, nullable=False),
        Column("quantity", Numeric(20,4), nullable=False),
        Column("quantity_before", Numeric(20,4), nullable=False),
        Column("quantity_after", Numeric(20,4), nullable=False),
        Column("invoice_reference", String(160), nullable=False),
        Column("without_invoice", Boolean, nullable=False),
        Column("delivery_note", Boolean, nullable=False),
        Column("reason", Text, nullable=False),
        UniqueConstraint("operation_id", "line_no"),
        CheckConstraint("movement_type IN ('IN', 'OUT')"),
        CheckConstraint("quantity > 0"))
    invoices = Table("posted_invoices", m,
        Column("invoice_reference", String(160), primary_key=True),
        Column("image_hash", String(64), unique=True),
        Column("operation_id", String(36), nullable=False, unique=True),
        Column("posted_at", DateTime(timezone=True), nullable=False),
        Column("username", String(80), nullable=False),
        Column("recognized_json", JSON, nullable=False))
    history = Table("imported_movement_history", m,
        Column("row_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
        Column("item_code", String(160), nullable=False),
        Column("item_name", Text, nullable=False),
        Column("movement_date", DateTime(timezone=True), nullable=False),
        Column("reference", Text, nullable=False),
        Column("customer", Text, nullable=False),
        Column("qty_in", Numeric(20,4), nullable=False),
        Column("qty_out", Numeric(20,4), nullable=False),
        Column("balance", Numeric(20,4)),
        Column("username", String(80), nullable=False),
        Column("statement", Text, nullable=False),
        Column("match_key", Text, nullable=False))
    drafts = Table("invoice_drafts", m,
        Column("draft_id", String(36), primary_key=True),
        Column("username", String(80), nullable=False),
        Column("image_hash", String(64)),
        Column("source_name", String(240), nullable=False),
        Column("payload", JSON, nullable=False),
        Column("status", String(16), nullable=False),
        Column("version", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("username", "image_hash"),
        CheckConstraint("status IN ('pending', 'posted', 'discarded')"))
    closures = Table("daily_closures", m,
        Column("business_date", Date, primary_key=True),
        Column("closed_at", DateTime(timezone=True), nullable=False),
        Column("username", String(80), nullable=False),
        Column("movement_count", Integer, nullable=False),
        Column("total_in", Numeric(20,4), nullable=False),
        Column("total_out", Numeric(20,4), nullable=False),
        Column("no_invoice_count", Integer, nullable=False),
        Column("analysis", JSON, nullable=False))
    snapshots = Table("daily_stock_snapshots", m,
        Column("business_date", Date, primary_key=True),
        Column("item_key", Text, primary_key=True),
        Column("item_code", String(160), nullable=False),
        Column("item_name", Text, nullable=False),
        Column("quantity", Numeric(20,4), nullable=False),
        Column("match_key", Text, nullable=False))
    baselines = Table("baseline_snapshots", m,
        Column("operation_id", String(36), primary_key=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("username", String(80), nullable=False),
        Column("stock", JSON, nullable=False))
    audit = Table("audit_log", m,
        Column("event_id", String(36), primary_key=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("username", String(80), nullable=False),
        Column("action", String(40), nullable=False),
        Column("details", JSON, nullable=False))
    Index("ix_ledger_business_date", ledger.c.business_date)
    Index("ix_history_match_date", history.c.match_key, history.c.movement_date)
    Index("ix_draft_owner_status", drafts.c.username, drafts.c.status)
    return m, {t.name: t for t in m.tables.values()}


class Store:
    def __init__(self, engine, schema=SCHEMA):
        self.engine = engine
        self.metadata, self.tables = make_tables(schema)
        self.tz = ZoneInfo("Asia/Damascus")

    @classmethod
    def from_settings(cls, config):
        required = ("host", "user", "password", "dbname")
        if any(not str(config.get(k, "")).strip() or "PASTE_" in str(config.get(k)) for k in required):
            raise AppError("Complete the database settings in Streamlit Secrets")
        if str(config.get("sslmode", "require")) not in ("require", "verify-ca", "verify-full"):
            raise AppError("Database TLS must be enabled")
        url = URL.create("postgresql+psycopg", username=config["user"], password=config["password"],
                         host=config["host"], port=int(config.get("port",5432)), database=config["dbname"])
        args = {"sslmode": config.get("sslmode", "require"), "connect_timeout": 12,
                "prepare_threshold": None, "application_name": "golden_palace_v5",
                "options": "-c statement_timeout=60000 -c lock_timeout=15000"}
        if config.get("sslrootcert"):
            args["sslrootcert"] = str(config["sslrootcert"])
        engine = create_engine(url, pool_size=2, max_overflow=1, pool_pre_ping=True,
                               pool_recycle=300, connect_args=args, hide_parameters=True)
        return cls(engine)

    @classmethod
    def for_tests(cls):
        """Explicit offline test database, not available through app configuration."""
        engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})
        store = cls(engine, schema=None)
        store.metadata.create_all(engine)
        with engine.begin() as c:
            c.execute(insert(store.tables["app_state"]).values(id=1, schema_version=5, revision=0,
                settings=DEFAULT_SETTINGS, updated_at=utcnow(), timezone="Asia/Damascus"))
        return store

    def _lock(self, conn):
        t = self.tables["app_state"]
        row = conn.execute(select(t).where(t.c.id == 1).with_for_update()).mappings().one()
        if row["schema_version"] != SCHEMA_VERSION:
            raise AppError("Run sql/setup.sql for this app version")
        self.tz = ZoneInfo(row["timezone"])
        return row

    def _touch(self, conn):
        t = self.tables["app_state"]
        conn.execute(update(t).where(t.c.id == 1).values(revision=t.c.revision+1, updated_at=utcnow()))

    def _audit(self, conn, username, action, details=None):
        conn.execute(insert(self.tables["audit_log"]).values(event_id=str(uuid.uuid4()),
            created_at=utcnow(), username=username, action=action, details=clean_json(details or {})))

    def initialize(self, username="admin", password="", timezone_name="Asia/Damascus"):
        with self.engine.begin() as c:
            state = self._lock(c)
            users = self.tables["app_users"]
            if c.execute(select(func.count()).select_from(users)).scalar_one() == 0:
                if not password or "PASTE_" in password or "CHANGE_" in password:
                    raise AppError("Set a new bootstrap admin password in Secrets")
                if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", username):
                    raise AppError("Use 3 to 80 letters, digits, dots or underscores for usernames")
                ZoneInfo(timezone_name)
                c.execute(insert(users).values(username=username, display_name=username, role="admin",
                    password_hash=password_hash(password), active=True, failed_attempts=0, created_at=utcnow()))
                c.execute(update(self.tables["app_state"]).where(self.tables["app_state"].c.id==1).values(timezone=timezone_name))
                self.tz = ZoneInfo(timezone_name)
                self._audit(c, username, "ADMIN_BOOTSTRAP")

    def login(self, username, password, session_hours=12):
        username = str(username).strip()
        error = False
        token = None
        with self.engine.begin() as c:
            u, s = self.tables["app_users"], self.tables["auth_sessions"]
            row = c.execute(select(u).where(u.c.username==username).with_for_update()).mappings().first()
            now = utcnow()
            if row and row["locked_until"] and aware(row["locked_until"]) > now:
                error = True
            elif row and row["active"] and password_matches(password, row["password_hash"]):
                token = secrets.token_urlsafe(32)
                c.execute(update(u).where(u.c.username==username).values(failed_attempts=0, locked_until=None))
                c.execute(delete(s).where(s.c.expires_at < now))
                c.execute(insert(s).values(token_hash=hashlib.sha256(token.encode()).hexdigest(), username=username,
                    created_at=now, expires_at=now+timedelta(hours=min(24,max(1,int(session_hours))))))
            else:
                error = True
                if row:
                    failures = row["failed_attempts"]+1
                    c.execute(update(u).where(u.c.username==username).values(failed_attempts=failures if failures<5 else 0,
                        locked_until=now+timedelta(minutes=15) if failures>=5 else None))
                else:
                    # Similar password-derivation work for unknown accounts.
                    hashlib.pbkdf2_hmac("sha256", str(password)[:256].encode(), b"gp-login-check", PBKDF_ROUNDS)
        if error:
            raise AppError("Login failed or account temporarily locked")
        return token

    def _actor(self, conn, token, password=None, admin=False):
        if not token:
            raise AppError("Please sign in again")
        u, s = self.tables["app_users"], self.tables["auth_sessions"]
        row = conn.execute(select(u).join(s, s.c.username==u.c.username).where(
            s.c.token_hash==hashlib.sha256(token.encode()).hexdigest(), s.c.expires_at>utcnow(), u.c.active.is_(True)
        )).mappings().first()
        if not row:
            raise AppError("Please sign in again")
        if row["locked_until"] and aware(row["locked_until"]) > utcnow():
            raise AppError("Login failed or account temporarily locked")
        if admin and row["role"] != "admin":
            raise AppError("Administrator access required")
        if password is not None and not password_matches(password, row["password_hash"]):
            raise AppError("Incorrect approval password")
        return dict(row)

    def actor(self, token):
        with self.engine.connect() as c:
            row = self._actor(c, token)
        return {k:row[k] for k in ("username", "display_name", "role")}

    def logout(self, token):
        with self.engine.begin() as c:
            s = self.tables["auth_sessions"]
            c.execute(delete(s).where(s.c.token_hash==hashlib.sha256(token.encode()).hexdigest()))

    def state(self, token):
        with self.engine.connect() as c:
            self._actor(c, token)
            row = c.execute(select(self.tables["app_state"])).mappings().one()
            self.tz = ZoneInfo(row["timezone"])
            return dict(row)

    def _open_day(self, c, day):
        t = self.tables["daily_closures"]
        if c.execute(select(t.c.business_date).where(t.c.business_date==day)).first():
            raise AppError("This business day is closed")

    def today(self):
        return utcnow().astimezone(self.tz).date()

    def _operation(self, c, token, password, request_key, source, data, *, admin=False):
        self._lock(c)
        actor = self._actor(c, token, password, admin=admin)
        if not request_key or len(request_key)>100:
            raise AppError("Invalid operation identifier")
        data = {"actor":actor["username"], "source":source, "data":data}
        fingerprint = hashlib.sha256(json.dumps(clean_json(data),sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        t = self.tables["operations"]
        previous = c.execute(select(t).where(t.c.request_key==request_key)).mappings().first()
        if previous:
            if previous["payload_hash"] != fingerprint:
                raise AppError("This operation identifier was already used with different data")
            return actor, previous["operation_id"], True, fingerprint
        return actor, str(uuid.uuid4()), False, fingerprint

    def _record_operation(self, c, actor, operation_id, request_key, source, fingerprint, details):
        c.execute(insert(self.tables["operations"]).values(operation_id=operation_id, request_key=request_key,
            payload_hash=fingerprint, username=actor["username"], source=source, business_date=self.today(),
            created_at=utcnow(), details=clean_json(details)))
        self._audit(c, actor["username"], source, {"operation_id":operation_id})
        self._touch(c)

    @staticmethod
    def stock_frame(rows):
        return pd.DataFrame([{COL_KEY:r["item_key"],COL_CODE:r["item_code"],COL_NAME:r["item_name"],
            COL_QTY:float(r["quantity"]),COL_MATCH:r["match_key"]} for r in rows],
            columns=[COL_KEY,COL_CODE,COL_NAME,COL_QTY,COL_MATCH])

    def stock(self, token):
        with self.engine.connect() as c:
            self._actor(c,token)
            rows=c.execute(select(self.tables["stock_state"]).order_by(self.tables["stock_state"].c.item_name)).mappings().all()
            return self.stock_frame(rows)

    def replace_stock(self, token, password, df, request_key, expected_revision):
        if df is None or df.empty:
            raise AppError("The stock report is empty")
        df=ensure_unique_stock_keys(df.copy())
        rows=[]
        for _,r in df.iterrows():
            name=str(r[COL_NAME]).strip(); key=str(r[COL_KEY]).strip(); code=normalize_item_code(r[COL_CODE])
            if not name or not key or len(code)>160:
                raise AppError("Invalid stock row")
            rows.append(dict(item_key=key,item_code=code,item_name=name,quantity=decimal_qty(r[COL_QTY]),
                match_key=normalize_item_name(name),updated_at=utcnow()))
        if len({r["item_key"] for r in rows})!=len(rows):
            raise AppError("Duplicate stock keys")
        data=[{k:v for k,v in r.items() if k!="updated_at"} for r in rows]
        with self.engine.begin() as c:
            actor,op,again,fp=self._operation(c,token,password,request_key,"BASELINE",data,admin=True)
            if again:return op
            state=self._lock(c)
            if state["revision"]!=expected_revision:
                raise AppError("Data changed. Refresh before replacing stock")
            self._open_day(c,self.today())
            l=self.tables["movement_ledger"]
            if c.execute(select(l.c.ledger_id).where(l.c.business_date==self.today()).limit(1)).first():
                raise AppError("Set a new baseline before the first movement of the day")
            t=self.tables["stock_state"]
            old=c.execute(select(t)).mappings().all()
            c.execute(insert(self.tables["baseline_snapshots"]).values(operation_id=op,created_at=utcnow(),
                username=actor["username"],stock={"before":clean_json([dict(r) for r in old]),"after":clean_json(data)}))
            c.execute(delete(t)); c.execute(insert(t),rows)
            self._record_operation(c,actor,op,request_key,"BASELINE",fp,{"row_count":len(rows)})
            return op

    def import_history(self, token, password, df, file_hash, as_of, request_key):
        if df is None or df.empty:
            raise AppError("The movement report is empty")
        as_of=aware(as_of).astimezone(timezone.utc)
        if as_of>utcnow()+timedelta(minutes=2):
            raise AppError("The history cutoff cannot be in the future")
        rows=[]
        for _,r in df.iterrows():
            dt=pd.Timestamp(r[COL_DATE]).to_pydatetime()
            dt=dt.replace(tzinfo=self.tz) if dt.tzinfo is None else dt
            if dt>as_of:
                raise AppError("The cutoff is earlier than a movement in the report")
            rows.append(dict(item_code=normalize_item_code(r[COL_CODE]),item_name=str(r[COL_NAME]),movement_date=dt,
                reference=str(r[COL_REF]),customer=str(r.get(COL_CUSTOMER,"")),qty_in=decimal_qty(r[COL_IN]),
                qty_out=decimal_qty(r[COL_OUT]),balance=None if pd.isna(r[COL_BAL]) else decimal_qty(r[COL_BAL]),
                username=str(r.get(COL_USER,"")),statement=str(r.get(COL_NOTE,"")),match_key=str(r[COL_MATCH])))
        with self.engine.begin() as c:
            actor,op,again,fp=self._operation(c,token,password,request_key,"HISTORY_IMPORT",
                {"file_hash":file_hash,"as_of":as_of},admin=True)
            if again:return op
            t=self.tables["imported_movement_history"]
            c.execute(delete(t))
            for i in range(0,len(rows),1000):c.execute(insert(t),rows[i:i+1000])
            # Only unambiguous exact-name matches may fill a missing code.
            mapping={}
            for r in rows:
                if r["item_code"]:mapping.setdefault(r["match_key"],set()).add(r["item_code"])
            s=self.tables["stock_state"]
            for r in c.execute(select(s).where(s.c.item_code=="")).mappings().all():
                codes=mapping.get(r["match_key"],set())
                if len(codes)==1:
                    c.execute(update(s).where(s.c.item_key==r["item_key"]).values(item_code=next(iter(codes)),updated_at=utcnow()))
            a=self.tables["app_state"]
            c.execute(update(a).where(a.c.id==1).values(history_as_of=as_of,history_hash=file_hash))
            self._record_operation(c,actor,op,request_key,"HISTORY_IMPORT",fp,{"rows":len(rows),"as_of":as_of})
            return op

    def movement_history(self, token):
        with self.engine.connect() as c:
            self._actor(c,token)
            state=c.execute(select(self.tables["app_state"])).mappings().one()
            rows=c.execute(select(self.tables["imported_movement_history"])).mappings().all()
            l=self.tables["movement_ledger"]
            query=select(l)
            if state["history_as_of"]:
                query=query.where(l.c.created_at>state["history_as_of"])
            local=c.execute(query.order_by(l.c.ledger_id)).mappings().all()
        result=[]
        for r in rows:
            result.append({COL_CODE:r["item_code"],COL_NAME:r["item_name"],COL_DATE:aware(r["movement_date"]).astimezone(self.tz).replace(tzinfo=None),
                COL_REF:r["reference"],COL_CUSTOMER:r["customer"],COL_IN:float(r["qty_in"]),COL_OUT:float(r["qty_out"]),
                COL_BAL:None if r["balance"] is None else float(r["balance"]),COL_USER:r["username"],COL_NOTE:r["statement"],COL_MATCH:r["match_key"]})
        for r in local:
            result.append({COL_CODE:r["item_code"],COL_NAME:r["item_name"],COL_DATE:aware(r["created_at"]).astimezone(self.tz).replace(tzinfo=None),
                COL_REF:r["invoice_reference"],COL_CUSTOMER:"",COL_IN:float(r["quantity"]) if r["movement_type"]=="IN" else 0,
                COL_OUT:float(r["quantity"]) if r["movement_type"]=="OUT" else 0,COL_BAL:float(r["quantity_after"]),
                COL_USER:r["username"],COL_NOTE:r["reason"],COL_MATCH:normalize_item_name(r["item_name"])})
        return pd.DataFrame(result)

    def post(self, token, password, changes, request_key, *, source="MANUAL", reference="", image_hash=None,
             reason="", delivery_note=False, reviewed=None, draft_id=None, expected_draft_version=None):
        if source not in ("MANUAL","INVOICE") or not changes:
            raise AppError("No valid movement lines")
        reference=str(reference).strip()
        if len(reference)>160:raise AppError("Reference is too long")
        if source=="INVOICE" and not reference:raise AppError("Invoice reference is required")
        if source=="MANUAL" and not str(reason).strip():raise AppError("A movement reason is required")
        grouped={}
        for r in changes:
            if r["movement_type"] not in ("IN","OUT"):raise AppError("Select IN or OUT")
            qty=decimal_qty(r["quantity"],positive=True)
            key=(str(r["item_key"]),r["movement_type"])
            grouped[key]=grouped.get(key,Decimal(0))+qty
        normalized=[dict(item_key=k,movement_type=d,quantity=decimal_qty(q,positive=True)) for (k,d),q in sorted(grouped.items())]
        if source=="MANUAL" and any(r["movement_type"]=="OUT" for r in normalized) and not delivery_note:
            raise AppError("Confirm the delivery note before stock OUT")
        data=dict(lines=normalized,reference=reference,image_hash=image_hash,reason=reason,delivery_note=bool(delivery_note),draft_id=draft_id)
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
            # Updates, ledger, duplicate register and draft status share one commit.
            self._record_operation(c,actor,op,request_key,source,fp,{"reference":reference,"lines":len(ledger)})
            c.execute(insert(self.tables["movement_ledger"]),ledger)
            for key,r in balances.items():
                c.execute(update(t).where(t.c.item_key==key).values(quantity=r["quantity"],updated_at=now))
            if source=="INVOICE":
                c.execute(insert(inv).values(invoice_reference=reference,image_hash=image_hash,operation_id=op,posted_at=now,
                    username=actor["username"],recognized_json=clean_json(reviewed or {})))
            if draft_id:
                d=self.tables["invoice_drafts"]
                c.execute(update(d).where(d.c.draft_id==draft_id).values(status="posted",updated_at=now,version=d.c.version+1))
            return op

    def _owned_draft(self,c,actor,draft_id):
        t=self.tables["invoice_drafts"]
        r=c.execute(select(t).where(t.c.draft_id==draft_id).with_for_update()).mappings().first()
        if not r or (r["username"]!=actor["username"] and actor["role"]!="admin"):
            raise AppError("Draft not found")
        return r

    def create_draft(self, token, source_name="", image_hash=None, payload=None):
        now=utcnow()
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token); t=self.tables["invoice_drafts"]
            if image_hash:
                previous=c.execute(select(t).where(t.c.username==actor["username"],t.c.image_hash==image_hash)).mappings().first()
                if previous:return previous["draft_id"]
            draft_id=str(uuid.uuid4())
            c.execute(insert(t).values(draft_id=draft_id,username=actor["username"],image_hash=image_hash,
                source_name=str(source_name)[:240],payload=clean_json(payload or {"invoice_number":"","movement_type":"","items":[]}),
                status="pending",version=1,created_at=now,updated_at=now))
            self._touch(c)
            return draft_id

    def drafts(self,token):
        with self.engine.connect() as c:
            actor=self._actor(c,token); t=self.tables["invoice_drafts"]
            q=select(t).where(t.c.status=="pending")
            if actor["role"]!="admin":q=q.where(t.c.username==actor["username"])
            return [dict(r) for r in c.execute(q.order_by(t.c.updated_at.desc())).mappings()]

    def save_draft(self,token,draft_id,payload,expected_version):
        payload=clean_json(payload)
        if not isinstance(payload,dict) or not isinstance(payload.get("items"),list) or len(payload["items"])>100:
            raise AppError("Invalid draft")
        if len(json.dumps(payload,allow_nan=False).encode())>1_000_000:raise AppError("Draft too large")
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token); old=self._owned_draft(c,actor,draft_id)
            if old["status"]!="pending":raise AppError("This draft is no longer pending")
            if old["version"]!=expected_version:raise AppError("Draft changed in another window. Reload it")
            t=self.tables["invoice_drafts"]
            c.execute(update(t).where(t.c.draft_id==draft_id).values(payload=payload,version=old["version"]+1,updated_at=utcnow()))
            self._touch(c)
            return old["version"]+1

    def discard_draft(self,token,draft_id):
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token); self._owned_draft(c,actor,draft_id)
            t=self.tables["invoice_drafts"]
            c.execute(update(t).where(t.c.draft_id==draft_id).values(status="discarded",updated_at=utcnow(),version=t.c.version+1))
            self._audit(c,actor["username"],"DISCARD_DRAFT",{"draft_id":draft_id}); self._touch(c)

    def ledger(self,token,day=None):
        with self.engine.connect() as c:
            self._actor(c,token); t=self.tables["movement_ledger"]; q=select(t)
            if day:q=q.where(t.c.business_date==day)
            return pd.DataFrame([dict(r) for r in c.execute(q.order_by(t.c.ledger_id)).mappings()])

    def closure(self,token,day):
        with self.engine.connect() as c:
            self._actor(c,token); t=self.tables["daily_closures"]
            r=c.execute(select(t).where(t.c.business_date==day)).mappings().first()
            return dict(r) if r else None

    def day_stock(self,token,day):
        with self.engine.connect() as c:
            self._actor(c,token); t=self.tables["daily_stock_snapshots"]
            rows=c.execute(select(t).where(t.c.business_date==day)).mappings().all()
            return self.stock_frame(rows)

    def close_day(self,token,password,day,analysis,expected_revision):
        with self.engine.begin() as c:
            state=self._lock(c); actor=self._actor(c,token,password,admin=True)
            if day!=self.today():raise AppError("Only today can be closed")
            if state["revision"]!=expected_revision:raise AppError("Data changed. Refresh before closing the day")
            self._open_day(c,day)
            l=self.tables["movement_ledger"]
            rows=c.execute(select(l).where(l.c.business_date==day)).mappings().all()
            total_in=sum((r["quantity"] for r in rows if r["movement_type"]=="IN"),Decimal(0))
            total_out=sum((r["quantity"] for r in rows if r["movement_type"]=="OUT"),Decimal(0))
            c.execute(insert(self.tables["daily_closures"]).values(business_date=day,closed_at=utcnow(),username=actor["username"],
                movement_count=len(rows),total_in=total_in,total_out=total_out,no_invoice_count=sum(bool(r["without_invoice"]) for r in rows),
                analysis=clean_json(analysis.to_dict("records") if analysis is not None else [])))
            stock=c.execute(select(self.tables["stock_state"])).mappings().all()
            if stock:c.execute(insert(self.tables["daily_stock_snapshots"]),[{"business_date":day,**{k:r[k] for k in ("item_key","item_code","item_name","quantity","match_key")}} for r in stock])
            self._audit(c,actor["username"],"CLOSE_DAY",{"day":day}); self._touch(c)

    def save_settings(self,token,password,settings):
        safe={}
        for key,low,high in (("lead_days",1,730),("safety_days",0,365),("slow_days",30,730),("demand_window_days",7,730),("review_days",1,365)):
            number=int(settings[key])
            if not low<=number<=high:raise AppError("Analysis setting is outside the allowed range")
            safe[key]=number
        safe["purchase_prefixes"]=[str(x).strip() for x in settings.get("purchase_prefixes",[]) if str(x).strip()]
        with self.engine.begin() as c:
            self._lock(c); actor=self._actor(c,token,password,admin=True);t=self.tables["app_state"]
            c.execute(update(t).where(t.c.id==1).values(settings=safe))
            self._audit(c,actor["username"],"SETTINGS",safe);self._touch(c)

    def list_users(self,token):
        with self.engine.connect() as c:
            self._actor(c,token,admin=True);t=self.tables["app_users"]
            return [dict(r) for r in c.execute(select(t.c.username,t.c.display_name,t.c.role,t.c.active,t.c.created_at)).mappings()]

    def create_user(self,token,password,username,new_password,role,display_name=""):
        username=str(username).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}",username):raise AppError("Use 3 to 80 letters, digits, dots or underscores for usernames")
        if role not in ("admin","store"):raise AppError("Invalid role")
        hashed=password_hash(new_password)
        with self.engine.begin() as c:
            self._lock(c);actor=self._actor(c,token,password,admin=True);t=self.tables["app_users"]
            if c.execute(select(t.c.username).where(t.c.username==username)).first():raise AppError("Username already exists")
            c.execute(insert(t).values(username=username,display_name=str(display_name or username)[:120],role=role,password_hash=hashed,
                active=True,failed_attempts=0,created_at=utcnow()))
            self._audit(c,actor["username"],"CREATE_USER",{"username":username,"role":role});self._touch(c)

    def change_password(self,token,password,new_password):
        hashed=password_hash(new_password)
        with self.engine.begin() as c:
            self._lock(c);actor=self._actor(c,token,password);t=self.tables["app_users"]
            c.execute(update(t).where(t.c.username==actor["username"]).values(password_hash=hashed,failed_attempts=0,locked_until=None))
            s=self.tables["auth_sessions"]
            current=hashlib.sha256(token.encode()).hexdigest()
            c.execute(delete(s).where(s.c.username==actor["username"],s.c.token_hash!=current))
            self._audit(c,actor["username"],"CHANGE_PASSWORD");self._touch(c)

    def set_user_active(self,token,password,username,active):
        with self.engine.begin() as c:
            self._lock(c);actor=self._actor(c,token,password,admin=True);t=self.tables["app_users"]
            if username==actor["username"]:raise AppError("You cannot disable your own account")
            row=c.execute(select(t).where(t.c.username==username)).mappings().first()
            if not row:raise AppError("User not found")
            c.execute(update(t).where(t.c.username==username).values(active=bool(active)))
            s=self.tables["auth_sessions"]
            c.execute(delete(s).where(s.c.username==username))
            self._audit(c,actor["username"],"USER_STATUS",{"username":username,"active":bool(active)});self._touch(c)

    def audit(self,token,limit=1000):
        with self.engine.connect() as c:
            self._actor(c,token,admin=True);t=self.tables["audit_log"]
            return pd.DataFrame([dict(r) for r in c.execute(select(t).order_by(t.c.created_at.desc()).limit(limit)).mappings()])

    def export_snapshot(self,token=None,*,for_backup_job=False):
        """Consistent logical snapshot, including all business tables and users.
        Login sessions are deliberately excluded, so restores cannot revive them.
        """
        engine=self.engine
        opts={"isolation_level":"REPEATABLE READ"} if engine.dialect.name=="postgresql" else {}
        with engine.connect().execution_options(**opts) as c:
            with c.begin():
                if not for_backup_job:self._actor(c,token,admin=True)
                result={}
                for name,t in self.tables.items():
                    if name!="auth_sessions":
                        result[name]=[clean_json(dict(r)) for r in c.execute(select(t)).mappings()]
                return {"format":"golden-palace-cloud","schema_version":SCHEMA_VERSION,"created_at":utcnow().isoformat(),"tables":result}

    def restore_empty(self,document):
        """CLI only: refuse to overwrite any existing users or business data."""
        expected=set(self.tables)-{"auth_sessions"}
        if not isinstance(document,dict) or document.get("format")!="golden-palace-cloud" or document.get("schema_version")!=5:
            raise AppError("Unsupported snapshot version")
        if set(document.get("tables",{}))!=expected:raise AppError("Incomplete snapshot")
        prepared={}
        for name,values in document["tables"].items():
            if not isinstance(values,list):raise AppError("Invalid snapshot table")
            table=self.tables[name]; prepared[name]=[]
            for value in values:
                if set(value)!=set(table.c.keys()):raise AppError("Invalid snapshot columns")
                row=dict(value)
                for col in table.c:
                    v=row[col.name]
                    if v is not None:
                        if isinstance(col.type,DateTime):row[col.name]=datetime.fromisoformat(v)
                        elif isinstance(col.type,Date):row[col.name]=date.fromisoformat(v)
                        elif isinstance(col.type,Numeric):row[col.name]=Decimal(v)
                prepared[name].append(row)
        if len(prepared["app_state"])!=1 or prepared["app_state"][0]["id"]!=1:raise AppError("Invalid application state")
        with self.engine.begin() as c:
            self._lock(c)
            for name,table in self.tables.items():
                if name!="app_state" and c.execute(select(func.count()).select_from(table)).scalar_one():
                    raise AppError("Restore requires a new empty project")
            c.execute(delete(self.tables["app_state"]))
            for name,rows in prepared.items():
                if rows:c.execute(insert(self.tables[name]),rows)
            if self.engine.dialect.name=="postgresql":
                # Restore explicit identities then advance their sequences.
                from sqlalchemy import text
                for name,column in (("movement_ledger","ledger_id"),("imported_movement_history","row_id")):
                    fq=f"{SCHEMA}.{name}"
                    c.execute(text(f"SELECT setval(pg_get_serial_sequence('{fq}','{column}'), COALESCE((SELECT MAX({column}) FROM {fq}),1), EXISTS(SELECT 1 FROM {fq}))"))
            self._audit(c,"restore-cli","RESTORE",{"snapshot_at":document["created_at"]});self._touch(c)
