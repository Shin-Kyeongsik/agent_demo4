from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

import pandas as pd

from _card_common import (
    add_date_parts,
    ensure_dir,
    ensure_normalized_transactions,
    read_normalized_transactions,
    to_jsonable,
    write_csv,
    write_json,
)


def money(value) -> str:
    return f"{int(float(value)):,}원"


def percent(value) -> str:
    return f"{float(value):.1f}%"


def optional_date(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.to_datetime(value, errors="raise")


def apply_filters(
    df: pd.DataFrame,
    from_date: pd.Timestamp | None,
    to_date: pd.Timestamp | None,
) -> pd.DataFrame:
    result = df
    if from_date is not None:
        result = result[result["transaction_date"] >= from_date]
    if to_date is not None:
        result = result[result["transaction_date"] <= to_date]
    return result


def department_summary(df: pd.DataFrame, high_amount: int) -> pd.DataFrame:
    total_amount = max(float(df["amount"].sum()), 1.0)
    df = df.copy()
    df["memo_missing_bool"] = df["memo_missing"].astype(str).str.lower().eq("true")
    df["high_amount_bool"] = df["amount"] >= high_amount

    grouped = df.groupby("department", dropna=False)
    summary = grouped.agg(
        transaction_count=("transaction_id", "count"),
        total_amount=("amount", "sum"),
        average_amount=("amount", "mean"),
        median_amount=("amount", "median"),
        max_amount=("amount", "max"),
        employee_count=("employee", "nunique"),
        merchant_count=("merchant_normalized", "nunique"),
        missing_memo_count=("memo_missing_bool", "sum"),
        weekend_count=("is_weekend", "sum"),
        high_amount_count=("high_amount_bool", "sum"),
    ).reset_index()

    amount_by_flag = df.assign(
        missing_memo_amount=df["amount"].where(df["memo_missing_bool"], 0),
        weekend_amount=df["amount"].where(df["is_weekend"], 0),
        high_amount_amount=df["amount"].where(df["high_amount_bool"], 0),
    )
    amount_summary = amount_by_flag.groupby("department", dropna=False).agg(
        missing_memo_amount=("missing_memo_amount", "sum"),
        weekend_amount=("weekend_amount", "sum"),
        high_amount_amount=("high_amount_amount", "sum"),
    ).reset_index()

    summary = summary.merge(amount_summary, on="department", how="left")
    summary["share_of_total_pct"] = summary["total_amount"] / total_amount * 100

    numeric_int_cols = [
        "transaction_count",
        "total_amount",
        "average_amount",
        "median_amount",
        "max_amount",
        "employee_count",
        "merchant_count",
        "missing_memo_count",
        "weekend_count",
        "high_amount_count",
        "missing_memo_amount",
        "weekend_amount",
        "high_amount_amount",
    ]
    for column in numeric_int_cols:
        summary[column] = summary[column].fillna(0).round(0).astype(int)
    summary["share_of_total_pct"] = summary["share_of_total_pct"].round(2)

    return summary.sort_values(
        ["total_amount", "transaction_count"], ascending=[False, False]
    )


def render_department_markdown(summary: pd.DataFrame, metadata: dict, limit: int) -> str:
    lines = [
        "# Department Corporate Card Summary",
        "",
        "## Scope",
        "",
        f"- Period: {metadata['date_min']} to {metadata['date_max']}",
        f"- Transactions: {metadata['transaction_count']:,}",
        f"- Total amount: {money(metadata['total_amount'])}",
        f"- Departments: {metadata['department_count']:,}",
        "",
        "## Department Summary",
        "",
        "| Department | Count | Total | Average | Share | Missing Memo | Weekend | High Amount |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.head(limit).iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["department"]),
                    f"{int(row['transaction_count']):,}",
                    money(row["total_amount"]),
                    money(row["average_amount"]),
                    percent(row["share_of_total_pct"]),
                    f"{int(row['missing_memo_count']):,}",
                    f"{int(row['weekend_count']):,}",
                    f"{int(row['high_amount_count']):,}",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Return department-level corporate card totals, counts, and averages."
    )
    parser.add_argument("--input", help="Source file or directory. Used when --transactions is not supplied.")
    parser.add_argument("--transactions", help="Existing normalized_transactions.csv.")
    parser.add_argument(
        "--out",
        help="Optional output directory. If omitted, use a temporary directory and print the result to stdout.",
    )
    parser.add_argument("--sheet", help="Optional Excel sheet name when using --input.")
    parser.add_argument("--from-date", help="Inclusive YYYY-MM-DD start date.")
    parser.add_argument("--to-date", help="Inclusive YYYY-MM-DD end date.")
    parser.add_argument("--high-amount", type=int, default=1_500_000)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--verbose", action="store_true", help="Print internal script progress.")
    args = parser.parse_args()

    context = (
        nullcontext(args.out)
        if args.out
        else tempfile.TemporaryDirectory(prefix="corporate-card-departments-")
    )
    with context as work_dir:
        out_dir = ensure_dir(work_dir)
        transactions_path = ensure_normalized_transactions(
            out_dir=out_dir,
            input_path=args.input,
            transactions_path=args.transactions,
            sheet=args.sheet,
            verbose=args.verbose,
        )
        df = add_date_parts(read_normalized_transactions(transactions_path))
        df = apply_filters(df, optional_date(args.from_date), optional_date(args.to_date))
        if df.empty:
            raise SystemExit("No transactions remain after filtering.")

        summary = department_summary(df, args.high_amount)

        metadata = {
            "source_transactions": str(transactions_path),
            "date_min": str(df["transaction_date"].min().date()),
            "date_max": str(df["transaction_date"].max().date()),
            "transaction_count": int(len(df)),
            "total_amount": int(df["amount"].sum()),
            "department_count": int(df["department"].nunique()),
            "high_amount_threshold": int(args.high_amount),
            "top_departments": summary.head(args.limit).to_dict(orient="records"),
        }
        markdown = render_department_markdown(summary, metadata, args.limit)

        if args.out:
            write_csv(summary, out_dir / "department_summary.csv")
            write_json(out_dir / "department_summary.json", metadata)
            (out_dir / "department_summary.md").write_text(markdown, encoding="utf-8")
            print(f"Wrote {out_dir / 'department_summary.csv'}", file=sys.stderr)
            print(f"Wrote {out_dir / 'department_summary.json'}", file=sys.stderr)
            print(f"Wrote {out_dir / 'department_summary.md'}", file=sys.stderr)

        if args.format == "json":
            print(json.dumps(to_jsonable(metadata), ensure_ascii=False, indent=2))
        else:
            print(markdown)


if __name__ == "__main__":
    main()
