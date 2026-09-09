from pathlib import Path
import re

path = Path(__file__).resolve().parents[1] / "gp_ui.py"
text = path.read_text(encoding="utf-8")
text, count = re.subn(r'BUILD = "GP-CLOUD-v\d+"', 'BUILD = "GP-CLOUD-v11"', text)
if count < 1:
    raise RuntimeError("No build marker found")
path.write_text(text, encoding="utf-8")
print(f"normalized {count} build markers")
