#!/usr/bin/env python3
import argparse
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

import pandas as pd
import pyarrow.parquet as pq
from eth_utils.crypto import keccak
from web3 import Web3
from web3.exceptions import BlockNotFound

from env_utils import load_env

# Constants
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

def _build_call_data():
    """Build function call data (selector + args) for each function."""
    data = {}
    for fn in FUNCTION_NAMES:
        if fn.startswith("balances("):
            # balances(uint256) with argument
            idx = int(fn.split("(")[1].rstrip(")"))
            selector = keccak(b"balances(uint256)")[:4]
            arg = idx.to_bytes(32, "big")
            data[fn] = selector + arg
        else:
            # No-argument functions
            selector = keccak(f"{fn}()".encode())[:4]
            data[fn] = selector
    return data

FUNCTION_CALL_DATA = _build_call_data()

STRIDES = {
    8453: 100,  # Base
    1: 20,      # Ethereum
    100: 40,    # Gnosis
}

SLEEP_TIME = 0.001 # 1ms

# Mapping of chain_name -> candidate environment variable names for RPC URLs.
RPC_ENV_HINTS = {
    "base": ("BASE_RPC", "BASE_RPC_URL", "RPC_BASE", "RPC"),
    "ethereum": ("ETHEREUM_RPC", "ETHEREUM_RPC_URL", "MAINNET_RPC_URL", "ETH_RPC", "RPC_ETHEREUM", "RPC"),
    "gnosis": ("GNOSIS_RPC", "GNOSIS_RPC_URL", "RPC_GNOSIS", "RPC"),
}

def get_rpc_url(chain_name):

    load_env()
    hints = RPC_ENV_HINTS.get(chain_name.lower(), ("RPC",))
    for hint in hints:
        url = os.getenv(hint)
        if url:
            return url
    return None

def load_existing_blocks(parquet_path):
    if not parquet_path.exists():
        return set()
    try:
        table = pq.read_table(parquet_path, columns=["block_number"])
        return set(table.column(0).to_pylist())
    except Exception as e:
        logging.error(f"Error reading {parquet_path}: {e}")
        return set()

def resolve_decimals(pool_name):
    token0_decimals, token1_decimals = 18, 18
    if "USDC" in pool_name.upper():
        token0_decimals = 6
    if "EURC" in pool_name.upper():
        token1_decimals = 6
    return token0_decimals, token1_decimals

def convert_result(fn_name, raw_bytes, decimals):
    if not raw_bytes: return 0.0
    val = int.from_bytes(raw_bytes, "big")
    if fn_name == "last_donation_release_ts": return float(val)
    if fn_name == "balances(0)": return val / (10 ** decimals[0])
    return val / (10 ** decimals[1])

def fetch_block_data(w3, multicall, address, block_number, decimals):
    try:
        block_info = w3.eth.get_block(block_number)
        ts = int(block_info["timestamp"])
        human_time = datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        calls = [{"target": address, "allowFailure": True, "callData": FUNCTION_CALL_DATA[fn]} for fn in FUNCTION_NAMES]
        results = multicall.functions.aggregate3(calls).call(block_identifier=block_number)
        
        records = []
        for fn_name, (success, raw) in zip(FUNCTION_NAMES, results):
            if not success: continue
            records.append({
                "block_number": block_number,
                "function_name": fn_name,
                "value": convert_result(fn_name, raw, decimals),
                "epoch": ts,
                "human_readable": human_time
            })
        return records
    except Exception as e:
        logging.error(f"Failed block {block_number}: {e}")
        return None

def save_batch(parquet_path, new_records):
    if not new_records: return
    df_new = pd.DataFrame(new_records)
    if parquet_path.exists():
        df_old = pd.read_parquet(parquet_path)
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new
    
    df_combined.drop_duplicates(subset=["block_number", "function_name"], keep="last", inplace=True)
    df_combined.sort_values(by=["block_number", "function_name"], inplace=True)
    
    # Atomic write via temp file
    temp_path = parquet_path.with_suffix(".tmp")
    df_combined.to_parquet(temp_path, index=False, compression="snappy")
    temp_path.replace(parquet_path)

def process_pool(pool_idx, pool_info, rpc_urls, no_progress=False):
    chain_name = pool_info["chain_name"]
    address = pool_info["address"]
    name = pool_info["name"]
    stride = STRIDES.get(pool_info["chain_id"], 100)
    
    rpc_url = rpc_urls.get(chain_name)
    if not rpc_url:
        logging.error(f"No RPC for {chain_name}")
        return

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    multicall = w3.eth.contract(address=MULTICALL3_ADDRESS, abi=MULTICALL3_ABI)
    
    latest_block = w3.eth.block_number
    latest_aligned = latest_block - (latest_block % stride)
    
    # Absolute floor for data collection
    floor_block = int(pool_info.get("first_liq_block") or pool_info.get("deployed_at_block", 0))
    if floor_block % stride != 0:
        floor_block += (stride - (floor_block % stride))

    parquet_path = Path(f"data/{chain_name}/{address}.parquet")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    
    existing_blocks = load_existing_blocks(parquet_path)
    existing_max = max(existing_blocks) if existing_blocks else 0
    
    # Generate list of target blocks backwards from latest down to the absolute floor.
    target_blocks = list(range(latest_aligned, floor_block - 1, -stride))
    missing_blocks = [b for b in target_blocks if b not in existing_blocks]
    
    logging.info(f"Pool {name}: on_chain={latest_block}, aligned={latest_aligned}, newest_local={existing_max}, missing={len(missing_blocks)}")
    
    if not missing_blocks:
        if latest_aligned > existing_max and existing_max > 0:
             logging.info(f"Pool {name}: Should fetch {latest_aligned} but it might be caught in stride.")
        return

    logging.info(f"Pool {name}: Fetching {len(missing_blocks)} blocks.")
    
    decimals = resolve_decimals(name)
    batch_records = []
    batch_count = 0
    total_missing = len(missing_blocks)
    
    iterator = missing_blocks
    pbar = None
    if tqdm and not no_progress:
        pbar = tqdm(total=total_missing, desc=f"Updating {name}", unit="block")
        iterator = missing_blocks

    for i, block in enumerate(iterator, 1):
        data = fetch_block_data(w3, multicall, address, block, decimals)
        if data:
            batch_records.extend(data)
            batch_count += 1
        
        if pbar:
            pbar.update(1)
        
        time.sleep(SLEEP_TIME) # Throttle
        
        if batch_count >= 200:
            save_batch(parquet_path, batch_records)
            if not pbar:
                logging.info(f"Saved batch of 200 blocks for {name}. Progress: {i}/{total_missing}")
            batch_records = []
            batch_count = 0
            
    if pbar:
        pbar.close()

    # Final save
    if batch_records:
        save_batch(parquet_path, batch_records)
        logging.info(f"Final save for {name}. Progress: {total_missing}/{total_missing}")

def main():
    print("DEBUG: update_data.py is starting...")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, help="Pool index")
    parser.add_argument("--all", action="store_true", help="Process all pools")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar")
    args = parser.parse_args()

    config_path = Path("config/fxswaps.json")
    with open(config_path) as f:
        config = json.load(f)
    
    # Pre-resolve RPCs
    chains = set(p["chain_name"] for p in config.values())
    rpc_urls = {c: get_rpc_url(c) for c in chains}
    
    targets = [str(args.index)] if args.index is not None else (config.keys() if args.all else ["0"])
    
    for idx in targets:
        if idx in config:
            process_pool(idx, config[idx], rpc_urls, no_progress=args.no_progress)

if __name__ == "__main__":
    main()
