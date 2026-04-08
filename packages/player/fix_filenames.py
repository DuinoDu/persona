import os
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'packages/player/prisma/dev.db'
CONV_DIR = ROOT / 'packages/player/public/audios/conversations'

cn_date_re = re.compile(r'(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5')


def ascii_date(m):
    y, mo, d = m.group(1), m.group(2), m.group(3)
    return f"{y}{int(mo):02d}{int(d):02d}"


def to_ascii_filename(name):
    new = cn_date_re.sub(ascii_date, name)
    result = []
    for ch in new:
        if ord(ch) < 128:
            result.append(ch)
        else:
            result.append('')
    out = ''.join(result)
    out = re.sub(r'_+', '_', out)
    out = out.strip('_')
    if not out.endswith('.mp3'):
        out = out.rsplit('.', 1)[0] + '.mp3'
    return out


# Rename files
renamed = 0
skipped = 0
errors = 0
used_names = set()
rename_map = {}  # old_name -> new_name

for fn in sorted(os.listdir(CONV_DIR)):
    if not fn.endswith('.mp3'):
        continue
    new_name = to_ascii_filename(fn)
    if new_name == fn:
        used_names.add(new_name)
        skipped += 1
        continue
    # Handle duplicates
    base_name = new_name
    idx = 1
    while new_name in used_names:
        new_name = base_name.replace('.mp3', f'_{idx}.mp3')
        idx += 1
    used_names.add(new_name)
    old_path = CONV_DIR / fn
    new_path = CONV_DIR / new_name
    try:
        os.rename(old_path, new_path)
        rename_map[fn] = new_name
        renamed += 1
    except Exception:
        errors += 1

print(f"Files renamed: {renamed}, skipped: {skipped}, errors: {errors}")

# Update DB
conn = sqlite3.connect(DB)
c = conn.cursor()
updated = 0
db_errors = 0

for old_name, new_name in rename_map.items():
    new_path = f'/audios/conversations/{new_name}'
    # Extract date from new filename
    dm = re.match(r'(\d{8})', new_name)
    new_date = None
    if dm:
        ds = dm.group(1)
        new_date = f'{ds[:4]}-{ds[4:6]}-{ds[6:8]}'
    try:
        if new_date:
            c.execute(
                'UPDATE Audio SET filename=?, filepath=?, date=? WHERE filename=?',
                (new_name, new_path, new_date, old_name),
            )
        else:
            c.execute(
                'UPDATE Audio SET filename=?, filepath=? WHERE filename=?',
                (new_name, new_path, old_name),
            )
        updated += c.rowcount
    except Exception:
        db_errors += 1

conn.commit()
conn.close()
print(f"DB updated: {updated}, db_errors: {db_errors}")
