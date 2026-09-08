"""Restore a v5 encrypted backup ONLY into a new, empty initialized project.
Run setup.sql first. Do NOT launch Streamlit/bootstrap an admin before restoring.
"""
from pathlib import Path
import argparse
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gp_backup import decrypt_snapshot
from backup import env_store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file",type=Path)
    parser.add_argument("--confirm-empty-target",action="store_true")
    args=parser.parse_args()
    try:
        doc=decrypt_snapshot(args.file.read_bytes(),os.environ.get("GP_BACKUP_KEY",""))
        print("Snapshot:",doc.get("created_at"),"schema:",doc.get("schema_version"))
        print("Tables:",len(doc.get("tables",{})))
        if not args.confirm_empty_target:
            print("Verified only. Add --confirm-empty-target to restore into a NEW empty project.")
            return 0
        env_store().restore_empty(doc)
        print("Restore committed. Login sessions were not restored.")
        return 0
    except Exception as error:
        print("Restore refused/failed. Error type:",type(error).__name__,file=sys.stderr)
        return 1


if __name__=="__main__":raise SystemExit(main())
