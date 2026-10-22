#!/usr/bin/env python3
import hashlib
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
SOURCE_FILE = PLUGIN_DIR / "plugin.js"
KEY = "glowpix"
API_VERSION = 1
VERSION = "1.0.0"


def run(dsn: str, sql: str) -> str:
    result = subprocess.run(
        ["docker", "exec", "-i", "data-plane_postgres_1", "psql", dsn, "-v", "ON_ERROR_STOP=1"],
        input=sql,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: python3 register_plugin.py "<SQL_DSN>"')
        sys.exit(1)
    dsn = sys.argv[1]

    source = SOURCE_FILE.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    now = int(time.time())
    escaped = source.replace("'", "''")

    sql = f"""
INSERT INTO task_plugins (key, api_version, version, source, source_hash, icon, enabled, active, created_at, remark)
VALUES ('{KEY}', {API_VERSION}, '{VERSION}', '{escaped}', '{source_hash}', '', true, true, {now}, 'GlowPix z-image-spicy image plugin')
ON CONFLICT (key, version) DO UPDATE
  SET source = EXCLUDED.source,
      source_hash = EXCLUDED.source_hash,
      enabled = true,
      active = true,
      remark = EXCLUDED.remark;
"""
    run(dsn, sql)
    print(f"OK  {KEY}@{VERSION} registered  hash={source_hash[:12]}")
    print(run(dsn, f"SELECT id, key, version, enabled, active, source_hash FROM task_plugins WHERE key='{KEY}';"))


if __name__ == "__main__":
    main()
