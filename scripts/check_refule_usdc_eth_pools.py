#!/usr/bin/env python3

import boa
import os
from datetime import datetime
import time
import csv
import sys
from web3 import Web3
"""
This script is used to deploy a Curve pool using the stablepool factory contract.
It unpacks the packed parameters from deployment data and calls the deploy_pool function.
"""

# Load environment variables with `source .env_optimism`
XSCAN_API_URI = os.getenv('XSCAN_API_URI')
XSCAN_API_KEY = os.getenv('XSCAN_API_KEY')
RPC = os.getenv('RPC')

def get_block_timestamp_boa(block_number, rpc_url=None):
    """
    Get block timestamp using boa's internal chain access, with fallback to web3.
    
    Args:
        block_number: Block number to query
        rpc_url: RPC URL for fallback (defaults to RPC env variable)
    
    Returns:
        Unix timestamp (int) or None if not accessible
    """
    if rpc_url is None:
        rpc_url = RPC
    
    # Try accessing through boa's internal chain first
    try:
        # Try accessing through boa.env.evm.chain.blocks
        block_header = boa.env.evm.chain.blocks.get(block_number)
        return block_header.timestamp
    except (AttributeError, KeyError):
        try:
            # Alternative: try accessing through _env
            block_header = boa.env._env._evm.chain.blocks.get(block_number)
            # Try both 'timestamp' and 'epoch' attributes
            timestamp = getattr(block_header, 'timestamp', getattr(block_header, 'epoch', None))
            if timestamp is not None:
                return timestamp
        except (AttributeError, KeyError):
            pass
    
    # Fallback: use web3 to fetch block from RPC
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        block = w3.eth.get_block(block_number)
        return block['timestamp']
    except Exception as e:
        print(f"Warning: Could not fetch block {block_number} timestamp via web3: {e}")
        return None



# Setup CSV logging - append mode
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
os.makedirs(log_dir, exist_ok=True)

# Dictionary to track CSV files per pool name
csv_files = {}
csv_file_headers = {}
pool_names = {}  # Map pool address to pool name

def sanitize_filename(name):
    """Sanitize pool name for use in filename"""
    # Replace invalid filename characters with underscore
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    # Replace spaces with underscore
    name = name.replace(' ', '_')
    return name

def get_csv_file(pool_address, pool_name=None):
    """Get or create CSV file for a pool"""
    # If we have a pool name, use it; otherwise use address as fallback
    if pool_name:
        pool_identifier = pool_name
        pool_names[pool_address] = pool_name
    elif pool_address in pool_names:
        pool_identifier = pool_names[pool_address]
    elif pool_address is None:
        pool_identifier = 'general'
    else:
        pool_identifier = pool_address
    
    if pool_identifier not in csv_files:
        # Create filename from pool name (sanitized)
        if pool_name:
            safe_name = sanitize_filename(pool_name)
        elif pool_identifier != 'general':
            # Use last 8 chars of address as fallback
            safe_name = pool_identifier[-8:] if len(pool_identifier) > 8 else pool_identifier
        else:
            safe_name = 'general'
        
        csv_filename = os.path.join(log_dir, f'check_refule_usdc_eth_pools_{safe_name}.csv')
        
        # Check if file exists
        file_exists = os.path.exists(csv_filename) and os.path.getsize(csv_filename) > 0
        
        # Open CSV file in append mode
        csv_file = open(csv_filename, 'a', newline='')
        csv_files[pool_identifier] = csv_file
        csv_file_headers[pool_identifier] = file_exists
        
        # Write header only if file is new/empty
        if not file_exists:
            csv_file.write('timestamp;pool_address;message\n')
            csv_file.flush()
    
    return csv_files[pool_identifier]

# Save the original print function before we replace it
_original_print = print

# Custom print function that also writes to CSV
current_pool_address = None
current_pool_name = None

def print_and_log(*args, **kwargs):
    """Print to console and also log to CSV"""
    # Use the original print function
    _original_print(*args, **kwargs)
    
    # Format the message
    message = ' '.join(str(arg) for arg in args)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Get the appropriate CSV file for this pool
    csv_file = get_csv_file(current_pool_address, current_pool_name)
    
    # Manually write CSV line with semicolon delimiter (no quotes)
    csv_line = f"{timestamp};{current_pool_address or ''};{message}\n"
    csv_file.write(csv_line)
    csv_file.flush()  # Ensure data is written immediately

# Replace print with our custom function
print = print_and_log

print(f"XSCAN_API_KEY; {XSCAN_API_KEY}")
print(f"XSCAN_API_URI; {XSCAN_API_URI}")
print(f"RPC; {RPC}")


