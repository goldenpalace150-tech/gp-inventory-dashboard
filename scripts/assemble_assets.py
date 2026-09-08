"""Reassemble the checked-in public logo without network access or credentials."""
from pathlib import Path
import base64
import hashlib

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "4a8d35163a99b182b20a178f67dd1386fb535c81933f986b743ee24ab6535cdc"


def main():
    parts = sorted((ROOT / "assets/encoded").glob("logo_*.b64"))
    if len(parts) != 9:
        raise RuntimeError("Expected nine logo segments")
    data = base64.b64decode("".join(p.read_text().strip() for p in parts), validate=True)
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise RuntimeError("Logo checksum mismatch; refusing to publish it")
    target = ROOT / "assets/golden_palace.jpg"
    target.write_bytes(data)
    print("Verified logo assembled:", len(data), "bytes")


if __name__ == "__main__":
    main()
