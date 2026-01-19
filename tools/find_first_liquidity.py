#!/usr/bin/env python3
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
from web3 import Web3

# Add scripts directory to path to import local modules
sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))
from env_utils import load_env, get_env_for_chain

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "fxswaps.json"

METHOD_ID_ADD_LIQUIDITY = "0x0b4c7e4d"

def get_api_config(chain_name):
    load_env()
    chain_upper = chain_name.upper()
    
    api_key = get_env_for_chain(chain_name, "XSCAN_API_KEY")
    api_uri = get_env_for_chain(chain_name, "XSCAN_API_URI_ONLY") or "https://api.etherscan.io/v2/api"
    chain_id = get_env_for_chain(chain_name, "XSCAN_CHAIN_ID")
    
    if not chain_id:
        if "base" in chain_name.lower():
            chain_id = "8453"
        elif "ethereum" in chain_name.lower():
            chain_id = "1"
            
    return api_key, api_uri, chain_id

def find_first_liquidity(address, chain_name, start_block=0):
    api_key, api_uri, chain_id = get_api_config(chain_name)
    if not api_key:
        logging.warning(f"No API key found for {chain_name}")
        return None

    # Base parameters
    params = {
        "chainid": chain_id,
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": start_block,
        "endblock": 99999999,
        "page": 1,
        "offset": 1000,
        "sort": "asc",
        "apikey": api_key
    }

    # Clean up URI
    url = api_uri or ""
    if url.endswith("/v2/"):
        url = url + "api"
    elif not url.endswith("api") and not url.endswith("api/"):
        if not url.endswith("/"):
            url += "/"
        url += "api"

    logging.info(f"Querying {chain_name} for {address} starting from block {start_block}...")
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get("status") != "1":
            msg = data.get("message", "No message")
            res = data.get("result", "")
            logging.error(f"API error: {msg} - {res}")
            # If we get the "Free API access" error, we might want to try the direct chain API
            if "Free API access" in str(res) and "basescan" not in (url or ""):
                logging.info("Attempting fallback to direct Basescan API...")
                fallback_url = "https://api.basescan.org/api"
                fallback_params = params.copy()
                fallback_params.pop("chainid", None)
                resp = requests.get(fallback_url, params=fallback_params)
                data = resp.json()
                if data.get("status") != "1":
                    logging.error(f"Fallback API error: {data.get('message')} - {data.get('result')}")
                    return None
                transactions = data.get("result", [])
            else:
                return None
        else:
            transactions = data.get("result", [])
            
        if not isinstance(transactions, list):
            logging.error(f"Unexpected API result format: {transactions}")
            return None
            
        for tx in transactions:
            input_data = tx.get("input", "")
            if input_data.startswith(METHOD_ID_ADD_LIQUIDITY):
                block_number = int(tx.get("blockNumber"))
                logging.info(f"Found first add_liquidity at block {block_number} (tx: {tx.get('hash')})")
                return block_number
                
        logging.info(f"No add_liquidity transaction found in the first {len(transactions)} transactions.")
        return None
        
    except Exception as e:
        logging.error(f"Error querying API: {e}")
        return None

def main():
    if not CONFIG_PATH.exists():
        logging.error(f"Config file not found at {CONFIG_PATH}")
        return

    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    updated = False
    # Sort indices to process consistently
    indices = sorted(config.keys(), key=int)
    
    for idx in indices:
        pool = config[idx]
        if "first_liq_block" in pool and pool["first_liq_block"] is not None:
            continue
        
        name = pool.get("name", "Unknown")
        address = pool.get("address")
        chain_name = pool.get("chain_name")
        deployed_block = pool.get("deployed_at_block", 0)
        current_first = pool.get("first_liq_block")

        logging.info(f"--- Processing pool {idx}: {name} ({address}) ---")
        
        first_liq_block = find_first_liquidity(address, chain_name, start_block=deployed_block)
        
        if first_liq_block:
            if current_first != first_liq_block:
                logging.info(f"Updating first_liq_block: {current_first} -> {first_liq_block}")
                pool["first_liq_block"] = first_liq_block
                updated = True
            else:
                logging.info(f"first_liq_block is already correct: {first_liq_block}")
        
        # Sleep to respect rate limits
        time.sleep(1.0)

    if updated:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
            f.write("\n")
        logging.info("Updated config/fxswaps.json")
    else:
        logging.info("No updates needed.")

if __name__ == "__main__":
    main()
