"""Extract _POSTGRES_SCHEMA from init_db.py into postgres_schema.sql"""
from pathlib import Path

src = Path("db/init_db.py").read_text(encoding="utf-8")

OPEN_MARKER = '_POSTGRES_SCHEMA = textwrap.dedent("""\\\n'
CLOSE_MARKER = '""")\n# fmt: on'

start_idx = src.index(OPEN_MARKER) + len(OPEN_MARKER)
end_idx   = src.index(CLOSE_MARKER, start_idx)

raw_sql = src[start_idx:end_idx]

# Strip the consistent 4-space leading indent textwrap.dedent would remove
lines = raw_sql.split("\n")
non_empty = [l for l in lines if l.strip()]
indent = min(len(l) - len(l.lstrip()) for l in non_empty) if non_empty else 0
dedented = "\n".join(l[indent:] if l.startswith(" " * indent) else l for l in lines)

out = Path("db/postgres_schema.sql")
out.write_text(dedented, encoding="utf-8")
print(f"Written {out}: {len(dedented)} bytes, {dedented.count(chr(10))} lines")
