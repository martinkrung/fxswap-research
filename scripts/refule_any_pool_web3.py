#!/usr/bin/env python3

from web3 import Web3
import json
import os
from getpass import getpass
from eth_account import account
import sys
import math
from eth_utils import keccak
import requests
from pathlib import Path

"""
This script is used to refuel a Curve pool by adding liquidity.
Rewritten to use web3.py instead of boa.
"""

# Load environment variables with `source .env_optimism`
XSCAN_API_URI = os.getenv('XSCAN_API_URI')
XSCAN_API_URI_ONLY = os.getenv('XSCAN_API_URI_ONLY')
XSCAN_API_KEY = os.getenv('XSCAN_API_KEY')
XSCAN_CHAIN_ID = os.getenv('XSCAN_CHAIN_ID')
RPC = os.getenv('RPC')
SINGER = os.getenv('SINGER')

print(f"XSCAN_API_KEY: {XSCAN_API_KEY}")
print(f"XSCAN_API_URI: {XSCAN_API_URI}")
print(f"XSCAN_API_URI_ONLY: {XSCAN_API_URI_ONLY}")
print(f"XSCAN_CHAIN_ID: {XSCAN_CHAIN_ID}")
print(f"RPC: {RPC}")
print(f"SINGER: {SINGER}")

def account_load(fname):
    path = os.path.expanduser(os.path.join('~', '.ape', 'accounts', fname + '.json'))
    print(f"Loading account from: {path}")
    with open(path, 'r') as f:
        pkey = account.decode_keyfile_json(json.load(f), getpass())
        acc = account.Account.from_key(pkey)
        print(f"Account loaded: {acc.address}")
        return acc


signer = account_load(SINGER)

SIM = True
# Note: SIM mode (forking) is not directly supported in web3.py
# You would need to use a local node with fork capabilities (e.g., Anvil, Hardhat)

# Setup web3
w3 = Web3(Web3.HTTPProvider(RPC))
if not w3.is_connected():
    raise ConnectionError(f"Failed to connect to RPC: {RPC}")

chain_id = w3.eth.chain_id
balance = w3.eth.get_balance(signer.address) / 1e18

print(
    f"Chain: {chain_id}, Deployer: {signer.address}, Balance: {balance}"
)

def get_abi_from_etherscan(address):

    # The new etherscan v2 API docs: https://docs.etherscan.io/api-endpoints/contracts#get-contract-abi-for-verified-contract-source-codes
    url = f"{XSCAN_API_URI_ONLY}api?module=contract&action=getabi&address={address}&apikey={XSCAN_API_KEY}&chainid={XSCAN_CHAIN_ID}"

    try:
        response = requests.get(url)
        data = response.json()
        # v2 API: returns {"status":"1", "message":"OK", "result":{...}} or "result":{abi:[...]} or "result":"[...]"
        if data["status"] == "1" and data["message"] == "OK":
            result = data.get("result")
            
            # Case 1: result is a dict with "abi" key
            if isinstance(result, dict) and "abi" in result:
                abi = result["abi"]
                # Etherscan returns JSON string, Basescan returns already-parsed list
                if isinstance(abi, str):
                    abi = json.loads(abi)
                return abi
            
            # Case 2: result is a JSON string (most common case)
            elif isinstance(result, str):
                abi = json.loads(result)
                return abi
            
            # Case 3: result is already a list
            elif isinstance(result, list):
                return result
            
            else:
                raise ValueError(f"Unexpected result format: {type(result)}, raw: {data}")
        else:
            raise ValueError(f"Failed to fetch ABI: {data.get('message', 'Unknown error')}, raw: {data}")
    except Exception as e:
        raise Exception(f"Error fetching ABI from Xscan/Etherscan v2 API: {e}")

# USDC/AERO A20-15
fxswap_address = "0x3CeA080D303bD105c48cA4C24D8426da99f75524"
# https://basescan.org/address/0x3CeA080D303bD105c48cA4C24D8426da99f75524

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
    fxswap_addresses = {}


index = 9
fxswap_address = fxswap_addresses[index]["address"]

# Get fxswap contract ABI and create contract instance
fxswap_abi = get_abi_from_etherscan(fxswap_address)
fxswap_contract = w3.eth.contract(
    address=Web3.to_checksum_address(fxswap_address),
    abi=fxswap_abi
)

