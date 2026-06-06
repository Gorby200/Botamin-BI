"""Botamin BI Pipeline — CLI entry point.

Usage:
    python -m pipeline --sheet "<url>" [--gid N] [--file path] [--out dir] [--sample N] [--use-llm]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import run_pipeline


def main() -> None:
    ap = argparse.ArgumentParser(description="Botamin BI Pipeline")
    ap.add_argument("--sheet", help="Google Sheets URL")
    ap.add_argument("--gid", type=int, default=None, help="Sheet GID (default: auto-detect or 0)")
    ap.add_argument("--file", type=Path, default=None, help="Local CSV/XLSX file fallback")
    ap.add_argument("--out", type=Path, default=Path("frontend/public/data"), help="Output directory")
    ap.add_argument("--sample", type=int, default=None, help="Limit to N rows for quick testing")
    ap.add_argument(
        "--llm-scope", choices=["focus", "full", "sample", "off"], default=None,
        help="LLM analysis depth: focus (substantive dialogues, default), "
             "full (all conversations), sample (calibration subset), off (deterministic only). "
             "Overrides LLM_SCOPE in .env.",
    )
    args = ap.parse_args()

    if not args.sheet and not args.file:
        ap.error("Provide --sheet URL or --file path")

    run_pipeline(
        sheet_url=args.sheet,
        gid=args.gid,
        file_path=args.file,
        out_dir=args.out,
        sample=args.sample,
        llm_scope=args.llm_scope,
    )


if __name__ == "__main__":
    main()
