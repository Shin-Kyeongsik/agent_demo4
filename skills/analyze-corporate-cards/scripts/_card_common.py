from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".csv", ".tsv"}


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


def discover_input_files(input_path: str | Path) -> list[Path]:
    path = Path(input_path)
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_SUFFIXES else []
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    files = [
        file
        for file in path.rglob("*")
        if file.is_file()
        and file.suffix.lower() in SUPPORTED_SUFFIXES
        and not file.name.startswith(("~$", "."))
    ]
    return sorted(files)


def read_tables(file_path: str | Path, sheet_name: str | None = None) -> list[dict[str, Any]]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        frame = read_delimited(path, sep)
        return [{"file": path, "sheet": None, "data": frame}]

    if suffix in {".xlsx", ".xls"}:
        excel = pd.ExcelFile(path)
        sheets = [sheet_name] if sheet_name else excel.sheet_names
        tables = []
        for sheet in sheets:
            frame = pd.read_excel(path, sheet_name=sheet)
            if not frame.empty:
                tables.append({"file": path, "sheet": sheet, "data": frame})
        return tables

    raise ValueError(f"Unsupported file type: {path.suffix}")


def read_delimited(path: Path, sep: str) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(path, sep=sep, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, sep=sep)


def normalize_key(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    text = text.strip().lower()
    return re.sub(r"[\s_\-./()]+", "", text)


def compact_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_amount(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("원", "", regex=False)
        .str.replace(r"[^0-9.\-]", "", regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def read_normalized_transactions(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "transaction_date" in df.columns:
        df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def ensure_normalized_transactions(
    *,
    out_dir: str | Path,
    input_path: str | Path | None = None,
    transactions_path: str | Path | None = None,
    sheet: str | None = None,
    verbose: bool = False,
) -> Path:
    if transactions_path:
        path = Path(transactions_path)
        if not path.exists():
            raise FileNotFoundError(f"Normalized transaction file does not exist: {path}")
        return path

    if not input_path:
        raise ValueError("Provide either --input or --transactions.")

    out_path = ensure_dir(out_dir)
    normalized_path = out_path / "normalized_transactions.csv"
    script_dir = Path(__file__).resolve().parent
    command = [
        sys.executable,
        str(script_dir / "normalize_transactions.py"),
        "--input",
        str(input_path),
        "--out",
        str(out_path),
    ]
    if sheet:
        command.extend(["--sheet", sheet])
    run_subprocess(command, verbose=verbose)
    return normalized_path


def add_date_parts(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["transaction_date"] = pd.to_datetime(result["transaction_date"], errors="coerce")
    result["month"] = result["transaction_date"].dt.to_period("M").astype(str)
    result["weekday"] = result["transaction_date"].dt.day_name()
    result["is_weekend"] = result["transaction_date"].dt.dayofweek >= 5
    return result


def run_subprocess(command: list[str], *, verbose: bool = False) -> None:
    if verbose:
        print("Running:", " ".join(command), file=sys.stderr, flush=True)
        subprocess.run(command, check=True)
        return

    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
