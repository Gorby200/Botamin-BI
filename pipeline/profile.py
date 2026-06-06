"""Data profiling: schema, types, distributions, anomalies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd
import numpy as np


@dataclass
class Profile:
    total_rows: int = 0
    columns: list[str] = field(default_factory=list)
    types: dict[str, str] = field(default_factory=dict)
    duplicates_by_phone: int = 0
    status_distribution: dict[str, int] = field(default_factory=dict)
    end_reason_distribution: dict[str, int] = field(default_factory=dict)
    empty_dialogue_share: float = 0.0
    duration_stats: dict = field(default_factory=dict)
    hour_distribution: dict[int, int] = field(default_factory=dict)
    dow_distribution: dict[int, int] = field(default_factory=dict)
    date_range: tuple[str | None, str | None] = (None, None)
    anomalies: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def parse_duration_seconds(raw: pd.Series) -> pd.Series:
    """Parse 'MM:SS' or 'HH:MM:SS' duration strings to seconds."""
    def _to_sec(val: str) -> float | None:
        if not val or pd.isna(val):
            return None
        val = str(val).strip()
        # Try MM:SS
        m = re.match(r"^(\d+):(\d{1,2})$", val)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        # Try HH:MM:SS
        m = re.match(r"^(\d+):(\d{1,2}):(\d{1,2})$", val)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        # Try plain number (seconds)
        try:
            return float(val)
        except ValueError:
            return None

    return raw.apply(_to_sec)


def profile_data(df: pd.DataFrame) -> Profile:
    """Profile the dataset and return summary statistics."""
    p = Profile()
    p.total_rows = len(df)
    p.columns = list(df.columns)

    # --- Types ---
    for col in df.columns:
        sample = df[col].dropna().head(100)
        if len(sample) == 0:
            p.types[col] = "empty"
        elif sample.str.match(r"^\d{1,2}:\d{2}(:\d{2})?$").all():
            p.types[col] = "duration"
        else:
            p.types[col] = "string"

    # --- Duplicates by phone ---
    if "phone" in df.columns:
        p.duplicates_by_phone = int(df["phone"].dropna().duplicated().sum())

    # --- Status distribution ---
    if "status" in df.columns:
        p.status_distribution = df["status"].fillna("(empty)").value_counts().to_dict()
        # Convert int keys
        p.status_distribution = {str(k): int(v) for k, v in p.status_distribution.items()}

    # --- End reason distribution ---
    if "end_reason" in df.columns:
        p.end_reason_distribution = df["end_reason"].fillna("(empty)").value_counts().to_dict()
        p.end_reason_distribution = {str(k): int(v) for k, v in p.end_reason_distribution.items()}

    # --- Empty dialogue share ---
    if "dialogue" in df.columns:
        empty_mask = df["dialogue"].isna() | (df["dialogue"].str.strip() == "")
        p.empty_dialogue_share = round(float(empty_mask.mean()), 4)

    # --- Duration stats ---
    if "duration_raw" in df.columns:
        secs = parse_duration_seconds(df["duration_raw"])
        valid = secs.dropna()
        if len(valid) > 0:
            p.duration_stats = {
                "count": int(len(valid)),
                "mean_sec": round(float(valid.mean()), 1),
                "median_sec": round(float(valid.median()), 1),
                "p25_sec": round(float(valid.quantile(0.25)), 1),
                "p75_sec": round(float(valid.quantile(0.75)), 1),
                "min_sec": round(float(valid.min()), 1),
                "max_sec": round(float(valid.max()), 1),
            }

    # --- Datetime distribution ---
    if "datetime" in df.columns:
        dt = pd.to_datetime(df["datetime"], errors="coerce", format="mixed")
        valid_dt = dt.dropna()
        if len(valid_dt) > 0:
            p.date_range = (
                str(valid_dt.min().date()),
                str(valid_dt.max().date()),
            )
            p.hour_distribution = (
                valid_dt.dt.hour.value_counts().sort_index().to_dict()
            )
            p.hour_distribution = {int(k): int(v) for k, v in p.hour_distribution.items()}
            p.dow_distribution = (
                valid_dt.dt.dayofweek.value_counts().sort_index().to_dict()
            )
            p.dow_distribution = {int(k): int(v) for k, v in p.dow_distribution.items()}

    # --- Anomalies ---
    if "duration_raw" in df.columns:
        secs = parse_duration_seconds(df["duration_raw"])
        very_short = (secs.fillna(0) < 3).sum()
        if very_short > 0:
            p.anomalies.append(f"{very_short} calls under 3 sec (likely non-conversations)")
        very_long = (secs.fillna(0) > 1800).sum()
        if very_long > 0:
            p.anomalies.append(f"{very_long} calls over 30 min")

    if p.duplicates_by_phone > 0:
        p.anomalies.append(f"{p.duplicates_by_phone} duplicate phone numbers")

    return p
