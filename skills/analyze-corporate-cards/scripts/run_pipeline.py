from __future__ import annotations

import argparse
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

from _card_common import ensure_dir, run_subprocess


def run_step(script_dir: Path, script_name: str, args: list[str], *, verbose: bool = False) -> None:
    command = [sys.executable, str(script_dir / script_name), *args]
    run_subprocess(command, verbose=verbose)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the staged corporate card analysis pipeline."
    )
    parser.add_argument("--input", required=True, help="Source file or directory.")
    parser.add_argument(
        "--out",
        help="Optional output directory. If omitted, use a temporary directory and print the report to stdout.",
    )
    parser.add_argument("--sheet", default=None, help="Optional Excel sheet name.")
    parser.add_argument("--high-amount", type=int, default=1_500_000)
    parser.add_argument("--split-min-total", type=int, default=500_000)
    parser.add_argument("--verbose", action="store_true", help="Print internal script progress.")
    args = parser.parse_args()

    context = (
        nullcontext(args.out)
        if args.out
        else tempfile.TemporaryDirectory(prefix="corporate-card-analysis-")
    )
    with context as work_dir:
        out_dir = ensure_dir(work_dir)
        script_dir = Path(__file__).resolve().parent
        sheet_args = ["--sheet", args.sheet] if args.sheet else []

        run_step(
            script_dir,
            "inspect_input.py",
            ["--input", args.input, "--out", str(out_dir), *sheet_args],
            verbose=args.verbose,
        )
        run_step(
            script_dir,
            "normalize_transactions.py",
            ["--input", args.input, "--out", str(out_dir), *sheet_args],
            verbose=args.verbose,
        )
        run_step(
            script_dir,
            "summarize_usage.py",
            ["--transactions", str(out_dir / "normalized_transactions.csv"), "--out", str(out_dir)],
            verbose=args.verbose,
        )
        run_step(
            script_dir,
            "detect_findings.py",
            [
                "--transactions",
                str(out_dir / "normalized_transactions.csv"),
                "--out",
                str(out_dir),
                "--high-amount",
                str(args.high_amount),
                "--split-min-total",
                str(args.split_min_total),
            ],
            verbose=args.verbose,
        )
        run_step(
            script_dir,
            "score_findings.py",
            ["--findings", str(out_dir / "findings.csv"), "--out", str(out_dir)],
            verbose=args.verbose,
        )
        run_step(
            script_dir,
            "render_report.py",
            [
                "--summary",
                str(out_dir / "summary.json"),
                "--findings-summary",
                str(out_dir / "findings_summary.json"),
                "--prioritized-findings",
                str(out_dir / "prioritized_findings.csv"),
                "--out",
                str(out_dir),
            ],
            verbose=args.verbose,
        )
        if args.out:
            print(
                f"Done. Saved {out_dir / 'report.md'} and {out_dir / 'prioritized_findings.csv'}.",
                file=sys.stderr,
            )
        print((out_dir / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
