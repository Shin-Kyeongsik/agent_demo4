from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

import pandas as pd

from _card_common import (
    ensure_dir,
    ensure_normalized_transactions,
    run_subprocess,
    to_jsonable,
    write_json,
)


def money(value) -> str:
    try:
        return f"{int(float(value)):,}원"
    except Exception:
        return "0원"


def run_step(script_dir: Path, script_name: str, args: list[str], *, verbose: bool = False) -> None:
    command = [sys.executable, str(script_dir / script_name), *args]
    run_subprocess(command, verbose=verbose)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_review_markdown(
    findings: pd.DataFrame,
    findings_summary: dict,
    limit: int,
) -> str:
    lines = [
        "# Corporate Card Review Candidates",
        "",
        "## Summary",
        "",
        f"- Review candidates: {findings_summary.get('total_findings', 0):,}",
        "",
        "## Findings by Type",
        "",
        "| Finding Type | Count | Amount |",
        "| --- | ---: | ---: |",
    ]

    amount_by_type = findings_summary.get("amount_by_type", {})
    for finding_type, count in sorted(
        findings_summary.get("by_type", {}).items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        lines.append(
            f"| {finding_type} | {int(count):,} | {money(amount_by_type.get(finding_type, 0))} |"
        )

    lines += [
        "",
        "## Highest Priority Candidates",
        "",
        "| ID | Severity | Score | Type | Date | Department | Employee | Merchant | Amount | Tx IDs | Source Rows | Reason |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]

    if findings.empty:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | No candidates. |")
    else:
        for _, row in findings.head(limit).fillna("").iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("finding_id", "")),
                        str(row.get("severity", "")),
                        str(row.get("risk_score", "")),
                        str(row.get("finding_type", "")),
                        str(row.get("transaction_date", "")),
                        str(row.get("department", "")),
                        str(row.get("employee", "")),
                        str(row.get("merchant_normalized", "")),
                        money(row.get("total_amount", 0)),
                        str(row.get("transaction_ids", "")).replace("|", "/"),
                        str(row.get("source_row", "")).replace("|", "/"),
                        str(row.get("reason", "")).replace("|", "/"),
                    ]
                )
                + " |"
            )

    lines += [
        "",
        "## Review Guidance",
        "",
        "- Treat candidates as review targets, not confirmed policy violations.",
        "- Start with exact duplicate and split-payment candidates, then high-amount rows with missing or reapproval-related memos.",
        "- Use the `Tx IDs` and `Source Rows` columns above for audit tracing.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find and prioritize corporate card transactions that need review."
    )
    parser.add_argument("--input", help="Source file or directory. Used when --transactions is not supplied.")
    parser.add_argument("--transactions", help="Existing normalized_transactions.csv.")
    parser.add_argument(
        "--out",
        help="Optional output directory. If omitted, use a temporary directory and print the result to stdout.",
    )
    parser.add_argument("--sheet", help="Optional Excel sheet name when using --input.")
    parser.add_argument("--high-amount", type=int, default=1_500_000)
    parser.add_argument("--split-min-total", type=int, default=500_000)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--verbose", action="store_true", help="Print internal script progress.")
    args = parser.parse_args()

    context = (
        nullcontext(args.out)
        if args.out
        else tempfile.TemporaryDirectory(prefix="corporate-card-review-")
    )
    with context as work_dir:
        out_dir = ensure_dir(work_dir)
        script_dir = Path(__file__).resolve().parent
        transactions_path = ensure_normalized_transactions(
            out_dir=out_dir,
            input_path=args.input,
            transactions_path=args.transactions,
            sheet=args.sheet,
            verbose=args.verbose,
        )

        run_step(
            script_dir,
            "detect_findings.py",
            [
                "--transactions",
                str(transactions_path),
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
            [
                "--findings",
                str(out_dir / "findings.csv"),
                "--out",
                str(out_dir),
                "--top",
                str(args.top),
            ],
            verbose=args.verbose,
        )

        findings = pd.read_csv(out_dir / "prioritized_findings.csv", encoding="utf-8-sig")
        top_findings = findings.head(args.top).fillna("").to_dict(orient="records")
        findings_summary = {
            "source_transactions": str(transactions_path),
            "high_amount_threshold": int(args.high_amount),
            "split_min_total": int(args.split_min_total),
            "top_findings": top_findings,
            **load_json(out_dir / "findings_summary.json"),
        }
        markdown = render_review_markdown(findings, findings_summary, args.top)

        if args.out:
            write_json(out_dir / "review_findings_summary.json", findings_summary)
            (out_dir / "review_findings.md").write_text(markdown, encoding="utf-8")
            print(f"Wrote {out_dir / 'prioritized_findings.csv'}", file=sys.stderr)
            print(f"Wrote {out_dir / 'review_findings_summary.json'}", file=sys.stderr)
            print(f"Wrote {out_dir / 'review_findings.md'}", file=sys.stderr)

        if args.format == "json":
            print(json.dumps(to_jsonable(findings_summary), ensure_ascii=False, indent=2))
        else:
            print(markdown)


if __name__ == "__main__":
    main()
