from __future__ import annotations

import argparse

import pandas as pd

from _card_common import ensure_dir, write_csv, write_json


BASE_SCORES = {
    "exact_duplicate_candidate": 78,
    "split_payment_candidate": 70,
    "reapproval_or_reprocess": 62,
    "high_amount": 58,
    "missing_memo": 35,
    "weekend_use": 38,
    "merchant_alias_group": 20,
}


def amount_bonus(amount: float) -> int:
    if amount >= 2_000_000:
        return 15
    if amount >= 1_500_000:
        return 12
    if amount >= 1_000_000:
        return 8
    if amount >= 500_000:
        return 5
    return 0


def severity(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def priority_reason(row: pd.Series, score: int) -> str:
    details = [str(row.get("reason", ""))]
    if pd.to_numeric(row.get("total_amount", 0), errors="coerce") >= 1_500_000:
        details.append("High total amount raises review priority.")
    if pd.to_numeric(row.get("transaction_count", 1), errors="coerce") > 1:
        details.append("Multiple related transactions raise review priority.")
    details.append(f"Priority score: {score}.")
    return " ".join(part for part in details if part)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score and prioritize corporate card findings."
    )
    parser.add_argument("--findings", required=True, help="findings.csv")
    parser.add_argument("--out", required=True, help="Output directory.")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args()

    out_dir = ensure_dir(args.out)
    findings = pd.read_csv(args.findings, encoding="utf-8-sig")
    if findings.empty:
        write_csv(findings, out_dir / "prioritized_findings.csv")
        write_json(out_dir / "top_findings.json", {"top_findings": []})
        print(f"Wrote {out_dir / 'prioritized_findings.csv'}")
        return

    findings["total_amount_numeric"] = pd.to_numeric(
        findings["total_amount"], errors="coerce"
    ).fillna(0)
    findings["transaction_count_numeric"] = pd.to_numeric(
        findings["transaction_count"], errors="coerce"
    ).fillna(1)

    scores = []
    severities = []
    priority_reasons = []
    for _, row in findings.iterrows():
        score = BASE_SCORES.get(row["finding_type"], 25)
        score += amount_bonus(float(row["total_amount_numeric"]))
        if row["transaction_count_numeric"] > 1:
            score += 5
        score = min(int(score), 100)
        scores.append(score)
        severities.append(severity(score))
        priority_reasons.append(priority_reason(row, score))

    findings["risk_score"] = scores
    findings["severity"] = severities
    findings["priority_reason"] = priority_reasons

    prioritized = findings.sort_values(
        ["risk_score", "total_amount_numeric", "transaction_count_numeric"],
        ascending=[False, False, False],
    ).drop(columns=["total_amount_numeric", "transaction_count_numeric"])

    write_csv(prioritized, out_dir / "prioritized_findings.csv")
    top = prioritized.head(args.top).to_dict(orient="records")
    write_json(out_dir / "top_findings.json", {"top_findings": top})
    print(f"Wrote {out_dir / 'prioritized_findings.csv'}")
    print(f"Wrote {out_dir / 'top_findings.json'}")


if __name__ == "__main__":
    main()
