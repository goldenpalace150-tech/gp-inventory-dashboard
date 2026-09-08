"""Authenticated encrypted logical backups. Keep the Fernet key off-repository."""
import gzip
import io
import json
from cryptography.fernet import Fernet, InvalidToken
from gp_store import AppError

MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024


def encrypt_snapshot(snapshot, key):
    try:
        cipher=Fernet(key.encode() if isinstance(key,str) else key)
    except (TypeError,ValueError):
        raise AppError("Use a valid Fernet backup key") from None
    raw=json.dumps(snapshot,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
    if len(raw)>MAX_SNAPSHOT_BYTES:
        raise AppError("Snapshot exceeds the 256 MB logical-export limit; use pg_dump for larger databases")
    return cipher.encrypt(gzip.compress(raw,compresslevel=6))


def decrypt_snapshot(data,key):
    if len(data)>MAX_SNAPSHOT_BYTES:
        raise AppError("Backup file too large")
    try:
        compressed=Fernet(key.encode() if isinstance(key,str) else key).decrypt(data)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as archive:
            raw=archive.read(MAX_SNAPSHOT_BYTES+1)
        if len(raw)>MAX_SNAPSHOT_BYTES:raise AppError("Expanded snapshot is too large")
        document=json.loads(raw)
    except (InvalidToken,TypeError,ValueError,OSError):
        raise AppError("Backup authentication failed or the file is invalid") from None
    if not isinstance(document,dict):raise AppError("Invalid snapshot")
    return document
