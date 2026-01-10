#!/usr/bin/env python3
"""Fill historical fxswap cache gaps efficiently.

This utility inspects the cached Parquet datasets for fxswap pools, determines
missing block snapshots at the expected stride (20 on Ethereum, 100 on Base),
and back-fills those gaps via Multicall in descending block order.

Key workflow:
    1. Discover the latest block on-chain and align it to the stride.
    2. Enumerate existing cached blocks for the pool and locate gaps.
    3. Fetch missing blocks in batches, skipping already cached snapshots.
    4. Persist updates back to the Parquet dataset (unless ``--dry-run``).

By default the backfill begins at the pool's ``first_block`` from
``config/fxswaps.json`` (rounded down to the stride). Use ``--min-block`` to
override this floor or ``--max-blocks`` to cap the number of iterations.

Examples
--------
    # Dry-run a single pool (index 5) to preview work to be done
    ./scripts/fill_missing_fxswap_data.py --index 5 --dry-run

    # Back-fill all pools, fetching at most 1500 blocks per market
    ./scripts/fill_missing_fxswap_data.py --all --max-blocks 1500

    # Extend a specific pool down to block 35000000
    ./scripts/fill_missing_fxswap_data.py --index 3 --min-block 35000000

The script automatically reuses the RPC resolution logic from
``update_fxswap_blocks.py`` (including per-chain ``.env_base`` /
``.env_ethereum`` files) and requires ``pyarrow`` + ``web3`` to be installed.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import pandas as pd
import pyarrow.parquet as pq
from eth_utils.crypto import keccak
from web3 import Web3
from web3.exceptions import BlockNotFound

try:  # Optional progress bar support
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None  # type: ignore


try:  # Optional progress bar support
    from tqdm import tqdm
except ImportError:  # pragma: no cover - tqdm not installed
    tqdm = None  # type: ignore

from update_fxswap_blocks import RpcRegistry, build_parquet_index, load_config

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "fxswaps.json"
DATA_ROOT = ROOT_DIR / "data"

BASE_CHAIN_ID = 8453
ETHEREUM_CHAIN_ID = 1
CHAIN_STRIDE = {
    BASE_CHAIN_ID: 100,
    ETHEREUM_CHAIN_ID: 20,
}
DEFAULT_MAX_BLOCKS: Optional[int] = None
DEFAULT_CHUNK_SIZE = 50

FUNCTION_NAMES = [
    "last_prices",
    "price_scale",
    "price_oracle",
    "donation_shares",
    "fee",
    "last_donation_release_ts",
    "totalSupply",
    "user_supply",
    "xcp_profit",
    "xcp_profit_a",
    "virtual_price",
    "balances(0)",
    "balances(1)",
]


def get_function_selector_any(func: str) -> Tuple[str, Optional[str]]:
    matcher = re.match(r"(\w+)\((.*?)\)$", func)
    if matcher:
        fn_name, params = matcher.group(1), matcher.group(2)
        if params == "":
            signature = f"{fn_name}()"
            selector = keccak(text=signature)[:4].hex()
            return selector, None
        # single integer param assumed (uint256)
        signature = f"{fn_name}(uint256)"
        selector = keccak(text=signature)[:4].hex()
        try:
            param_value = int(params)
        except ValueError:
            raise ValueError(f"Unsupported parameter format in function '{func}'") from None
        encoded_param = param_value.to_bytes(32, "big").hex()
        return selector, encoded_param
    # fallback assume no params
    signature = f"{func}()"
    selector = keccak(text=signature)[:4].hex()
    return selector, None


def get_call_data(function_name: str) -> str:
    selector, param = get_function_selector_any(function_name)
    return "0x" + selector + (param or "")


FUNCTION_CALL_DATA = {name: get_call_data(name) for name in FUNCTION_NAMES}
MULTICALL3_ADDRESS = Web3.to_checksum_address("0xcA11bde05977b3631167028862bE2a173976CA11")
MULTICALL3_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bool", "name": "allowFailure", "type": "bool"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Call[]",
                "name": "calls",
                "type": "tuple[]",
            }
        ],
        "name": "aggregate3",
        "outputs": [
            {
                "components": [
                    {"internalType": "bool", "name": "success", "type": "bool"},
                    {"internalType": "bytes", "name": "returnData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Result[]",
                "name": "returnData",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    }
]



def load_existing_blocks(parquet_path: Path) -> List[int]:
    if not parquet_path.exists():
        return []
    try:
        parquet_file = pq.ParquetFile(parquet_path)
    except Exception as exc:  # pragma: no cover - I/O error
        logging.error("Unable to read %s: %s", parquet_path, exc)
        return []

    blocks: set[int] = set()
    try:
        for batch in parquet_file.iter_batches(columns=["block_number"], batch_size=100_000):
            column = batch.column(0)
            blocks.update(int(value) for value in column.to_pylist() if value is not None)
    except KeyError:
        logging.warning("Column 'block_number' missing in %s", parquet_path)
    return sorted(blocks)


def determine_target_blocks(
    *,
    latest_aligned: int,
    stride: int,
    existing_blocks: Sequence[int],
    min_block: Optional[int],
    max_blocks: Optional[int],
) -> List[int]:
    if latest_aligned < 0:
        return []

    lower_bound = max(0, min_block) if min_block is not None else None
    if lower_bound is None:
        lower_bound = existing_blocks[0] if existing_blocks else 0

    step_limit = max_blocks

    existing_set = set(existing_blocks)
    missing: List[int] = []

    block = latest_aligned
    steps = 0
    while block >= lower_bound:
        if block not in existing_set:
            missing.append(block)
        block -= stride
        steps += 1
        if step_limit is not None and steps >= step_limit:
            break

    return missing


def resolve_decimals(pool_name: str) -> Tuple[int, int]:
    token0_decimals = 18
    token1_decimals = 18
    if "USDC" in pool_name.upper():
        token0_decimals = 6
        token1_decimals = 18
    if "EURC" in pool_name.upper():
        token1_decimals = 6
    return token0_decimals, token1_decimals


def convert_result(function_name: str, raw: bytes, token_decimals: Tuple[int, int]) -> float:
    if not raw:
        return 0.0
    result_int = int.from_bytes(raw, "big")
    if function_name == "last_donation_release_ts":
        return float(result_int)
    if function_name == "balances(0)":
        return result_int / (10 ** token_decimals[0])
    return result_int / (10 ** token_decimals[1])


def fetch_block_snapshot(
    *,
    w3: Web3,
    multicall_contract,
    address: str,
    block_number: int,
    token_decimals: Tuple[int, int],
    silent: bool,
) -> Optional[List[Dict[str, object]]]:
    try:
        block_data = w3.eth.get_block(block_number)
    except BlockNotFound:
        logging.warning("Block %s not found; skipping", block_number)
        return None

    timestamp = int(block_data["timestamp"])
    human_readable = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    calls = [
        {
            "target": address,
            "allowFailure": True,
            "callData": FUNCTION_CALL_DATA[fn],
        }
        for fn in FUNCTION_NAMES
    ]

    try:
        results = multicall_contract.functions.aggregate3(calls).call(block_identifier=block_number)
    except Exception as exc:
        logging.warning("aggregate3 failed for block %s: %s -- retrying with single calls", block_number, exc)
        results = []
        for fn in FUNCTION_NAMES:
            try:
                raw = w3.eth.call({"to": address, "data": FUNCTION_CALL_DATA[fn]}, block_identifier=block_number)
                results.append((True, raw))
            except Exception as call_exc:
                logging.error("call() failed for %s at block %s: %s", fn, block_number, call_exc)
                results.append((False, b""))

    records: List[Dict[str, object]] = []
    for fn_name, (success, raw_bytes) in zip(FUNCTION_NAMES, results):
        if not success:
            logging.debug("Call %s failed at block %s", fn_name, block_number)
            continue
        value = convert_result(fn_name, raw_bytes, token_decimals)
        records.append(
            {
                "block_number": block_number,
                "function_name": fn_name,
                "value": value,
                "epoch": timestamp,
                "human_readable": human_readable,
            }
        )
    if not silent:
        logging.info("Fetched %s values for block %s", len(records), block_number)
    return records


def write_updates(
    *,
    parquet_path: Path,
    new_records: List[Dict[str, object]],
    dry_run: bool,
    existing_df: Optional[pd.DataFrame],
) -> Optional[pd.DataFrame]:
    if not new_records:
        logging.info("No data collected; skipping write to %s", parquet_path)
        return existing_df

    df_new = pd.DataFrame(new_records)
    if df_new.empty:
        logging.info("New record set empty after DataFrame conversion for %s", parquet_path)
        return existing_df

    if dry_run:
        logging.info("Dry-run: collected %s new rows for %s", len(df_new), parquet_path)
        return existing_df

    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    if existing_df is None and parquet_path.exists():
        existing_df = pd.read_parquet(parquet_path)

    if existing_df is not None:
        combined = pd.concat([existing_df, df_new], ignore_index=True)
    else:
        combined = df_new

    combined.drop_duplicates(subset=["block_number", "function_name"], keep="last", inplace=True)
    combined.sort_values(by=["block_number", "function_name"], inplace=True)

    temp_fd, temp_path = tempfile.mkstemp(suffix=".parquet", dir=parquet_path.parent)
    os.close(temp_fd)
    temp_file = Path(temp_path)
    try:
        combined.to_parquet(temp_file, compression="snappy", index=False)
        temp_file.replace(parquet_path)
    finally:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)

    logging.info("Wrote %s rows to %s", len(combined), parquet_path)
    return combined


def process_pool(
    *,
    pool_index: int,
    pool: Dict[str, object],
    rpc_registry: RpcRegistry,
    parquet_index: Dict[str, Path],
    args: argparse.Namespace,
) -> Dict[str, int]:
    address = str(pool["address"])
    chain_name = str(pool["chain_name"])
    chain_id = int(pool["chain_id"])
    name = str(pool.get("name", address))

    if chain_id not in CHAIN_STRIDE:
        logging.error("Unsupported chain_id %s for pool #%s", chain_id, pool_index)
        return {"fetched": 0, "missing": 0}

    stride = CHAIN_STRIDE[chain_id]
    normalized_address = address.lower()
    parquet_path = parquet_index.get(normalized_address)
    if parquet_path is None:
        parquet_path = DATA_ROOT / chain_name / f"{address}.parquet"
        parquet_index[normalized_address] = parquet_path

    w3 = rpc_registry.get(chain_name)
    multicall = w3.eth.contract(address=MULTICALL3_ADDRESS, abi=MULTICALL3_ABI)
    latest_block = w3.eth.get_block("latest")["number"]
    latest_aligned = latest_block - (latest_block % stride)

    existing_blocks = load_existing_blocks(parquet_path)

    config_first_block = pool.get("first_block")
    effective_min_block: Optional[int]
    if args.min_block is not None:
        effective_min_block = int(args.min_block)
    elif config_first_block is not None:
        try:
            effective_min_block = int(config_first_block)
        except (TypeError, ValueError):
            logging.warning(
                "Pool #%s %s (%s) has non-integer first_block=%s in config; falling back to cached data",
                pool_index,
                name,
                chain_name,
                config_first_block,
            )
            effective_min_block = None
    else:
        effective_min_block = None

    if effective_min_block is not None:
        effective_min_block = max(0, effective_min_block)
        remainder = effective_min_block % stride
        if remainder != 0:
            effective_min_block -= remainder

    missing_blocks = determine_target_blocks(
        latest_aligned=latest_aligned,
        stride=stride,
        existing_blocks=existing_blocks,
        min_block=effective_min_block,
        max_blocks=args.max_blocks,
    )
    missing_blocks.sort(reverse=True)

    target_floor = (
        effective_min_block
        if effective_min_block is not None
        else (existing_blocks[0] if existing_blocks else None)
    )

    logging.info(
        "Pool #%s %s (%s): latest=%s stride=%s cached=%s missing=%s floor=%s",
        pool_index,
        name,
        chain_name,
        latest_aligned,
        stride,
        len(existing_blocks),
        len(missing_blocks),
        target_floor,
    )

    if not missing_blocks:
        return {"fetched": 0, "missing": 0}

    token_decimals = resolve_decimals(name)
    failures: Dict[int, int] = defaultdict(int)
    fetched_blocks: set[int] = set()
    existing_df: Optional[pd.DataFrame] = None
    if not args.dry_run and parquet_path.exists():
        existing_df = pd.read_parquet(parquet_path)

    def process_batch(batch_blocks: List[int]) -> None:
        nonlocal existing_df
        if not batch_blocks:
            return
        chunk_records: List[Dict[str, object]] = []
        for block in batch_blocks:
            snapshot = fetch_block_snapshot(
                w3=w3,
                multicall_contract=multicall,
                address=address,
                block_number=block,
                token_decimals=token_decimals,
                silent=not args.verbose,
            )
            if snapshot:
                chunk_records.extend(snapshot)
                fetched_blocks.add(block)
            else:
                failures[block] += 1
        if chunk_records:
            existing_df = write_updates(
                parquet_path=parquet_path,
                new_records=chunk_records,
                dry_run=args.dry_run,
                existing_df=existing_df,
            )

    iterator: Iterable[int]
    progress_bar = None
    if tqdm is not None and not args.no_progress:
        progress_bar = tqdm(missing_blocks, desc=f"Pool #{pool_index} {name}", unit="block", leave=False)
        iterator = progress_bar
    else:
        iterator = missing_blocks

    batch: List[int] = []
    try:
        for block in iterator:
            batch.append(block)
            if len(batch) >= args.chunk_size:
                process_batch(batch)
                batch.clear()
    finally:
        if progress_bar is not None:
            progress_bar.close()

    if batch:
        process_batch(batch)

    if failures:
        logging.warning("Encountered %s failed blocks for pool #%s", len(failures), pool_index)

    return {"fetched": len(fetched_blocks), "missing": len(missing_blocks)}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to fxswap config JSON")
    parser.add_argument("--index", action="append", type=int, dest="indexes", help="Pool index to process (repeatable)")
    parser.add_argument("--all", action="store_true", help="Process every pool in the config")
    parser.add_argument("--min-block", type=int, help="Lower block bound to backfill (inclusive)")
    parser.add_argument(
        "--max-blocks",
        type=int,
        help="Maximum number of blocks to examine per pool (default: unlimited)",
        default=DEFAULT_MAX_BLOCKS,
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Number of blocks to fetch per batch")
    parser.add_argument("--dry-run", action="store_true", help="Do not write any changes to Parquet files")
    parser.add_argument("--verbose", action="store_true", help="Print per-block fetch logs")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bars even if tqdm is available")
    return parser.parse_args(list(argv) if argv is not None else None)



def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.max_blocks is not None and args.max_blocks <= 0:
        args.max_blocks = None

    config_path = Path(args.config)
    config = load_config(config_path)

    if not args.indexes and not args.all:
        raise SystemExit("Specify --index at least once or pass --all")

    targets = sorted(config.keys()) if args.all else sorted(set(int(i) for i in args.indexes))

    chains = {
        str(config[idx]["chain_name"]).lower()
        for idx in targets
        if idx in config and config[idx].get("chain_name")
    }
    rpc_registry = RpcRegistry(args, chains)
    parquet_index = build_parquet_index(DATA_ROOT)

    totals = {"fetched": 0, "missing": 0, "processed": 0}
    for idx in targets:
        if idx not in config:
            logging.error("Index %s not found in config; skipping", idx)
            continue
        summary = process_pool(
            pool_index=idx,
            pool=config[idx],
            rpc_registry=rpc_registry,
            parquet_index=parquet_index,
            args=args,
        )
        totals["fetched"] += summary["fetched"]
        totals["missing"] += summary["missing"]
        totals["processed"] += 1

    logging.info(
        "Finished processing %s pools. Missing=%s, fetched=%s.",
        totals["processed"],
        totals["missing"],
        totals["fetched"],
    )


if __name__ == "__main__":
    main()
