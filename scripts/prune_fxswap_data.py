#!/usr/bin/env python3
"""Prune cached fxswap Parquet data before a given block threshold.

Typical usage
-------------
    # Preview how many rows would be removed for pool index 0
    ./scripts/prune_fxswap_data.py --index 0 --before-block 38000000 --dry-run

    # Delete rows with block_number < 38000000 for two pools, writing backups
    ./scripts/prune_fxswap_data.py --index 0 --index 1 --before-block 38000000 --backup

The script loads ``config/fxswaps.json`` to resolve pool metadata and finds the
associated Parquet files inside ``data/<chain>/<address>.parquet``. Data is
filtered in-memory and rewritten atomically via a temporary file to avoid
corruption if interrupted. When ``--dry-run`` is supplied, no files are
modified and only summary information is displayed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from update_fxswap_blocks import build_parquet_index, load_config

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT_DIR / "config" / "fxswaps.json"
DATA_ROOT = ROOT_DIR / "data"


def ensure_parquet_index() -> Dict[str, Path]:
    if not DATA_ROOT.exists():
        raise SystemExit(f"Data directory not found: {DATA_ROOT}")
    return build_parquet_index(DATA_ROOT)


def locate_parquet_file(
    *,
    pool: Dict[str, object],
    index: int,
    parquet_index: Dict[str, Path],
) -> Path:
    address = str(pool.get("address", "")).lower()
    chain_name = str(pool.get("chain_name", "")).strip()
    if not address or not chain_name:
        raise SystemExit(f"Pool #{index} is missing address or chain_name")

    if address in parquet_index:
        return parquet_index[address]

    fallback = DATA_ROOT / chain_name / f"{address}.parquet"
    parquet_index[address] = fallback
    return fallback


def prune_file(
    *,
    parquet_path: Path,
    before_block: int,
    dry_run: bool,
    backup: bool,
) -> Dict[str, int]:
    if not parquet_path.exists():
        logging.warning("Parquet file not found: %s", parquet_path)
        return {"total": 0, "removed": 0, "remaining": 0}

    df = pd.read_parquet(parquet_path)
    if df.empty:
        logging.info("File %s already empty", parquet_path)
        return {"total": 0, "removed": 0, "remaining": 0}

    original_rows = len(df)
    mask = df["block_number"] < before_block
    removed_rows = int(mask.sum())
    remaining_df = df[~mask].copy()
    remaining_rows = len(remaining_df)

    logging.info(
        "%s: total=%s removed=%s remaining=%s (threshold=%s)",
        parquet_path,
        original_rows,
        removed_rows,
        remaining_rows,
        before_block,
    )

    if dry_run or removed_rows == 0:
        return {
            "total": original_rows,
            "removed": removed_rows,
            "remaining": remaining_rows,
        }

    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    temp_fd, temp_name = tempfile.mkstemp(suffix=".parquet", dir=parquet_path.parent)
    os.close(temp_fd)
    temp_path = Path(temp_name)
    try:
        remaining_df.sort_values(by=["block_number", "function_name"], inplace=True)
        remaining_df.to_parquet(temp_path, compression="snappy", index=False)
        if backup:
            backup_path = parquet_path.with_suffix(parquet_path.suffix + ".bak")
            parquet_path.replace(backup_path)
            logging.info("Backed up original file to %s", backup_path)
        temp_path.replace(parquet_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return {
        "total": original_rows,
        "removed": removed_rows,
        "remaining": remaining_rows,
    }


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to fxswap config JSON file")
    parser.add_argument("--index", action="append", type=int, dest="indexes", help="Pool index to prune (repeatable)")
    parser.add_argument("--all", action="store_true", help="Prune every pool listed in the config")
    parser.add_argument("--before-block", type=int, required=True, help="Delete rows where block_number is less than this value")
    parser.add_argument("--dry-run", action="store_true", help="Only report what would be removed")
    parser.add_argument("--backup", action="store_true", help="Preserve original file as <name>.parquet.bak before overwriting")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")

    if args.before_block < 0:
        raise SystemExit("--before-block must be a non-negative integer")

    if not args.indexes and not args.all:
        raise SystemExit("Specify --index at least once or pass --all")

    config_path = Path(args.config)
    config = load_config(config_path)

    targets = sorted(config.keys()) if args.all else sorted(set(int(i) for i in args.indexes))
    parquet_index = ensure_parquet_index()

    totals = {"total": 0, "removed": 0, "remaining": 0, "processed": 0}

    for idx in targets:
        if idx not in config:
            logging.error("Index %s not found in config; skipping", idx)
            continue

        pool = config[idx]
        parquet_path = locate_parquet_file(pool=pool, index=idx, parquet_index=parquet_index)
        summary = prune_file(
            parquet_path=parquet_path,
            before_block=args.before_block,
            dry_run=args.dry_run,
            backup=args.backup,
        )
        totals["total"] += summary["total"]
        totals["removed"] += summary["removed"]
        totals["remaining"] += summary["remaining"]
        totals["processed"] += 1

    logging.info(
        "Finished pruning %s pools. Removed %s rows out of %s; %s remain.",
        totals["processed"],
        totals["removed"],
        totals["total"],
        totals["remaining"],
    )


if __name__ == "__main__":
    main()
