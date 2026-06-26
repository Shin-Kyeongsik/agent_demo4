from __future__ import annotations

import argparse
from collections import Counter

import pandas as pd

from _card_common import ensure_dir, read_normalized_transactions, write_csv, write_json


def amount_text(value: int | float) -> str:
    return f"{int(value):,}원"


def make_base(row: dict, finding_id: str, finding_type: str) -> dict:
    return {
        "finding_id": finding_id,
        "finding_type": finding_type,
        "severity": "",
        "risk_score": "",
        "transaction_ids": row.get("transaction_ids", ""),
        "transaction_count": row.get("transaction_count", 1),
        "transaction_date": row.get("transaction_date", ""),
        "department": row.get("department", ""),
        "employee": row.get("employee", ""),
        "rank": row.get("rank", ""),
        "merchant": row.get("merchant", ""),
        "merchant_normalized": row.get("merchant_normalized", ""),
        "description": row.get("description", ""),
        "amount": row.get("amount", ""),
        "total_amount": row.get("total_amount", row.get("amount", "")),
        "memo": row.get("memo", ""),
        "source_file": row.get("source_file", ""),
        "source_sheet": row.get("source_sheet", ""),
        "source_row": row.get("source_row", ""),
        "reason": row.get("reason", ""),
        "recommended_action": row.get("recommended_action", ""),
    }


def finding_counter():
    counter = {"value": 0}

    def next_id() -> str:
        counter["value"] += 1
        return f"F{counter['value']:04d}"

    return next_id


def add_transaction_finding(findings: list[dict], next_id, row, finding_type, reason, action):
    payload = row.to_dict()
    payload.update(
        {
            "transaction_ids": row["transaction_id"],
            "transaction_count": 1,
            "transaction_date": row.get("transaction_date_str", row.get("transaction_date", "")),
            "total_amount": int(row["amount"]),
            "reason": reason,
            "recommended_action": action,
        }
    )
    findings.append(make_base(payload, next_id(), finding_type))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect corporate card spending review candidates."
    )
    parser.add_argument("--transactions", required=True, help="normalized_transactions.csv")
    parser.add_argument("--out", required=True, help="Output directory.")
    parser.add_argument("--high-amount", type=int, default=1_500_000)
    parser.add_argument("--split-min-total", type=int, default=500_000)
    args = parser.parse_args()

    out_dir = ensure_dir(args.out)
    df = read_normalized_transactions(args.transactions)
    df["memo"] = df["memo"].fillna("").astype(str)
    df["merchant"] = df["merchant"].fillna("").astype(str)
    df["merchant_normalized"] = df["merchant_normalized"].fillna("").astype(str)
    df["transaction_date_str"] = df["transaction_date"].dt.strftime("%Y-%m-%d")
    df["is_weekend"] = df["transaction_date"].dt.dayofweek >= 5

    findings: list[dict] = []
    next_id = finding_counter()

    detect_exact_duplicates(df, findings, next_id)
    detect_split_candidates(df, findings, next_id, args.split_min_total)
    detect_high_amounts(df, findings, next_id, args.high_amount)
    detect_reapproval(df, findings, next_id)
    detect_missing_memo(df, findings, next_id)
    detect_weekend_use(df, findings, next_id)
    detect_merchant_aliases(df, findings, next_id)

    findings_df = pd.DataFrame(findings)
    if findings_df.empty:
        findings_df = pd.DataFrame(columns=list(make_base({}, "F0000", "").keys()))

    write_csv(findings_df, out_dir / "findings.csv")
    write_json(out_dir / "findings_summary.json", summarize_findings(findings_df))
    print(f"Wrote {out_dir / 'findings.csv'}")
    print(f"Wrote {out_dir / 'findings_summary.json'}")


def detect_exact_duplicates(df: pd.DataFrame, findings: list[dict], next_id) -> None:
    group_cols = [
        "transaction_date_str",
        "department",
        "employee",
        "merchant_normalized",
        "description",
        "amount",
    ]
    duplicate_groups = df.groupby(group_cols, dropna=False)
    for keys, group in duplicate_groups:
        if len(group) <= 1:
            continue
        sample = group.iloc[0]
        total = int(group["amount"].sum())
        reason = (
            "Same date, department, employee, merchant, description, and amount "
            f"appear {len(group)} times."
        )
        action = "Check whether these rows are duplicate approvals, reversals, or legitimate repeated purchases."
        payload = {
            "transaction_ids": ",".join(group["transaction_id"].astype(str)),
            "transaction_count": int(len(group)),
            "transaction_date": keys[0],
            "department": sample["department"],
            "employee": sample["employee"],
            "rank": sample["rank"],
            "merchant": ",".join(sorted(set(group["merchant"].astype(str)))),
            "merchant_normalized": sample["merchant_normalized"],
            "description": sample["description"],
            "amount": int(sample["amount"]),
            "total_amount": total,
            "memo": " | ".join(sorted(set(group["memo"].astype(str)))),
            "source_file": ",".join(sorted(set(group["source_file"].astype(str)))),
            "source_sheet": ",".join(sorted(set(group["source_sheet"].astype(str)))),
            "source_row": ",".join(group["source_row"].astype(str)),
            "reason": reason,
            "recommended_action": action,
        }
        findings.append(make_base(payload, next_id(), "exact_duplicate_candidate"))