boa.fork(RPC)

fxswap_addresses = [
    # USDC/WETH A2-5
    "0x4de88ecfa7f6548aA0d5C6D01b381Ea917E71F73",
    # USDC/WETH A5-5
    "0xC88768B569902e1A67E54b090bA4969fde1204FA",
    # USDC/WETH A20-5
    "0x3D0143f6453a707b840b6565F959D6cbBA86F23e",
    # USDC/WETH A40-5
    "0x993a0D30FfA321D32eD0E8272Ded0108eBb1099A",
    # USDC/AERO A20-15
    #"0x3CeA080D303bD105c48cA4C24D8426da99f75524",
]

del fxswap_addresses[0]
del fxswap_addresses[0]
del fxswap_addresses[0]

fxswap_contracts = {}

for fxswap_address in fxswap_addresses:
    lp_price = boa.env.raw_call(
        to=fxswap_address,
        data="0x54f0f7d5",
        block_identifier=37788206
    )
    print(f"lp_price; {lp_price}")

    fxswap_contract = boa.from_etherscan(
        fxswap_address,
        name="fxswap",
        chain_id=8453,
        api_key=XSCAN_API_KEY
    )
    fxswap_contracts[fxswap_address] = fxswap_contract
    # 10. lp_price (0x54f0f7d5)
    result = boa.env.raw_call(
        to=fxswap_address,
        data="0x54f0f7d5",
        block_identifier=37788206
    )
    print(f"result; {result}")
    time.sleep(2)




# https://basescan.org/tx/0x3362ef552d87b3c02b4a933d060757b7023b4bd9ad6a91d6dc27a4d47665eda4#statechange
# last_donation_release_ts storage slot, why two different slots?
# 0x0000000000000000000000000000000000000000000000000000000000000005
# 0x000000000000000000000000000000000000000000000000000000000000000d