# Call name() function
pool_name = fxswap_contract.functions.name().call()
print(f"Pool name: {pool_name}")

# Standard ERC20 ABI for getting token info
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

# Get token addresses from pool
token0_address = fxswap_contract.functions.coins(0).call()
token1_address = fxswap_contract.functions.coins(1).call()

print(f"Token 0 address: {token0_address}")
print(f"Token 1 address: {token1_address}")

# Get token info (name and decimals)
token0_contract = w3.eth.contract(address=Web3.to_checksum_address(token0_address), abi=ERC20_ABI)
token1_contract = w3.eth.contract(address=Web3.to_checksum_address(token1_address), abi=ERC20_ABI)

token0_name = token0_contract.functions.name().call()
token0_decimals = token0_contract.functions.decimals().call()
token1_name = token1_contract.functions.name().call()
token1_decimals = token1_contract.functions.decimals().call()

print(f"Token 0: {token0_name} ({token0_decimals} decimals)")
print(f"Token 1: {token1_name} ({token1_decimals} decimals)")

# Common USDC addresses on different chains
USDC_ADDRESSES = [
    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Base USDC
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # Ethereum USDC
    "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",  # Optimism USDC
    "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # Arbitrum USDC
    "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",  # Base USDbC
]

# Check if tokens are USDC
token0_is_usdc = token0_address.lower() in [addr.lower() for addr in USDC_ADDRESSES]
token1_is_usdc = token1_address.lower() in [addr.lower() for addr in USDC_ADDRESSES]

# Get current pool state
current_balance_0 = fxswap_contract.functions.balances(0).call()
current_balance_1 = fxswap_contract.functions.balances(1).call()

# Get last_price from pool (price of token1 in terms of token0, scaled by 10^18)
last_price = fxswap_contract.functions.last_prices().call()
price_ratio = last_price / 10**18  # Price of token1 in terms of token0

# Get USD prices - calculate from last_price if one token is USDC, otherwise ask
token0_price_usd = None
token1_price_usd = None

if token0_is_usdc:
    token0_price_usd = 1.0
    print(f"{token0_name} is USDC, using price: $1.00")
    
    # last_price gives price of token1 in terms of token0 (USDC)
    # So token1_price_usd = price_ratio (since token0 is $1)
    token1_price_usd = price_ratio
    print(f"Calculated {token1_name} price from pool last_price: ${token1_price_usd:.6f} per {token1_name}")
    
elif token1_is_usdc:
    token1_price_usd = 1.0
    print(f"{token1_name} is USDC, using price: $1.00")
    
    # last_price gives price of token1 in terms of token0
    # Since token1 is USDC ($1), token0_price_usd = 1 / price_ratio
    token0_price_usd = 1.0 / price_ratio
    print(f"Calculated {token0_name} price from pool last_price: ${token0_price_usd:.6f} per {token0_name}")
    
else:
    # Neither token is USDC - ask for both prices
    print(f"\nNeither token is USDC. Please provide USD prices for both tokens.")
    
    while token0_price_usd is None:
        try:
            price_input = input(f"Enter USD price for {token0_name}: ").strip()
            token0_price_usd = float(price_input)
            if token0_price_usd <= 0:
                print("Price must be greater than 0. Please try again.")
                token0_price_usd = None
        except ValueError:
            print("Invalid price. Please enter a number.")
    
    while token1_price_usd is None:
        try:
            price_input = input(f"Enter USD price for {token1_name}: ").strip()
            token1_price_usd = float(price_input)
            if token1_price_usd <= 0:
                print("Price must be greater than 0. Please try again.")
                token1_price_usd = None
        except ValueError:
            print("Invalid price. Please enter a number.")

# Calculate USD value of 1 LP token (10**18)
one_lp_token = 10**18
current_total_supply = fxswap_contract.functions.totalSupply().call()

# Get current pool state (balances already retrieved above for price calculation)
print(f"Current balance(0): {current_balance_0 / 10**token0_decimals} {token0_name}")
print(f"Current balance(1): {current_balance_1 / 10**token1_decimals} {token1_name}")
print(f"Current totalSupply: {current_total_supply / 10**18} LP tokens")

