"""Data ingestion: Google Sheets CSV export or local file."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pandas as pd


# ---------------------------------------------------------------------------
# Column name normalisation (Russian headers with spaces/case variations)
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {
    "телефон": "phone",
    "телефон ": "phone",
    "phone": "phone",
    "дата и время": "datetime",
    "дата_и_время": "datetime",
    "дата": "datetime",
    "datetime": "datetime",
    "длительность мин:сек": "duration_raw",
    "длительность": "duration_raw",
    "duration": "duration_raw",
    "длительность мин": "duration_raw",
    "статус": "status",
    "status": "status",
    "запись аудио": "audio_url",
    "запись_аудио": "audio_url",
    "аудио": "audio_url",
    "audio": "audio_url",
    "audio_url": "audio_url",
    "причина завершения": "end_reason",
    "причина_завершения": "end_reason",
    "end_reason": "end_reason",
    "история диалога юзер-бот": "dialogue",
    "история_диалога": "dialogue",
    "диалог": "dialogue",
    "dialogue": "dialogue",
    "транскрипт": "dialogue",
    "transcript": "dialogue",
}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map Russian/varied column names to canonical English names."""
    new_cols = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in COLUMN_MAP:
            new_cols[col] = COLUMN_MAP[key]
        # also try without special chars
        elif re.sub(r"[\s_]+", " ", key) in COLUMN_MAP:
            new_cols[col] = COLUMN_MAP[re.sub(r"[\s_]+", " ", key)]
        else:
            new_cols[col] = col  # keep as-is
    return df.rename(columns=new_cols)


def _parse_sheet_url(url: str) -> tuple[str, str]:
    """Extract sheet ID and GID from Google Sheets URL."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError(f"Cannot extract sheet ID from URL: {url}")
    sheet_id = m.group(1)

    gid_m = re.search(r"[#?&]gid=(\d+)", url)
    gid = gid_m.group(1) if gid_m else "0"
    return sheet_id, gid


def ingest_sheet(url: str, gid: int | None = None, cache_path: Path | None = None) -> pd.DataFrame:
    """Download Google Sheet as CSV via public export link."""
    sheet_id, default_gid = _parse_sheet_url(url)
    gid_str = str(gid) if gid is not None else default_gid

    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid_str}"

    content: bytes | None = None

    if cache_path and cache_path.exists():
        print(f"[ingest] Using cached file: {cache_path}")
        content = cache_path.read_bytes()
    else:
        print(f"[ingest] Downloading: {csv_url}")
        resp = httpx.get(csv_url, follow_redirects=True, timeout=60)
        resp.raise_for_status()
        content = resp.content
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(content)
            print(f"[ingest] Cached to: {cache_path}")

    # Try multiple encodings and CSV parsing options
    df = None
    for enc in ("utf-8", "utf-8-sig", "windows-1251", "cp1251", "latin-1"):
        try:
            text = content.decode(enc)
            df = pd.read_csv(pd.io.common.StringIO(text), dtype=str)
            print(f"[ingest] Decoded with {enc}, {len(df)} rows × {len(df.columns)} cols")
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except pd.errors.ParserError:
            # Try with different separators or error handling
            try:
                text = content.decode(enc)
                df = pd.read_csv(pd.io.common.StringIO(text), dtype=str, sep=",", on_bad_lines="skip")
                print(f"[ingest] Decoded with {enc} (skip bad lines), {len(df)} rows × {len(df.columns)} cols")
                break
            except Exception:
                continue
        except Exception:
            continue

    if df is None:
        raise ValueError("Cannot decode/parse CSV content with any tried encoding")

    df = _normalise_columns(df)
    return df


def ingest_file(path: Path) -> pd.DataFrame:
    """Load local CSV or XLSX file."""
    print(f"[ingest] Loading local file: {path}")
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
    elif suffix == ".csv":
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    else:
        raise ValueError(f"Unsupported file format: {suffix}")
    print(f"[ingest] Loaded {len(df)} rows × {len(df.columns)} cols")
    df = _normalise_columns(df)
    return df
