import base64
from pathlib import Path

text = Path("backend/app/tabgen.py").read_text(encoding="utf-8")
key = 'STUB_TAB_FULL_GP5_BASE64 = (\n    "'
i = text.index(key) + len(key)
j = text.index('"\n)', i)
raw = text[i:j]
raw = "".join(ch for ch in raw if not ch.isspace())
if "=" in raw:
    raw = raw[: raw.rfind("=") + 1]
print("tail", repr(raw[-28:]), "len", len(raw), "mod4", len(raw) % 4)
b_loose = base64.b64decode(raw.encode("ascii"), validate=False)
print("bytes_loose", len(b_loose), "head16", b_loose[:16].hex())
fixed_b64 = base64.b64encode(b_loose).decode("ascii")
print("fixed_b64 len", len(fixed_b64), "mod4", len(fixed_b64) % 4)
base64.b64decode(fixed_b64.encode("ascii"), validate=True)
print("fixed strict ok")
Path("scripts/jam_gp5_b64_canonical.txt").write_text(fixed_b64, encoding="ascii")
