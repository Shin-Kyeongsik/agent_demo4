from __future__ import annotations

import argparse

import pandas as pd

from _card_common import ensure_dir, read_normalized_transactions, write_csv, write_json


def money_stats(amounts: pd.Series) -> dict:
    return {
        "count": int(amounts.count()),
        "sum": int(amounts.sum()),
        "mean": int(round(amounts.mean())) if len(amounts) else 0,
        "median": int(round(amounts.median())) if len(amounts) else 0,
        "p75": int(round(amounts.quantile(0.75))) if len(amounts) else 0,
        "p90": int(round(amounts.quantile(0.90))) if len(amounts) else 0,
        "p95": int(round(amounts.quantile(0.95))) if len(amounts) else 0,
        "p99": int(round(amounts.quantile(0.99))) if len(amounts) else 0,
        "max": int(amounts.max()) if len(amounts) else 0,
    }


def aggregate(df: pd.DataFrame, group_cols: list[str], limit: int = 30) -> pd.DataFrame:
    grouped = (
        df.groupby(group_cols, dropna=False)["amount"]
        .agg(["count", "sum", "mean", "median", "max"])
        .reset_index()
    )
    for column in ["sum", "mean", "median", "max"]:
        grouped[column] = grouped[column].round(0).astype(int)
    return grouped.sort_values(["sum", "count"], ascending=[False, False]).head(limit)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize normalized corporate card spending."
    )
    parser.add_argument("--transactions", required=True, help="normalized_transactions.csv")
    parser.add_argument("--out", required=True, help="Output directory.")
    args = parser.parse_args()

    out_dir = ensure_dir(args.out)
    aggregates_dir = ensure_dir(out_dir / "aggregates")
    df = read_normalized_transactions(args.transactions)
    df["weekday"] = df["transaction_date"].dt.day_name()
    df["is_weekend"] = df["transaction_date"].dt.dayofweek >= 5
    df["month"] = df["transaction_date"].dt.to_period("M").astype(str)

    aggregate_specs = {
        "by_month.csv": ["month"],
        "by_department.csv": ["department"],
        "by_employee.csv": ["department", "employee"],
        "by_rank.csv": ["rank"],
        "by_merchant.csv": ["merchant_normalized"],
        "by_description.csv": ["description"],
        "by_category.csv": ["content_category"],
        "by_date.csv": ["transaction_date"],
        "by_weekend.csv": ["is_weekend"],
    }

    top_tables = {}
    for file_name, group_cols in aggregate_specs.items():
        table = aggregate(df, group_cols)
        write_csv(table, aggregates_dir / file_name)
        top_tables[file_name.removesuffix(".csv")] = table.head(10).to_dict(orient="records")

    memo_missing = df["memo_missing"].astype(str).str.lower().eq("true")
    summary = {
        "rows": int(len(df)),
        "date_min": str(df["transaction_date"].min().date()),
        "date_max": str(df["transaction_date"].max().date()),
        "department_count": int(df["department"].nunique()),
        "employee_count": int(df["employee"].nunique()),
        "merchant_count": int(df["merchant_normalized"].nunique()),
        "description_count": int(df["description"].nunique()),
        "amount": money_stats(df["amount"]),
        "memo_missing": {
            "count": int(memo_missing.sum()),
            "amount": int(df.loc[memo_missing, "amount"].sum()),
        },
        "weekend": {
            "count": int(df["is_weekend"].sum()),
            "amount": int(df.loc[df["is_weekend"], "amount"].sum()),
        },
        "top": top_tables,
    }
    write_json(out_dir / "summary.json", summary)
    print(f"Wrote {out_dir / 'summary.json'}")
    print(f"Wrote aggregate tables under {aggregates_dir}")


if __name__ == "__main__":
    main()
