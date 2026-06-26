from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

from _card_common import discover_input_files, ensure_dir, read_tables, to_jsonable, write_json


def profile_table(file_path: Path, sheet: str | None, frame) -> dict:
    preview = frame.head(5).fillna("").astype(str).to_dict(orient="records")
    return {
        "file": str(file_path),
        "sheet": sheet,
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        "null_counts": {
            str(column): int(count) for column, count in frame.isna().sum().items()
        },
        "preview": preview,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect corporate card source files and write an input profile."
    )
    parser.add_argument("--input", required=True, help="Source file or directory.")
    parser.add_argument(
        "--out",
        help="Optional output directory. If omitted, print the input profile JSON to stdout.",
    )
    parser.add_argument("--sheet", default=None, help="Optional Excel sheet name.")
    args = parser.parse_args()

    files = discover_input_files(args.input)
    if not files:
        raise SystemExit(f"No supported spreadsheet files found under {args.input}")

    tables = []
    for file_path in files:
        for table in read_tables(file_path, args.sheet):
            tables.append(profile_table(table["file"], table["sheet"], table["data"]))

    profile = {
        "input": str(Path(args.input)),
        "file_count": len(files),
        "table_count": len(tables),
        "total_rows": sum(table["rows"] for table in tables),
        "files": [str(file_path) for file_path in files],
        "tables": tables,
    }

    payload = to_jsonable(profile)
    if args.out:
        out_dir = ensure_dir(args.out)
        write_json(out_dir / "input_profile.json", payload)
        print(f"Wrote {out_dir / 'input_profile.json'}", file=sys.stderr)

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
