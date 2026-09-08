"""Create an encrypted full application snapshot; never print credentials/data."""
from pathlib import Path
import argparse
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gp_store import Store, utcnow
from gp_backup import encrypt_snapshot


def env_store():
    return Store.from_settings({"host":os.environ.get("PGHOST",""),"port":os.environ.get("PGPORT",5432),
        "user":os.environ.get("PGUSER",""),"password":os.environ.get("PGPASSWORD",""),
        "dbname":os.environ.get("PGDATABASE","postgres"),"sslmode":"require"})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="backups")
    args=parser.parse_args()
    folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    key=os.environ.get("GP_BACKUP_KEY","")
    try:
        store=env_store()
        snapshot=store.export_snapshot(for_backup_job=True)
        encrypted=encrypt_snapshot(snapshot,key)
        path=folder/("gp_"+utcnow().strftime("%Y%m%dT%H%M%SZ")+".gpbackup")
        tmp=path.with_suffix(".tmp")
        tmp.write_bytes(encrypted);tmp.replace(path)
        print("Encrypted backup created:",path.name)
        return 0
    except Exception as error:
        print("Backup failed; no plaintext artifact was written. Error type:",type(error).__name__,file=sys.stderr)
        return 1


if __name__=="__main__":raise SystemExit(main())