def detect_split_candidates(
    df: pd.DataFrame, findings: list[dict], next_id, split_min_total: int
) -> None:
    group_cols = [
        "transaction_date_str",
        "department",
        "employee",
        "merchant_normalized",
        "description",
    ]
    for keys, group in df.groupby(group_cols, dropna=False):
        if len(group) <= 1:
            continue
        unique_amounts = group["amount"].nunique()
        total = int(group["amount"].sum())
        if unique_amounts <= 1 or total < split_min_total:
            continue
        sample = group.iloc[0]
        reason = (
            f"{len(group)} transactions to the same merchant and description on the same day "
            f"sum to {amount_text(total)} with different amounts."
        )
        action = "Check whether the purchases were intentionally split or represent separate approved expenses."
        payload = {
            "transaction_ids": ",".join(group["transaction_id"].astype(str)),
            "transaction_count": int(len(group)),
            "transaction_date": keys[0],
            "department": sample["department"],
            "employee": sample["employee"],
            "rank": sample["rank"],
            "merchant": ",".join(sorted(set(group["merchant"].astype(str)))),
            "merchant_normalized": sample["merchant_normalized"],
            "description": sample["description"],
            "amount": "",
            "total_amount": total,
            "memo": " | ".join(sorted(set(group["memo"].astype(str)))),
            "source_file": ",".join(sorted(set(group["source_file"].astype(str)))),
            "source_sheet": ",".join(sorted(set(group["source_sheet"].astype(str)))),
            "source_row": ",".join(group["source_row"].astype(str)),
            "reason": reason,
            "recommended_action": action,
        }
        findings.append(make_base(payload, next_id(), "split_payment_candidate"))


def detect_high_amounts(
    df: pd.DataFrame, findings: list[dict], next_id, high_amount: int
) -> None:
    threshold = max(high_amount, int(round(df["amount"].quantile(0.95))))
    for _, row in df[df["amount"] >= threshold].iterrows():
        add_transaction_finding(
            findings,
            next_id,
            row,
            "high_amount",
            f"Transaction amount is at or above the review threshold ({amount_text(threshold)}).",
            "Verify approval evidence, business purpose, and budget owner.",
        )


def detect_reapproval(df: pd.DataFrame, findings: list[dict], next_id) -> None:
    mask = df["memo"].str.contains("재승인|재처리|승인.*확인", regex=True, na=False)
    for _, row in df[mask].iterrows():
        add_transaction_finding(
            findings,
            next_id,
            row,
            "reapproval_or_reprocess",
            "Memo indicates reapproval or approval confirmation.",
            "Match this transaction to its original approval, cancellation, or correction record.",
        )


def detect_missing_memo(df: pd.DataFrame, findings: list[dict], next_id) -> None:
    mask = df["memo"].str.strip().eq("")
    for _, row in df[mask].iterrows():
        add_transaction_finding(
            findings,
            next_id,
            row,
            "missing_memo",
            "Memo is blank, so business purpose or evidence status is not visible in the source file.",
            "Request receipt, attendee list, approval note, or other supporting evidence.",
        )


def detect_weekend_use(df: pd.DataFrame, findings: list[dict], next_id) -> None:
    for _, row in df[df["is_weekend"]].iterrows():
        add_transaction_finding(
            findings,
            next_id,
            row,
            "weekend_use",
            "Transaction date falls on a weekend.",
            "Confirm whether the weekend purchase aligns with travel, event, or urgent business activity.",
        )


def detect_merchant_aliases(df: pd.DataFrame, findings: list[dict], next_id) -> None:
    for normalized, group in df.groupby("merchant_normalized", dropna=False):
        raw_names = sorted({name for name in group["merchant"].astype(str) if name})
        if len(raw_names) <= 1:
            continue
        payload = {
            "transaction_ids": ",".join(group["transaction_id"].astype(str).head(50)),
            "transaction_count": int(len(group)),
            "transaction_date": "",
            "department": "",
            "employee": "",
            "rank": "",
            "merchant": ",".join(raw_names),
            "merchant_normalized": normalized,
            "description": "",
            "amount": "",
            "total_amount": int(group["amount"].sum()),
            "memo": "",
            "source_file": ",".join(sorted(set(group["source_file"].astype(str)))),
            "source_sheet": ",".join(sorted(set(group["source_sheet"].astype(str)))),
            "source_row": "",
            "reason": f"Multiple raw merchant names map to '{normalized}'.",
            "recommended_action": "Confirm whether these merchant names should be treated as the same vendor in policy reporting.",
        }
        findings.append(make_base(payload, next_id(), "merchant_alias_group"))


def summarize_findings(findings_df: pd.DataFrame) -> dict:
    if findings_df.empty:
        return {"total_findings": 0, "by_type": {}, "amount_by_type": {}}
    counts = Counter(findings_df["finding_type"])
    amount_by_type = (
        findings_df.assign(total_amount_numeric=pd.to_numeric(findings_df["total_amount"], errors="coerce").fillna(0))
        .groupby("finding_type")["total_amount_numeric"]
        .sum()
        .astype(int)
        .to_dict()
    )
    return {
        "total_findings": int(len(findings_df)),
        "by_type": dict(counts),
        "amount_by_type": amount_by_type,
    }


if __name__ == "__main__":
    main()
