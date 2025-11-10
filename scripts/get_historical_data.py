from web3 import Web3
import os
import json
import time
from eth_utils import keccak
from pathlib import Path
from datetime import datetime, timezone
import re
import argparse

# Setup
RPC = os.getenv('RPC')
w3 = Web3(Web3.HTTPProvider(RPC))

print(f"RPC: {RPC}")
print(f"w3: {w3}")

# Load fxswap_addresses from fxswaps.json if file exists, else use default.
fxswaps_path = Path(__file__).parent.parent / "config" / "fxswaps.json"
print(f"fxswaps_path: {fxswaps_path}")
fxswap_addresses = {}
if fxswaps_path.exists():
    try:
        with open(fxswaps_path, 'r') as f:
            fxswap_addresses_raw = json.load(f)
            # Convert string keys to integers (JSON requires string keys)
            fxswap_addresses = {int(k): v for k, v in fxswap_addresses_raw.items()}
        print(f"Loaded {len(fxswap_addresses)} pools from fxswaps.json")
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"Error loading fxswaps.json: {e}")
        print("Using empty fxswap_addresses dictionary")
        fxswap_addresses = {}
else:
    print(f"fxswaps.json not found at {fxswaps_path}, using empty dictionary")


# Parse command line arguments
parser = argparse.ArgumentParser(description='Collect historical data for fxswap pools')
parser.add_argument('--index', type=int, default=0, help='Index of the pool to query (default: 0)')
args = parser.parse_args()

index = args.index
if index not in fxswap_addresses:
    print(f"Error: Index {index} not found in fxswap_addresses")
    print(f"Available indices: {list(fxswap_addresses.keys())}")
    exit(1)

fxswap_address = fxswap_addresses[index]["address"]
name = fxswap_addresses[index]["name"]
chain_id = fxswap_addresses[index]["chain_id"]
chain_name = fxswap_addresses[index]["chain_name"]
print(f"Querying {name} on chain {chain_name} ({chain_id})")    

#first_block = fxswap_addresses[index]["first_block"]    

# Find the latest block on Base, rounded down to the nearest multiple of 200
latest_block = w3.eth.get_block('latest').number

print(f"Latest block: {latest_block}")

match chain_id:
    case 8453:
        block_number = latest_block - (latest_block % 100)
        min_block_threshold = 37524600  # Base chain minimum block
    case 1:
        block_number = latest_block - (latest_block % 20)
        # Ethereum: set to 0 or a reasonable minimum (e.g., deployment block)
        # 200 iterations * 20 blocks = 4000 blocks ≈ 1.5 days at 14s block time
        min_block_threshold = 0  # No minimum for Ethereum
    case _:
        print(f"Error: Chain ID {chain_id} not supported")
        print(f"Available chain IDs: {8453, 1}")
        sys.exit(1)

# Configuration
PRINT_CACHED_VALUES = False  # Set to True to print cached values
SILENT_MODE = True

# Data directory setup
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
# Use the chain_name as a subfolder for the fxswap data
fxswap_data_dir = Path("data") / chain_name
DATA_DIR.mkdir(parents=True, exist_ok=True)

data_file = fxswap_data_dir / f"{fxswap_address}.json"

# Global in-memory cache (loaded once at startup)
_in_memory_cache = None
_cache_dirty = False

# default decimals
token0_decimals = 18
token1_decimals = 18


def has_USDC(name):
    """
    Returns True if 'USDC' appears anywhere in the input pool name, else returns False.
    """
    if not isinstance(name, str):
        return False
    if "USDC" in name:
        return True
    return False

def load_cache():
    """Load cache from file (only called once at startup)"""
    global _in_memory_cache
    if _in_memory_cache is None:
        if data_file.exists():
            try:
                with open(data_file, 'r') as f:
                    _in_memory_cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                _in_memory_cache = {}
        else:
            _in_memory_cache = {}
    return _in_memory_cache

def save_cache(cache=None, force=False):
    """Save cache to file (only when dirty or forced)"""
    global _in_memory_cache, _cache_dirty
    if cache is None:
        cache = _in_memory_cache
    if cache is None:
        return False  # Nothing to save
    
    # Only save if dirty or forced - this prevents saving when nothing changed
    if force or _cache_dirty:
        with open(data_file, 'w') as f:
            json.dump(cache, f, indent=2)
        _cache_dirty = False
        return True  # Return True if we actually saved
    return False  # Return False if nothing changed, so we didn't save

