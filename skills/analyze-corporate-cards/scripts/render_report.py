from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from _card_common import ensure_dir


def money(value) -> str:
    try:
        return f"{int(float(value)):,}원"
    except Exception:
        return "0원"


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def markdown_table(rows: list[dict], columns: list[tuple[str, str]], limit: int = 10) -> str:
    if not rows:
        return "_No rows._"
    selected = rows[:limit]
    header = "| " + " | ".join(title for title, _ in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in selected:
        values = []
        for _, key in columns:
            value = row.get(key, "")
            if key in {"sum", "amount", "total_amount", "max", "mean", "median"}:
                value = money(value)
            values.append(str(value).replace("\n", " "))
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, divider] + body)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a compact Markdown report from corporate card analysis outputs."
    )
    parser.add_argument("--summary", required=True, help="summary.json")
    parser.add_argument("--findings-summary", required=True, help="findings_summary.json")
    parser.add_argument("--prioritized-findings", required=True, help="prioritized_findings.csv")
    parser.add_argument("--out", required=True, help="Output directory.")
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    out_dir = ensure_dir(args.out)
    summary = load_json(args.summary)
    findings_summary = load_json(args.findings_summary)
    findings = pd.read_csv(args.prioritized_findings, encoding="utf-8-sig")

    lines = [
        "# Corporate Card Spending Analysis",
        "",
        "## Scope",
        "",
        f"- Period: {summary.get('date_min')} to {summary.get('date_max')}",
        f"- Transactions: {summary.get('rows'):,}",
        f"- Total amount: {money(summary.get('amount', {}).get('sum', 0))}",
        f"- Average amount: {money(summary.get('amount', {}).get('mean', 0))}",
        f"- P95 amount: {money(summary.get('amount', {}).get('p95', 0))}",
        f"- Departments / employees / merchants: {summary.get('department_count')} / {summary.get('employee_count')} / {summary.get('merchant_count')}",
        "",
        "## Key Control Signals",
        "",
        f"- Missing memo: {summary.get('memo_missing', {}).get('count', 0):,} transactions, {money(summary.get('memo_missing', {}).get('amount', 0))}",
        f"- Weekend use: {summary.get('weekend', {}).get('count', 0):,} transactions, {money(summary.get('weekend', {}).get('amount', 0))}",
        f"- Review candidates: {findings_summary.get('total_findings', 0):,}",
        "",
        "## Top Departments",
        "",
        markdown_table(
            summary.get("top", {}).get("by_department", []),
            [("Department", "department"), ("Count", "count"), ("Amount", "sum"), ("Max", "max")],
            8,
        ),
        "",
        "## Top Employees",
        "",
        markdown_table(
            summary.get("top", {}).get("by_employee", []),
            [("Department", "department"), ("Employee", "employee"), ("Count", "count"), ("Amount", "sum"), ("Max", "max")],
            10,
        ),
        "",
        "## Top Merchants",
        "",
        markdown_table(
            summary.get("top", {}).get("by_merchant", []),
            [("Merchant", "merchant_normalized"), ("Count", "count"), ("Amount", "sum"), ("Max", "max")],
            10,
        ),
        "",
        "## Findings by Type",
        "",
    ]

    by_type = findings_summary.get("by_type", {})
    amount_by_type = findings_summary.get("amount_by_type", {})
    type_rows = [
        {
            "finding_type": finding_type,
            "count": count,
            "total_amount": amount_by_type.get(finding_type, 0),
        }
        for finding_type, count in sorted(by_type.items(), key=lambda item: item[1], reverse=True)
    ]
    lines.append(
        markdown_table(
            type_rows,
            [("Finding Type", "finding_type"), ("Count", "count"), ("Amount", "total_amount")],
            20,
        )
    )

    lines += [
        "",
        "## Highest Priority Findings",
        "",
    ]

    if findings.empty:
        lines.append("_No findings._")
    else:
        top = findings.head(args.top).fillna("").to_dict(orient="records")
        lines.append(
            markdown_table(
                top,
                [
                    ("ID", "finding_id"),
                    ("Severity", "severity"),
                    ("Score", "risk_score"),
                    ("Type", "finding_type"),
                    ("Date", "transaction_date"),
                    ("Department", "department"),
                    ("Employee", "employee"),
                    ("Merchant", "merchant_normalized"),
                    ("Amount", "total_amount"),
                    ("Reason", "reason"),
                ],
                args.top,
            )
        )

    lines += [
        "",
        "## Review Guidance",
        "",
        "- Treat findings as review candidates, not final policy violations.",
        "- Start with exact duplicates, split payment candidates, and high amount items with missing or reapproval-related memos.",
        "- For vendor alias groups, confirm whether raw merchant names should be merged before month-over-month reporting.",
    ]

    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
