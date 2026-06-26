from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from _card_common import (
    compact_text,
    discover_input_files,
    ensure_dir,
    normalize_key,
    parse_amount,
    read_tables,
    write_csv,
    write_json,
)


COLUMN_ALIASES = {
    "transaction_id": ["거래ID", "거래번호", "승인번호", "transaction_id", "id"],
    "transaction_date": ["거래일자", "사용일자", "승인일자", "date", "transaction_date"],
    "department": ["부서", "소속", "department", "team"],
    "employee": ["사용자", "사용자명", "사원명", "employee", "user", "cardholder"],
    "rank": ["직급", "직위", "rank", "title"],
    "merchant": ["거래처", "가맹점", "사용처", "merchant", "vendor"],
    "description": ["거래내용", "사용내역", "내용", "description", "purpose"],
    "amount": ["금액", "사용금액", "승인금액", "amount"],
    "payment_method": ["결제수단", "카드구분", "payment_method"],
    "memo": ["메모", "비고", "적요", "memo", "note"],
}

MERCHANT_ALIASES = {
    "cloudbox": "CloudBox",
    "클라우드박스": "CloudBox",
    "korail": "KORAIL",
    "코레일": "KORAIL",
    "ktx예약센터": "KORAIL",
    "별빛coffee": "별빛커피",
    "별빛커피": "별빛커피",
    "한빛식당본점": "한빛식당",
}


def find_column(frame: pd.DataFrame, aliases: list[str]) -> str | None:
    direct = {str(column): column for column in frame.columns}
    for alias in aliases:
        if alias in direct:
            return direct[alias]
    normalized = {normalize_key(column): column for column in frame.columns}
    for alias in aliases:
        key = normalize_key(alias)
        if key in normalized:
            return normalized[key]
    return None


def merchant_canonical(value: str) -> str:
    key = normalize_key(value)
    if key in MERCHANT_ALIASES:
        return MERCHANT_ALIASES[key]
    return compact_text(value)


def categorize_transaction(description: str, merchant: str) -> str:
    text = f"{description} {merchant}".lower()
    if any(keyword in text for keyword in ["숙박", "호텔", "리조트", "출장", "택시", "교통", "열차", "주차", "korail", "ktx"]):
        return "travel"
    if any(keyword in text for keyword in ["식대", "식사", "다과", "커피", "음료", "도시락", "분식", "한식"]):
        return "meals"
    if any(keyword in text for keyword in ["클라우드", "협업툴", "솔루션", "보안", "saas", "라이선스", "구독", "데이터 분석 도구"]):
        return "software"
    if any(keyword in text for keyword in ["교육", "세미나", "컨퍼런스", "리더십", "직무"]):
        return "education"
    if any(keyword in text for keyword in ["인쇄", "배너", "리플렛", "홍보물", "출력", "제작", "디자인"]):
        return "marketing_print"
    if any(keyword in text for keyword in ["문구", "사무", "복사용지", "토너", "파일철"]):
        return "office_supplies"
    return "other"


def normalize_frame(file_path: Path, sheet: str | None, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    mapping = {
        standard: find_column(frame, aliases)
        for standard, aliases in COLUMN_ALIASES.items()
    }
    required = ["transaction_date", "amount"]
    missing_required = [name for name in required if mapping.get(name) is None]
    if missing_required:
        raise ValueError(
            f"{file_path} {sheet or ''}: missing required columns {missing_required}"
        )

    output = pd.DataFrame()
    for standard in COLUMN_ALIASES:
        source = mapping.get(standard)
        if source is not None:
            output[standard] = frame[source]
        else:
            output[standard] = ""

    if mapping.get("transaction_id") is None:
        stem = file_path.stem
        sheet_part = sheet or "sheet"
        output["transaction_id"] = [
            f"{stem}-{sheet_part}-{index + 2}" for index in range(len(frame))
        ]

    output["transaction_date"] = pd.to_datetime(
        output["transaction_date"], errors="coerce"
    ).dt.date
    output["amount"] = parse_amount(output["amount"]).fillna(0).round(0).astype(int)

    for column in [
        "transaction_id",
        "department",
        "employee",
        "rank",
        "merchant",
        "description",
        "payment_method",
        "memo",
    ]:
        output[column] = output[column].map(compact_text)

    output["merchant_normalized"] = output["merchant"].map(merchant_canonical)
    output["content_category"] = [
        categorize_transaction(description, merchant)
        for description, merchant in zip(output["description"], output["merchant_normalized"])
    ]
    output["memo_missing"] = output["memo"].eq("")
    output["source_file"] = str(file_path)
    output["source_sheet"] = sheet or ""
    output["source_row"] = [index + 2 for index in range(len(frame))]

    output = output[output["transaction_date"].notna()].copy()
    output = output[output["amount"].notna()].copy()

    report = {
        "file": str(file_path),
        "sheet": sheet,
        "rows_in": int(len(frame)),
        "rows_out": int(len(output)),
        "column_mapping": {
            key: str(value) if value is not None else None for key, value in mapping.items()
        },
        "missing_optional_columns": [
            key for key, value in mapping.items() if value is None and key not in required
        ],
    }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize corporate card transaction files into a standard schema."
    )
    parser.add_argument("--input", required=True, help="Source file or directory.")
    parser.add_argument("--out", required=True, help="Output directory.")
    parser.add_argument("--sheet", default=None, help="Optional Excel sheet name.")
    args = parser.parse_args()

    out_dir = ensure_dir(args.out)
    files = discover_input_files(args.input)
    if not files:
        raise SystemExit(f"No supported spreadsheet files found under {args.input}")

    normalized_frames = []
    reports = []
    for file_path in files:
        for table in read_tables(file_path, args.sheet):
            normalized, report = normalize_frame(table["file"], table["sheet"], table["data"])
            normalized_frames.append(normalized)
            reports.append(report)

    if not normalized_frames:
        raise SystemExit("No transaction rows could be normalized.")

    transactions = pd.concat(normalized_frames, ignore_index=True)
    transactions = transactions.sort_values(
        ["transaction_date", "department", "employee", "transaction_id"]
    )
    write_csv(transactions, out_dir / "normalized_transactions.csv")

    normalization_report = {
        "input": str(Path(args.input)),
        "rows": int(len(transactions)),
        "files": len(files),
        "tables": len(reports),
        "date_min": str(transactions["transaction_date"].min()),
        "date_max": str(transactions["transaction_date"].max()),
        "total_amount": int(transactions["amount"].sum()),
        "reports": reports,
        "merchant_alias_groups": find_merchant_alias_groups(transactions),
    }
    write_json(out_dir / "normalization_report.json", normalization_report)
    print(f"Wrote {out_dir / 'normalized_transactions.csv'}")
    print(f"Wrote {out_dir / 'normalization_report.json'}")


def find_merchant_alias_groups(transactions: pd.DataFrame) -> list[dict]:
    groups = []
    for normalized, group in transactions.groupby("merchant_normalized", dropna=False):
        raw_names = sorted({name for name in group["merchant"].astype(str) if name})
        if len(raw_names) > 1:
            groups.append(
                {
                    "merchant_normalized": normalized,
                    "raw_names": raw_names,
                    "count": int(len(group)),
                    "amount": int(group["amount"].sum()),
                }
            )
    return sorted(groups, key=lambda item: item["amount"], reverse=True)


if __name__ == "__main__":
    main()
