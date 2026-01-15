#!/usr/bin/env python3
import argparse
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from eth_utils.crypto import keccak
from web3 import Web3
from web3.exceptions import BlockNotFound

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

STRIDES = {
    8453: 100,  # Base
    1: 20,      # Ethereum
}

# Mapping of chain_name -> candidate environment variable names for RPC URLs.
RPC_ENV_HINTS = {
    "base": ("BASE_RPC_URL", "BASE_RPC", "RPC_BASE", "RPC"),
    "ethereum": ("ETHEREUM_RPC_URL", "MAINNET_RPC_URL", "ETH_RPC", "RPC_ETHEREUM", "RPC"),
}

def get_function_selector(func):
    import re
    matcher = re.match(r"(\w+)\((.*?)\)$", func)
    if matcher:
        fn_name, params = matcher.group(1), matcher.group(2)
        if params == "":
            signature = f"{fn_name}()"
            selector = keccak(text=signature)[:4].hex()
            return selector, None
        signature = f"{fn_name}(uint256)"
        selector = keccak(text=signature)[:4].hex()
        encoded_param = int(params).to_bytes(32, "big").hex()
        return selector, encoded_param
    signature = f"{func}()"
    selector = keccak(text=signature)[:4].hex()
    return selector, None

FUNCTION_CALL_DATA = {name: "0x" + get_function_selector(name)[0] + (get_function_selector(name)[1] or "") for name in FUNCTION_NAMES}

def get_rpc_url(chain_name):
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

def process_pool(pool_idx, pool_info, rpc_urls):
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
    floor_block = int(pool_info.get("first_block", 0))
    if floor_block % stride != 0:
        floor_block += (stride - (floor_block % stride))

    parquet_path = Path(f"data/{chain_name}/{address}.parquet")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    
    existing_blocks = load_existing_blocks(parquet_path)
    
    # Generate list of target blocks backwards
    target_blocks = list(range(latest_aligned, floor_block - 1, -stride))
    missing_blocks = [b for b in target_blocks if b not in existing_blocks]
    
    if not missing_blocks:
        logging.info(f"Pool {name}: Already up to date.")
        return

    logging.info(f"Pool {name}: Fetching {len(missing_blocks)} blocks.")
    
    decimals = resolve_decimals(name)
    batch_records = []
    processed_count = 0
    
    for block in missing_blocks:
        data = fetch_block_data(w3, multicall, address, block, decimals)
        if data:
            batch_records.extend(data)
            processed_count += 1
        
        time.sleep(0.01) # Throttle
        
        if processed_count >= 200:
            save_batch(parquet_path, batch_records)
            logging.info(f"Saved batch of 200 blocks for {name}. Progress: {processed_count}/{len(missing_blocks)}")
            batch_records = []
            processed_count = 0
            # Note: processed_count reset here only for batching, need separate total if reporting total progress
            
    # Final save
    if batch_records:
        save_batch(parquet_path, batch_records)
        logging.info(f"Final save for {name}.")

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, help="Pool index")
    parser.add_argument("--all", action="store_true", help="Process all pools")
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
            process_pool(idx, config[idx], rpc_urls)

if __name__ == "__main__":
    main()
