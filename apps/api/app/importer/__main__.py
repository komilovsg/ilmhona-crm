"""`python -m app.importer <snapshot.json> --dry-run | --apply [--out-dir DIR]`"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from app.core.db import engine, sessionmaker
from app.importer import run_import


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.importer", description=__doc__)
    ap.add_argument("snapshot", type=Path, help="import-data/sheets-YYYYMMDD.json")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="run, roll back, write the report")
    mode.add_argument("--apply", action="store_true", help="run and commit, in one transaction")
    ap.add_argument(
        "--out-dir", type=Path, help="where the report goes (default: next to the file)"
    )
    args = ap.parse_args(argv)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    out_dir = args.out_dir or args.snapshot.resolve().parent
    async with sessionmaker() as db:
        report = await run_import(db, snapshot, apply=args.apply, source=args.snapshot.name)
    await engine.dispose()
    md, xlsx = report.write(out_dir, datetime.now().strftime("%Y%m%d-%H%M%S"))
    print(f"{report.mode}: report {md}\nreview list {xlsx}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