def get_cached_value(fxswap_address, block_number, function_name, cache=None):
    """Get value from cache if exists (uses in-memory cache)"""
    if cache is None:
        cache = load_cache()
    block_str = str(block_number)
    
    if block_str in cache and isinstance(cache[block_str], dict):
        if function_name in cache[block_str]:
            cached_entry = cache[block_str][function_name]
            if isinstance(cached_entry, dict):
                return cached_entry.get('value')
    
    return None

def get_cached_entry(fxswap_address, block_number, function_name, cache=None):
    """Get full cached entry (including metadata) (uses in-memory cache)"""
    if cache is None:
        cache = load_cache()
    block_str = str(block_number)
    
    if block_str in cache and isinstance(cache[block_str], dict):
        if function_name in cache[block_str]:
            return cache[block_str][function_name]
    
    return None

def set_cached_value(fxswap_address, block_number, function_name, value, epoch=None, human_readable=None, cache=None, save_now=False):
    """Store value in cache with epoch and human-readable date (nested by block number)"""
    global _cache_dirty
    if cache is None:
        cache = load_cache()
    block_str = str(block_number)
    
    # Initialize block_number key if it doesn't exist
    if block_str not in cache:
        cache[block_str] = {}
    
    # Store nested: cache[block_number][function_name]
    cache[block_str][function_name] = {
        'value': value,
        'epoch': epoch,
        'human_readable': human_readable
    }
    _cache_dirty = True
    
    # Only save immediately if requested (for periodic saves)
    if save_now:
        save_cache(cache, force=True)

def get_function_selector_any(func):
    """
    Get selector for function, supporting e.g. "balances(0)"
    Returns tuple: (selector_hex, encoded_params_hex or None)
    """
    m = re.match(r"(\w+)\((.*?)\)", func)
    if m:
        fn, param = m.group(1), m.group(2)
        if param == "":
            sig = f"{fn}()"
            selector = keccak(bytes(sig, 'utf-8'))[:4].hex()
            return selector, None
        else:
            # Supports single integer param, assumes uint256
            sig = f"{fn}(uint256)"
            selector = keccak(bytes(sig, 'utf-8'))[:4].hex()
            # Encode the parameter as uint256 (32 bytes, padded)
            param_value = int(param)
            encoded_param = param_value.to_bytes(32, 'big').hex()
            return selector, encoded_param
    else:
        # fallback: treat as function()
        selector = keccak(bytes(f"{func}()", 'utf-8'))[:4].hex()
        return selector, None

def get_call_data(function_name):
    """
    Get the full call data (selector + encoded params) for a function
    Returns hex string starting with '0x'
    """
    selector, encoded_param = get_function_selector_any(function_name)
    if encoded_param:
        return '0x' + selector + encoded_param
    else:
        return '0x' + selector

