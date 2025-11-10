#!/usr/bin/env python3

import boa
import json
import os
from getpass import getpass
from eth_account import account
import sys
import math
from eth_utils import keccak
"""
This script is used to deploy a Curve pool using the stablepool factory contract.
It unpacks the packed parameters from deployment data and calls the deploy_pool function.
"""

# Load environment variables with `source .env_optimism`
XSCAN_API_URI = os.getenv('XSCAN_API_URI')
XSCAN_API_KEY = os.getenv('XSCAN_API_KEY')
RPC = os.getenv('RPC')
SINGER = os.getenv('SINGER')

print(f"XSCAN_API_KEY: {XSCAN_API_KEY}")
print(f"XSCAN_API_URI: {XSCAN_API_URI}")
print(f"RPC: {RPC}")
print(f"SINGER: {SINGER}")

def account_load(fname):
    if fname == "babe":
        path = os.path.expanduser(os.path.join('~', '.brownie', 'accounts', fname + '.json'))
    else:
        path = os.path.expanduser(os.path.join('~', '.ape', 'accounts', fname + '.json'))
    print(f"Loading account from: {path}")
    with open(path, 'r') as f:
        pkey = account.decode_keyfile_json(json.load(f), getpass())
        acc = account.Account.from_key(pkey)
        print(f"Account loaded: {acc.address}")
        return acc


signer = account_load(SINGER)


SIM = False
'''
if not SIM:
    private_key = decrypt_private_key(os.environ.get("ENCRYPTED_PK"), getpass())
    if not private_key:
        raise ValueError("WEB3_TESTNET_PK not found in environment")
else:
    private_key = os.environ.get("WEB3_TESTNET_PK")
deployer = Account.from_key(private_key)
'''

# Setup boa environment
if SIM:
    boa.fork(RPC)
else:
#    boa.fork(RPC)
    boa.set_network_env(RPC)
    boa.env.add_account(signer)
boa.env.eoa = signer.address

print(
    f"Chain: {boa.env.evm.patch.chain_id}, Deployer: {signer.address}, Balance: {boa.env.get_balance(signer.address)/1e18}"
)


# USDC/AERO A20-15
fxswap_address = "0x3CeA080D303bD105c48cA4C24D8426da99f75524"
# https://basescan.org/address/0x3CeA080D303bD105c48cA4C24D8426da99f75524


fxswap_contract = boa.from_etherscan(
    fxswap_address,
    name="fxswap",
    chain_id=8453,
    api_key=XSCAN_API_KEY
)

token0_amount = int(4.99*10**6)  # $99.99
token1_amount = int(4*10**18) # 0.0012 AERO ~= $0.99 with price $0.99

# refule history
# $16 on 2025-11-31?, all pools were refuled
# $14.4 on 2025-11-03, all pools were refuled
# $14 on 2025-11-04, all pools were refuled


print(fxswap_contract.name())

# Target LP token amount: 0.1
target_lp_tokens = int(0.1 * 10**18)  # 0.1 LP tokens with 18 decimals
print(f"Target LP tokens: {target_lp_tokens / 10**18}")

# Get current pool state
current_balance_0 = fxswap_contract.balances(0)  # USDC (6 decimals)
current_balance_1 = fxswap_contract.balances(1)  # AERO (18 decimals)
current_total_supply = fxswap_contract.totalSupply()

print(f"Current balance(0): {current_balance_0 / 10**6} USDC")
print(f"Current balance(1): {current_balance_1 / 10**18} AERO")
print(f"Current totalSupply: {current_total_supply / 10**18} LP tokens")

# Calculate token amounts by simulating withdrawal of 0.1 LP tokens
# Using the same formula as remove_liquidity: balances[i] * amount // total_supply
# This gives us the exact token amounts that correspond to 0.1 LP tokens
token0_amount = (current_balance_0 * target_lp_tokens) // current_total_supply
token1_amount = (current_balance_1 * target_lp_tokens) // current_total_supply

print(f"\nToken amounts from withdrawing {target_lp_tokens / 10**18} LP tokens:")
print(f"  token0_amount: {token0_amount / 10**6} USDC")
print(f"  token1_amount: {token1_amount / 10**18} AERO")

# Verify: calculate how many LP tokens we'd get by adding these amounts back
calc_lp_share = fxswap_contract.calc_token_amount([token0_amount, token1_amount], True)
print(f"\nVerification - LP tokens from re-adding:")
print(f"  Expected LP tokens: {calc_lp_share / 10**18}")
print(f"  Target LP tokens: {target_lp_tokens / 10**18}")
print(f"  Difference: {abs(calc_lp_share - target_lp_tokens) / 10**18}")

coin0_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" # USDC
coin1_address = "0x940181a94A35A4569E4529A3CDfB74e38FD98631" # AERO

params = {
    "amounts": [token0_amount, token1_amount],
    "min_mint_amount": int(calc_lp_share),
    "receiver": "0x0000000000000000000000000000000000000000",
    "donation": True,
}

print(f"\nTransaction parameters:")
print(params)
sys.exit()
refuel_tx = fxswap_contract.add_liquidity(
    **params, 
    sender=signer.address,
    gas=300_000)

print(refuel_tx)

