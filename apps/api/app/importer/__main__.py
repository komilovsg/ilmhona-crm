"""`python -m app.importer <snapshot.json> --dry-run | --apply [--out-dir DIR] [--confirm-db NAME]`

With ENV=production `--apply` runs only with `--confirm-db` = the name of the database it writes to.
A failure prints the error type and place only: the rows hold personal data, so no message, value
or SQL parameter goes to the terminal or a log."""

import argparse
import asyncio
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.db import engine, sessionmaker
from app.importer import run_import

# the gitignored `import-data/` at the repo root (apps/api/app/importer -> repo)
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[4] / "import-data"


def _where(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)
    return f" at {Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else ""


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.importer", description=__doc__)
    ap.add_argument("snapshot", type=Path, help="import-data/sheets-YYYYMMDD.json")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="run, roll back, write the report")
    mode.add_argument("--apply", action="store_true", help="run and commit, in one transaction")
    ap.add_argument(
        "--out-dir", type=Path, help=f"where the report goes (default: {DEFAULT_OUT_DIR})"
    )
    ap.add_argument(
        "--confirm-db", help="ENV=production: --apply needs the target database name typed here"
    )
    args = ap.parse_args(argv)
    if args.apply and settings.env == "production":
        target = make_url(settings.database_url).database
        if args.confirm_db != target:
            print(
                "production: --apply needs --confirm-db <name of the target database>",
                file=sys.stderr,
            )
            return 2
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        async with sessionmaker() as db:
            report = await run_import(db, snapshot, apply=args.apply, source=args.snapshot.name)
        md, xlsx = report.write(
            args.out_dir or DEFAULT_OUT_DIR, datetime.now().strftime("%Y%m%d-%H%M%S")
        )
    except Exception as exc:  # noqa: BLE001 - the message may quote a row
        print(f"import failed: {type(exc).__name__}{_where(exc)}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(f"{report.mode}: report {md}\nreview list {xlsx}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
