#!/usr/bin/env python3

import boa
import json
import os
from getpass import getpass
from eth_account import account
import sys
"""
This script is used to refuel a Curve pool using the stablepool factory contract.
"""

# Load environment variables with `source .env_optimism`
XSCAN_API_URI = os.getenv('XSCAN_API_URI')
XSCAN_API_KEY = os.getenv('XSCAN_API_KEY')
XSCAN_CHAIN_ID = os.getenv('XSCAN_CHAIN_ID')

RPC = os.getenv('RPC')
SINGER = os.getenv('SINGER')

print(f"XSCAN_API_KEY: {XSCAN_API_KEY}")
print(f"XSCAN_API_URI: {XSCAN_API_URI}")
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

# set to True to fork the network
# set to False to use the actual network
SIM = True

# Setup boa environment
if SIM:
    boa.fork(RPC)
else:
    boa.set_network_env(RPC)
    boa.env.add_account(signer)

boa.env.eoa = signer.address

if not SIM:
    print(
        f"Chain: {boa.env.evm.patch.chain_id}, Deployer: {signer.address}, Balance: {boa.env.get_balance(signer.address)/1e18}"
    )

# ZCHF/crvUSD
# token 0 is crvUSD, token 1 is ZCHF !!!!!
fxswap_address = "0x027B40F5917FCd0eac57d7015e120096A5F92ca9"

fxswap_contract = boa.from_etherscan(
    fxswap_address,
    name="fxswap",
    chain_id=int(XSCAN_CHAIN_ID),
    api_key=XSCAN_API_KEY
)

print(f"pool name: {fxswap_contract.name()}")

# coin0_address = "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E" # crvUSD
# coin1_address = "0xB58E61C3098d85632Df34EecfB899A1Ed80921cB" # ZCHF

token0_balance = fxswap_contract.balances(0)
print(f"balance(0): {token0_balance/10**18} crvUSD")
token1_balance = fxswap_contract.balances(1)
print(f"balance(1): {token1_balance/10**18} ZCHF")  

last_price = fxswap_contract.last_prices()
print(f"last_price: {last_price/10**18}")

tvl = token0_balance + token1_balance * (last_price/10**18) # in USD
print(f"tvl: {tvl/10**18} USD")
# refuel for one week:

refuel_APY = 0.05 # 20% APY
refuel_amount_per_week = tvl * refuel_APY / 52
print(f"refuel_amount_per_week: {refuel_amount_per_week} USD")

# calculate the amount of crvUSD and ZCHF to refuel
token0_amount = refuel_amount_per_week / 2 # $

token1_amount = refuel_amount_per_week / (last_price/10**18) / 2 # ZCHF


token0_amount = int(token0_amount) # 
token1_amount = int(token1_amount) # 

print(f"token0_amount: {token0_amount/10**18} crvUSD")
print(f"token0_amount: {token0_amount} crvUSD as decimals")
print(f"token1_amount: {token1_amount/10**18} ZCHF")
print(f"token1_amount: {token1_amount} ZCHF as decimals")

min_mint_amount = fxswap_contract.calc_token_amount([token0_amount, token1_amount], True)

print(f"min_mint_amount: {min_mint_amount}")


params = {
    "amounts": [token0_amount, token1_amount],
    "min_mint_amount": min_mint_amount,
    "receiver": "0x0000000000000000000000000000000000000000",
    "donation": True,
}

print(params)

if not SIM:
    refuel_tx = fxswap_contract.add_liquidity(
        **params, 
        sender=signer.address,
        gas=300_000)
    print(refuel_tx)
else:
    with boa.fork(RPC, allow_dirty=True):
        refuel_tx = fxswap_contract.add_liquidity(**params, sender=signer.address)
        print(refuel_tx)