# Calculate token amounts corresponding to 1 LP token
token0_per_lp = (current_balance_0 * one_lp_token) // current_total_supply
token1_per_lp = (current_balance_1 * one_lp_token) // current_total_supply

token0_per_lp_display = token0_per_lp / 10**token0_decimals
token1_per_lp_display = token1_per_lp / 10**token1_decimals

# Calculate USD value of 1 LP token
token0_value_usd_per_lp = token0_per_lp_display * token0_price_usd
token1_value_usd_per_lp = token1_per_lp_display * token1_price_usd
lp_token_usd_value = token0_value_usd_per_lp + token1_value_usd_per_lp

print(f"\nValue of 1 LP token ({one_lp_token / 10**18} LP):")
print(f"  - {token0_per_lp_display:.8f} {token0_name} = ${token0_value_usd_per_lp:.6f}")
print(f"  - {token1_per_lp_display:.8f} {token1_name} = ${token1_value_usd_per_lp:.6f}")
print(f"Total: ${lp_token_usd_value:.6f} per 1 LP token\n")

# Prompt user for USD value to refuel
prompt_val = None
while prompt_val is None:
    try:
        prompt_val = float(input(f"Enter USD value you want to refuel: ").strip())
        if prompt_val <= 0:
            print("Amount must be greater than 0. Please try again.")
            prompt_val = None
    except ValueError:
        print("Invalid input. Please enter a number.")

# Calculate LP token amount for that USD value
target_lp_tokens = int((prompt_val / lp_token_usd_value) * one_lp_token)
print(f"\nTarget LP tokens for ${prompt_val:.2f} USD: {target_lp_tokens / 10**18:.8f}")

# Calculate token amounts by simulating withdrawal of LP tokens
# Using the same formula as remove_liquidity: balances[i] * amount // total_supply
token0_amount = (current_balance_0 * target_lp_tokens) // current_total_supply
token1_amount = (current_balance_1 * target_lp_tokens) // current_total_supply


print(f"\nToken amounts from withdrawing {target_lp_tokens / 10**18} LP tokens:")
print(f"  token0_amount: {token0_amount / 10**token0_decimals} {token0_name}")
print(f"  token1_amount: {token1_amount / 10**token1_decimals} {token1_name}")

# Calculate total USD value
token0_value_usd = (token0_amount / 10**token0_decimals) * token0_price_usd
token1_value_usd = (token1_amount / 10**token1_decimals) * token1_price_usd
total_value_usd = token0_value_usd + token1_value_usd

print(f"\nTotal refuel value: {total_value_usd:.2f} USD")
print(f"  - {token0_name}: {token0_value_usd:.2f} USD (at ${token0_price_usd:.6f} per {token0_name})")
print(f"  - {token1_name}: {token1_value_usd:.2f} USD (at ${token1_price_usd:.6f} per {token1_name})")

# Check if refuel value is above 10 USD and prompt for confirmation
if total_value_usd > 10:
    print(f"\n⚠️  WARNING: Total refuel value is {total_value_usd:.2f} USD, which is above 10 USD!")
    response = input("Do you want to continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Refuel cancelled by user.")
        sys.exit(0)
    print("Continuing with refuel...")

# Verify: calculate how many LP tokens we'd get by adding these amounts back
calc_lp_share = fxswap_contract.functions.calc_token_amount([token0_amount, token1_amount], True).call()
print(f"\nVerification - LP tokens from re-adding:")
print(f"  Expected LP tokens: {calc_lp_share / 10**18}")
print(f"  Target LP tokens: {target_lp_tokens / 10**18}")
print(f"  Difference: {abs(calc_lp_share - target_lp_tokens) / 10**18}")
# Withdraw `calc_lp_share` from the pool to get the tokens we'll use to refuel.
# Use `remove_liquidity` method on the contract.
print("\nWithdrawing from pool to get refuel tokens...")

# Note: remove_liquidity(uint256 _burn_amount, uint256[2] memory min_amounts, address receiver)
# We'll use min_amounts as 0 (no slippage protection!) for demonstration, receiver is our signer address

min_amounts = [0, 0]  # You may want to tighten this in production

