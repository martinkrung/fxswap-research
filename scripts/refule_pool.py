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


# USDC/WETH A2-5
fxswap_address = "0x4de88ecfa7f6548aA0d5C6D01b381Ea917E71F73"
# https://basescan.org/address/0x4de88ecfa7f6548aA0d5C6D01b381Ea917E71F73
# USDC/WETH A5-5
#fxswap_address = "0xC88768B569902e1A67E54b090bA4969fde1204FA"
# https://basescan.org/address/0xC88768B569902e1A67E54b090bA4969fde1204FA
# USDC/WETH A20-5
#fxswap_address = "0x3D0143f6453a707b840b6565F959D6cbBA86F23e"
# https://basescan.org/address/0x3D0143f6453a707b840b6565F959D6cbBA86F23e
# USDC/WETH A40-5
#fxswap_address = "0x993a0D30FfA321D32eD0E8272Ded0108eBb1099A"
# https://basescan.org/address/0x993a0D30FfA321D32eD0E8272Ded0108eBb1099A

# USDC/WETH A80-5
fxswap_address = "0xd3E3B0FE036295A9e531bd72b024F7B308bca4f7"
# https://basescan.org/address/0xd3E3B0FE036295A9e531bd72b024F7B308bca4f7

fxswap_address = "0xF30fcb00b7C3d2f6e12043157011bea7f848049D"

fxswap_contract = boa.from_etherscan(
    fxswap_address,
    name="fxswap",
    chain_id=8453,
    api_key=XSCAN_API_KEY
)

token0_amount = int(4*10**6)  # $4
token1_amount = int(0.00121773*10**18) # 0.0012 ETH ~= $4 with price $3465

# refule history
# $16 on 2025-11-31?, all pools were refuled
# $14.4 on 2025-11-03, all pools were refuled
# $14 on 2025-11-04, all pools were refuled


print(fxswap_contract.name())

calc_lp_share = fxswap_contract.calc_token_amount([token0_amount, token1_amount], True)
print(calc_lp_share)

coin0_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" # USDC
coin1_address = "0x4200000000000000000000000000000000000006" # WETH

params = {
    "amounts": [token0_amount, token1_amount],  # 4 USDC, 0.001 WETH
    "min_mint_amount": calc_lp_share,
    "receiver": "0x0000000000000000000000000000000000000000",
    "donation": True,
}

print(params)
sys.exit()
refuel_tx = fxswap_contract.add_liquidity(
    **params, 
    sender=signer.address,
    gas=300_000)

print(refuel_tx)