# List of functions to query
function_names = [
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

# Print selectors for all functions
for func_name in function_names:
    selector, param = get_function_selector_any(func_name)
    if param:
        print(f"{func_name} selector: {selector}, param: {param}")
    else:
        print(f"{func_name} selector: {selector}")

# Load cache once at startup
cache = load_cache()
print(f"Loaded cache with {len(cache)} blocks")

# Save interval: save every N blocks (constant interval)
SAVE_INTERVAL = 20  # Save every 20 blocks processed

# Counter for consecutive blocks with all functions cached
consecutive_cached_blocks = 0
# Increase threshold to allow more blocks to be processed
# For Ethereum: 400 iterations * 20 blocks = 8000 blocks ≈ 3 days at 14s block time
MAX_CONSECUTIVE_CACHED = 1600  # Increased from 10 to allow more cached blocks before stopping

# override decimals if USDC is in the name
if has_USDC(name):
    token0_decimals = 6
    token1_decimals = 18

print(f"token0_decimals: {token0_decimals}")
print(f"token1_decimals: {token1_decimals}")   


# Loop over blocks and functions
for i in range(3000):
    if i == 0:
        # On the first iteration, do not subtract, so we start at the latest block
        pass
    else:
        if chain_id == 8453:
            block_number = block_number - 100
        else:
            block_number = block_number - 20

    if block_number < min_block_threshold:
        print(f"\n  STOPPING: Reached minimum block threshold")
        print(f"  Block {block_number} < min_block_threshold {min_block_threshold}")
        print(f"  Iteration: {i+1} of {400}")
        # Save before exiting
        save_cache(cache, force=True)
        break
    if PRINT_CACHED_VALUES:
        print(f"\nBlock {block_number}")

    # Separate cached and uncached functions (using in-memory cache)
    cached_functions = {}
    uncached_functions = []
    
    for function_name in function_names:
        cached_value = get_cached_value(fxswap_address, block_number, function_name, cache=cache)
        if cached_value is not None:
            cached_functions[function_name] = cached_value
        else:
            uncached_functions.append(function_name)
    
    # Check if all functions are cached
    if len(uncached_functions) == 0:
        consecutive_cached_blocks += 1
        if consecutive_cached_blocks >= MAX_CONSECUTIVE_CACHED:
            print("\n" + "="*80)
            print(" " * 20 + "⚠️  STOPPING: All Functions Cached ⚠️")
            print("="*80)
            print(f"\n  Encountered {MAX_CONSECUTIVE_CACHED} consecutive blocks")
            print(f"  where ALL functions were already cached!")
            print(f"\n  Last block checked: {block_number}")
            print(f"  Iteration: {i+1} of {400}")
            print(f"  Blocks processed: {i+1} blocks")
            print(f"  This indicates we've reached the end of uncached data.")
            print(f"  All data for blocks >= {block_number} is already in cache.")
            print("\n" + "="*80)
            save_cache(cache, force=True)
            break
        elif not SILENT_MODE or (i + 1) % 50 == 0:
            print(f"  Block {block_number}: All functions cached ({consecutive_cached_blocks}/{MAX_CONSECUTIVE_CACHED} consecutive)")
    else:
        # Reset counter when we find uncached functions
        if consecutive_cached_blocks > 0:
            print(f"  Block {block_number}: Found {len(uncached_functions)} uncached functions, resetting cached counter")
        consecutive_cached_blocks = 0
    
    # Process cached functions first (no network calls needed)
    for function_name, result in cached_functions.items():
        if PRINT_CACHED_VALUES:
            print(f"\n  Function: {function_name}")
            print(f"    Using cached value for {function_name}")
        cached_entry = get_cached_entry(fxswap_address, block_number, function_name, cache=cache)
        if isinstance(cached_entry, dict):
            epoch = cached_entry.get('epoch')
            human_readable = cached_entry.get('human_readable')
            if epoch and human_readable:
                print(f"    Cached epoch: {epoch}, time: {human_readable}")
        if PRINT_CACHED_VALUES:
            print(f"    {function_name}: {result}")
    
    # Check if totalSupply is 0 (from cache)
    total_supply = cached_functions.get('totalSupply')
    if total_supply is not None and total_supply == 0:
        print(f"\n  totalSupply is 0 at block {block_number}. Stopping data collection.")
        save_cache(cache, force=True)
        break
    
    # Only fetch block info if we have uncached functions
    if uncached_functions:
        block = w3.eth.get_block(block_number)
        timestamp = block['timestamp']
        dt = datetime.fromtimestamp(timestamp, timezone.utc)
        human_readable = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n  Block timestamp: {timestamp} ({human_readable})")
        
        # Flag to break out of outer loop if totalSupply is 0
        should_stop = False
        
        # Prioritize totalSupply - fetch it first if it's not cached
        # This allows us to stop early if totalSupply is 0
        function_list = uncached_functions.copy()
        if 'totalSupply' in function_list:
            # Move totalSupply to the front
            function_list.remove('totalSupply')
            function_list.insert(0, 'totalSupply')
        
        # Use Multicall3 for batching all uncached function calls
        # Multicall3 ABI and address
        multicall3_abi = [{
            "inputs": [
                {
                    "components": [
                        {"internalType": "address", "name": "target", "type": "address"},
                        {"internalType": "bool", "name": "allowFailure", "type": "bool"},
                        {"internalType": "bytes", "name": "callData", "type": "bytes"}
                    ],
                    "internalType": "struct Multicall3.Call[]",
                    "name": "calls",
                    "type": "tuple[]"
                }
            ],
            "name": "aggregate3",
            "outputs": [
                {
                    "components": [
                        {"internalType": "bool", "name": "success", "type": "bool"},
                        {"internalType": "bytes", "name": "returnData", "type": "bytes"}
                    ],
                    "internalType": "struct Multicall3.Result[]",
                    "name": "returnData",
                    "type": "tuple[]"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        }]

        MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"

        multicall3_contract = w3.eth.contract(address=MULTICALL3_ADDRESS, abi=multicall3_abi)
        calls = []
        fn_name_and_index = []
        for function_name in function_list:
            call_data = get_call_data(function_name)
            # allowFailure: True for all calls
            calls.append({
                "target": fxswap_address,
                "allowFailure": True,
                "callData": call_data
            })
            fn_name_and_index.append(function_name)

        try:
            # Call aggregate3 with the call array
            results = multicall3_contract.functions.aggregate3(calls).call(block_identifier=block_number)
            # Each result is a tuple (success, returnData)
            for idx, (success, result_bytes) in enumerate(results):
                function_name = fn_name_and_index[idx]
                if not success:
                    print(f"    ERROR: Call to {function_name} failed")
                    continue
                
                if not SILENT_MODE:
                    print(f"\n  Function: {function_name}")
                    print(f"    Fetching new data for {function_name} (multicall3)")
                
                # Parse the result bytes.
                # All our calls are reading uint values (single return), result is always 32 bytes.
                result_int = int.from_bytes(result_bytes, 'big')
                # For last_donation_release_ts, store as integer (timestamp)
                # For balances(0) (USDC), divide by 10**6 (USDC has 6 decimals)
                # For other functions, divide by 10**18 (decimal values)
                if function_name == 'last_donation_release_ts':
                    result = result_int
                elif function_name == 'balances(0)':
                    result = result_int / 10 ** token0_decimals
                else:
                    result = result_int / 10 ** token1_decimals
                set_cached_value(
                    fxswap_address, block_number, function_name, result,
                    epoch=timestamp, human_readable=human_readable, cache=cache, save_now=False
                )
                if not SILENT_MODE:
                    print(f"    {function_name}: {result}")
                else:
                    print(".", end="", flush=True)
                # Check if totalSupply is 0 and stop if so
                if function_name == 'totalSupply' and result == 0:
                    print(f"\n  totalSupply is 0 at block {block_number}. Stopping data collection.")
                    save_cache(cache, force=True)
                    should_stop = True
                    break
                time.sleep(0.01)
            if should_stop:
                break
            # Save after processing uncached functions if it's time for interval save
            # Only save if something actually changed (_cache_dirty will be True if new data was written)
            if (i + 1) % SAVE_INTERVAL == 0:
                if save_cache(cache, force=False):
                    print(f"  Saved cache after processing uncached functions (iteration {i + 1}, interval: {SAVE_INTERVAL})")
            continue  # Skip the legacy per-function loop below
        except Exception as e:
            print(f"    ERROR in multicall3: {e}")
            print(f"    Falling back to single-call loop.")
        # Process uncached functions
        for function_name in function_list:
            if not SILENT_MODE:
                print(f"\n  Function: {function_name}")
                print(f"    Fetching new data for {function_name}")
            
            call_data = get_call_data(function_name)
            result_bytes = w3.eth.call(
                {'to': fxswap_address, 'data': call_data},
                block_identifier=block_number
            )
            if not SILENT_MODE:
                print(f"    web3.eth.call params: {{'to': {fxswap_address}, 'data': {call_data}}}, block_identifier: {block_number}")
            # Convert bytes to int
            result_int = int.from_bytes(result_bytes, 'big')
            # For last_donation_release_ts, store as integer (timestamp)
            # For balances(0) (USDC), divide by 10**6 (USDC has 6 decimals)
            # For other functions, divide by 10**18 (decimal values)
            if function_name == 'last_donation_release_ts':
                result = result_int
            elif function_name == 'balances(0)':
                result = result_int / 10**6
            else:
                result = result_int / 10**18
            # Cache the result with epoch and human-readable date (don't save immediately)
            set_cached_value(fxswap_address, block_number, function_name, result, 
                            epoch=timestamp, human_readable=human_readable, cache=cache, save_now=False)
            if not SILENT_MODE:
                print(f"    {function_name}: {result}")
            else:
                print(".")
            
            # Check if totalSupply is 0 and stop if so
            if function_name == 'totalSupply' and result == 0:
                print(f"\n  totalSupply is 0 at block {block_number}. Stopping data collection.")
                # Save cache before breaking
                save_cache(cache, force=True)
                should_stop = True
                break
            
            time.sleep(0.01)
        
        # Save after processing uncached functions if it's time for interval save
        # Only save if something actually changed (_cache_dirty will be True if new data was written)
        if (i + 1) % SAVE_INTERVAL == 0:
            if save_cache(cache, force=False):
                print(f"  Saved cache after processing uncached functions (iteration {i + 1}, interval: {SAVE_INTERVAL})")
        
        # Break out of outer loop if totalSupply was 0
        if should_stop:
            break
    
    # Save cache periodically (every SAVE_INTERVAL blocks) - constant interval
    # Only save if something actually changed (_cache_dirty will be True if new data was written)
    # Note: If uncached functions were processed above, save already happened there
    if uncached_functions and (i + 1) % SAVE_INTERVAL == 0:
        # Already saved above after processing uncached functions
        pass
    elif (i + 1) % SAVE_INTERVAL == 0:
        # No uncached functions, but check if we should save (only if something changed)
        if save_cache(cache, force=False):
            print(f"  Saved cache after {i + 1} blocks processed (interval: {SAVE_INTERVAL})")

# Save cache at the end
save_cache(cache, force=True)
print(f"\nFinal cache save complete. Cache contains {len(cache)} blocks")