remove_liquidity_fn = fxswap_contract.functions.remove_liquidity(
    int(calc_lp_share),
    min_amounts,
    signer.address
)

# Estimate gas for withdrawal
try:
    withdraw_gas_estimate = remove_liquidity_fn.estimate_gas({'from': signer.address})
    print(f"Estimated gas for withdrawal: {withdraw_gas_estimate}")
    withdraw_gas_limit = int(withdraw_gas_estimate * 1.2)
except Exception as e:
    print(f"Warning: Could not estimate gas for withdrawal: {e}")
    withdraw_gas_limit = 300_000

# Build and sign withdrawal tx
withdraw_nonce = w3.eth.get_transaction_count(signer.address)
withdraw_tx = remove_liquidity_fn.build_transaction({
    'from': signer.address,
    'nonce': withdraw_nonce,
    'gas': withdraw_gas_limit,
    'gasPrice': w3.eth.gas_price,
    'chainId': chain_id,
})
signed_withdraw_txn = signer.sign_transaction(withdraw_tx)

# Send the withdrawal tx
print("Sending withdrawal transaction...")
withdraw_tx_hash = w3.eth.send_raw_transaction(signed_withdraw_txn.raw_transaction)
print(f"Withdrawal transaction hash: {withdraw_tx_hash.hex()}")

# Wait for withdrawal receipt
print("Waiting for withdrawal transaction receipt...")
withdraw_tx_receipt = w3.eth.wait_for_transaction_receipt(withdraw_tx_hash, timeout=300)
if withdraw_tx_receipt.status == 1:
    print("✓ Withdrawal successful! Tokens received.")
else:
    print("✗ Withdrawal failed!")
    print(f"Transaction receipt: {withdraw_tx_receipt}")
    sys.exit(1)

# Token addresses are already retrieved from the pool contract above
# coin0_address and coin1_address are defined earlier in the script

min_mint_amount = int(calc_lp_share) # no slippage
receiver = "0x0000000000000000000000000000000000000000"

print(f"\nTransaction parameters:")
print(f"  amounts: [{token0_amount}, {token1_amount}]")
print(f"  min_mint_amount: {min_mint_amount}")
print(f"  receiver: {receiver}")
print(f"  donation: True")

# Todo: check if approve for pool exists to get token sent


if SIM:
    print("WARNING: SIM mode (forking) is not directly supported in web3.py.")
    print("You would need to use a local node with fork capabilities (e.g., Anvil, Hardhat).")

# Build transaction
add_liquidity_function = fxswap_contract.functions.add_liquidity(
    [token0_amount, token1_amount],
    min_mint_amount,
    receiver,
    True  # donation
)

# Get fresh nonce and gas price after withdrawal (nonce has increased)
# Calculate nonce from withdrawal nonce + 1 to avoid race conditions
print("\nPreparing add_liquidity transaction...")
gas_price = w3.eth.gas_price
nonce = withdraw_nonce + 1
print(f"Using nonce: {nonce} (withdrawal used nonce {withdraw_nonce})")

# Estimate gas
try:
    gas_estimate = add_liquidity_function.estimate_gas({'from': signer.address})
    print(f"Estimated gas: {gas_estimate}")
    gas_limit = int(gas_estimate * 1.2)  # Add 20% buffer
except Exception as e:
    print(f"Warning: Could not estimate gas: {e}")
    gas_limit = 300_000  # Use default

# Build transaction
transaction = add_liquidity_function.build_transaction({
    'from': signer.address,
    'nonce': nonce,
    'gas': gas_limit,
    'gasPrice': gas_price,
    'chainId': chain_id,
})

# Sign transaction
signed_txn = signer.sign_transaction(transaction)

# Send transaction
print("\nSending transaction...")
tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
print(f"Transaction hash: {tx_hash.hex()}")

# Wait for transaction receipt
print("Waiting for transaction receipt...")
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

if tx_receipt.status == 1:
    print(f"✓ Transaction successful!")
    print(f"Block number: {tx_receipt.blockNumber}")
    print(f"Gas used: {tx_receipt.gasUsed}")
    print(f"Transaction receipt: {tx_receipt}")
else:
    print(f"✗ Transaction failed!")
    print(f"Transaction receipt: {tx_receipt}")