from pathlib import Path

script = Path(__file__).with_name("live_v6_update2.py")
code = compile(script.read_text(encoding="utf-8"), str(script), "exec")
exec(code, {"__name__": "__main__", "__file__": str(script)})