for i in range(100000):
    print(f"Iteration {i}")



    print(f"result; {result}")

    # 37788206 now 2000 blocks an h
    # Force update to latest block and print blocknumber for tracking historical data

    # boa.env.set_block('latest')  
    block_number = 37788206-i*400   # every ~10 min
    boa.env.set_block(block_number)
    current_block = boa.env.block_number
    print(f"Current block number: {current_block}")
    
    # Get block timestamp from boa's EVM chain (with fallback to RPC)
    block_epoch = get_block_timestamp_boa(block_number)
    if block_epoch is not None:
        block_datetime = datetime.fromtimestamp(block_epoch)
        print(f"Block {block_number} timestamp: {block_epoch} ({block_datetime})")
    else:
        print(f"Warning: Could not access block timestamp for block {block_number}")
        block_datetime = None
    
    for fxswap_address in fxswap_addresses:
        
        current_pool_address = fxswap_address  # Update current pool for CSV logging
        fxswap_contract = fxswap_contracts[fxswap_address]

        pool_name = fxswap_contract.name()  # Get pool name
        current_pool_name = pool_name  # Update current pool name for CSV logging
        
        print(f"\n\n\nName; {pool_name}\n\n\n\n")
        # Use block_datetime instead of datetime.now()
        if block_datetime is not None:
            print(f"Block datetime (UTC); {block_datetime}")
        else:
            print(f"Current date and time; {datetime.now()}")
        token0_address = fxswap_contract.coins(0)
        token1_address = fxswap_contract.coins(1)
        print(f"token0_address; {token0_address}")
        print(f"token1_address; {token1_address}")

        if False:  
            token0_contract = boa.from_etherscan(
                token0_address,
                name="token0",
                chain_id=8453,
                api_key=XSCAN_API_KEY
            )
            token0_name = token0_contract.name()
            token0_symbol = token0_contract.symbol()
            token0_decimals = token0_contract.decimals()

            print(f"token0_name; {token0_name}")
            print(f"token0_symbol; {token0_symbol}")
            print(f"token0_decimals; {token0_decimals}")
            token1_contract = boa.from_etherscan(
                token1_address,
                name="token1",
                chain_id=8453,
                api_key=XSCAN_API_KEY
            )
            token1_name = token1_contract.name()
            token1_symbol = token1_contract.symbol()
            token1_decimals = token1_contract.decimals()
            print(f"token1_name; {token1_name}")
            print(f"token1_symbol; {token1_symbol}")
            print(f"token1_decimals; {token1_decimals}")

        else:
            token0_name = "USDC"
            token1_name = "WETH"
            token0_decimals = 6
            token1_decimals = 18

        print(f"token0_name; {token0_name}")
        print(f"token1_name; {token1_name}")
        print(f"token0_decimals; {token0_decimals}")
        print(f"token1_decimals; {token1_decimals}")

        donation_shares = fxswap_contract.donation_shares()

        print(f"donation_shares(); {donation_shares / 10**18}")
        print(f"donation_shares(); {donation_shares}")
        print(f"donation_shares_max_ratio(); {fxswap_contract.donation_shares_max_ratio()}")

        last_donation_release_ts = fxswap_contract.last_donation_release_ts()
        print(f"last_donation_release_ts; {last_donation_release_ts}")
        print(f"last_donation_release_ts; {datetime.fromtimestamp(last_donation_release_ts)}")
        time_delta = datetime.now() - datetime.fromtimestamp(last_donation_release_ts)
        print(f"time_delta; {time_delta}")
        print(f"time_delta; {time_delta.days}")
        print(f"time_delta; {time_delta.seconds}")
        print(f"time_delta; {time_delta.total_seconds()}")
        print(f"time_delta; {time_delta.total_seconds() / 60 / 60 / 24}")


        print(f"donation_protection_expiry_ts(); {fxswap_contract.donation_protection_expiry_ts()}")
        print(f"donation_protection_period(); {fxswap_contract.donation_protection_period()}")

        # Print out *all* view/external-view functions with no params from fxswap.vy

        print(f"fee_receiver(); {fxswap_contract.fee_receiver()}")
        print(f"admin(); {fxswap_contract.admin()}")
        
        balance_0 = fxswap_contract.balances(0)
        balance_1 = fxswap_contract.balances(1)

        print(f"balance_0; {balance_0}")
        print(f"balance_1; {balance_1}")
        print(f"balance_0; {balance_0}")
        print(f"balance_eth; {balance_1}")
        print(f"balance_usdc; {balance_0 / 10**token0_decimals} {token0_name}")
        print(f"balance_eth; {balance_1 / 10**token1_decimals} {token1_name}")
        calculate_lp_share = fxswap_contract.calc_token_amount([balance_0, balance_1], True)
        print(f"calculate_lp_share; {calculate_lp_share / 10**18}")
        calculate_price = balance_0 * 10**12 / balance_1
        print(f"calculate_price; {calculate_price}")
        print(f"calculate_price; {calculate_price / 10**18}")
        print(f"calculate_price; {calculate_price / 10**18 / 10**18}")

        print(f"user_supply(); {fxswap_contract.user_supply()}")
        print(f"donation_shares_max_ratio(); {fxswap_contract.donation_shares_max_ratio()}")
        print(f"last_donation_release_ts(); {fxswap_contract.last_donation_release_ts()}")
        print(f"donation_protection_expiry_ts(); {fxswap_contract.donation_protection_expiry_ts()}")
        print(f"donation_protection_period(); {fxswap_contract.donation_protection_period()}")
        print(f"name(); {fxswap_contract.name()}")
        print(f"symbol(); {fxswap_contract.symbol()}")
        # print(f"decimals(); {fxswap_contract.decimals()}")
        # print(f"version(); {fxswap_contract.version()}")

        print(f"\n\n*****donnation shares calculation*****\n")
        # total lp tokens supply
        total_supply = fxswap_contract.totalSupply()    

        token0_amount = (donation_shares / total_supply) * balance_0
        token1_amount = (donation_shares / total_supply) * balance_1

        print(f"token0_amount; {token0_amount / 10**token0_decimals} {token0_name}")
        print(f"token1_amount; {token1_amount / 10**token1_decimals} {token1_name}")
        total_amount = token0_amount*2 / 10**token0_decimals
        print(f"total_amount; {total_amount} {token0_name} + {token1_name}")

        print(f"totalSupply(); {total_supply}")
        print(f"user_supply(); {fxswap_contract.user_supply()}")
        print(f"donation_shares(); {fxswap_contract.donation_shares()}")
        print(f"user supply is the total supply minus the donation shares; {fxswap_contract.totalSupply() - fxswap_contract.donation_shares()}")

        print(f"A(); {fxswap_contract.A()}")
        print(f"gamma(); {fxswap_contract.gamma()}")
        print(f"mid_fee(); {fxswap_contract.mid_fee()}")
        print(f"out_fee(); {fxswap_contract.out_fee()}")
        print(f"fee_gamma(); {fxswap_contract.fee_gamma()}")
        print(f"admin_fee(); {fxswap_contract.admin_fee()}")
        print(f"allowed_extra_profit(); {fxswap_contract.allowed_extra_profit()}")
        print(f"adjustment_step(); {fxswap_contract.adjustment_step()}")
        # print(f"ma_time(); {fxswap_contract.ma_time()}")
        print(f"virtual_price(); {fxswap_contract.virtual_price()}")
        print(f"precisions(); {fxswap_contract.precisions()}")
        #print(f"fee_calc(balances); {fxswap_contract.fee_calc(fxswap_contract.balances())}")
        #print(f"fee(); {fxswap_contract.fee()}")
        #print(f"calc_token_fee(amounts, xp, donation, deposit); {fxswap_contract.calc_token_fee(fxswap_contract.balances(), fxswap_contract.balances(), True, False)}")
        #print(f"calc_token_fee(amounts, xp, donation, deposit); {fxswap_contract.calc_token_fee(fxswap_contract.balances(), fxswap_contract.balances(), False, True)}")
        #print(f"calc_token_fee(amounts, xp, donation, deposit); {fxswap_contract.calc_token_fee(fxswap_contract.balances(), fxswap_contract.balances(), True, True)}")
        #print(f"calc_token_fee(amounts, xp, donation, deposit); {fxswap_contract.calc_token_fee(fxswap_contract.balances(), fxswap_contract.balances(), False, False)}")
        #print(f"calc_token_fee(amounts, xp, donation, deposit); {fxswap_contract.calc_token_fee(fxswap_contract.balances(), fxswap_contract.balances(), True, True)}")
        # print(f"cached_price_scale(); {fxswap_contract.cached_price_scale()}")
        # print(f"cached_price_oracle(); {fxswap_contract.cached_price_oracle()}")

        print(f"\n\n*****diviation of liquidity*****\n")

        print(f"last_prices(); {fxswap_contract.last_prices()}")
        print(f"price_oracle(); {fxswap_contract.price_oracle()}")
        print(f"price_scale(); {fxswap_contract.price_scale()}")

        delta_price_last_to_oracle = fxswap_contract.last_prices() - fxswap_contract.price_oracle()
        print(f"delta_price_last_to_oracle() in USD; {delta_price_last_to_oracle/10**18}")
        
        delta_price_last_to_oracle_percent = (delta_price_last_to_oracle / fxswap_contract.price_oracle()) * 100
        print(f"delta_price_last_to_oracle() in %; {delta_price_last_to_oracle_percent:.6f}%")


        delta_price_last_to_scale = fxswap_contract.last_prices() - fxswap_contract.price_scale()
        print(f"delta_price_last_to_scale() in USD; {delta_price_last_to_scale/10**18}")
        delta_price_last_to_scale_percent = (delta_price_last_to_scale / fxswap_contract.price_scale()) * 100
        print(f"delta_price_last_to_scale() in %; {delta_price_last_to_scale_percent:.6f}%")
        
        delta_price_oracle_to_scale = fxswap_contract.price_oracle() - fxswap_contract.price_scale()
        print(f"delta_price_oracle_to_scale() in USD; {delta_price_oracle_to_scale/10**18}")
        delta_price_oracle_to_scale_percent = (delta_price_oracle_to_scale / fxswap_contract.price_scale()) * 100
        print(f"delta_price_oracle_to_scale() in %; {delta_price_oracle_to_scale_percent:.6f}%")


        lp_price = fxswap_contract.lp_price()
        print(f"lp_price(); {lp_price}")
        get_virtual_price = fxswap_contract.get_virtual_price()
        print(f"get_virtual_price(); {get_virtual_price}")
        print(f"last_timestamp(); {fxswap_contract.last_timestamp()}")
        print(f"xcp_profit(); {fxswap_contract.xcp_profit()}")
        print(f"xcp_profit_a(); {fxswap_contract.xcp_profit_a()}")
        print(f"D(); {fxswap_contract.D()}")
        print(f"initial_A_gamma(); {fxswap_contract.initial_A_gamma()}")
        print(f"future_A_gamma(); {fxswap_contract.future_A_gamma()}")
        print(f"future_A_gamma_time(); {fxswap_contract.future_A_gamma_time()}")
        print(f"packed_fee_params(); {fxswap_contract.packed_fee_params()}")
        print(f"packed_rebalancing_params(); {fxswap_contract.packed_rebalancing_params()}")
        print(f"donation_duration(); {fxswap_contract.donation_duration()}")
        print(f"donation_protection_lp_threshold(); {fxswap_contract.donation_protection_lp_threshold()}")
        time.sleep(2)
        #time.sleep(60/len(fxswap_addresses))

# Close all CSV files at the end
for csv_file in csv_files.values():
    csv_file.close()

# Use original print for final message since CSV files are closed
_original_print(f"\nLogs appended to files in: {log_dir}")