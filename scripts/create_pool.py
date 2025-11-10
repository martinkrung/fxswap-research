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
TWOCRYPTO_FACTORY = os.getenv('TWOCRYPTO_FACTORY')

print(f"XSCAN_API_KEY: {XSCAN_API_KEY}")
print(f"XSCAN_API_URI: {XSCAN_API_URI}")
print(f"RPC: {RPC}")
print(f"SINGER: {SINGER}")
print(f"STABLEPOOL_FACTORY: {TWOCRYPTO_FACTORY}")

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

factory_contract = boa.from_etherscan(
    TWOCRYPTO_FACTORY,
    name="stablepool_factory",
    chain_id=8453,
    api_key=XSCAN_API_KEY
)


print(factory_contract.admin())

coin0_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
coin1_address = "0x4200000000000000000000000000000000000006"

params = {
    "_name": "USDC/WETH A80-5 2",
    "_symbol": "USDC/WETH A80",
    "_coins": [coin0_address, coin1_address],
    "implementation_id": int(keccak(text="fx50").hex(), 16),
    "A": 80*10000,
    "gamma": int(10**18 * 0.001),  # irrelevant for fx pools
    "mid_fee": int(10**10 * 5 / 10_000),  # in bps
    "out_fee": int(10**10 * 20 / 10_000),  # in bps
    "fee_gamma": int(10**18 * 0.001),  # 0.003
    "allowed_extra_profit": int(10**18 * 1e-15),  # 1e-12
    "adjustment_step": int(10**18 * 1e-4),  # 1e-7
    "ma_exp_time": int(86400 / 24),  # 1h
    "initial_price": int(3465 * 10**18),  #
}

# USDC/WETH A2-5  A=20000, mid_fee=5, out_fee=10, fee in bps, adjustment_step 1e-7, allowed_extra_profit 1e-12
# USDC/WETH A5-5  A=50000, mid_fee=5, out_fee=10, fee in bps, adjustment_step 1e-7, allowed_extra_profit 1e-12
# USDC/WETH A20-5 A=200000, mid_fee=5, out_fee=10, fee in bps, adjustment_step 1e-7, allowed_extra_profit 1e-12
# USDC/WETH A40-5 A=400000, mid_fee=5, out_fee=10, fee in bps, adjustment_step 1e-7, allowed_extra_profit 1e-12
# old USDC/WETH A80-5 A=800000, mid_fee=5, out_fee=25, fee in bps, adjustment_step 1e-5, allowed_extra_profit 1e-11
# USDC/WETH A80-5 A=800000, mid_fee=5, out_fee=20, fee in bps, adjustment_step 1e-4, allowed_extra_profit 1e-15


print(f"Deploying pool with parameters:")
print(f"name: {params['_name']}")
print(f"symbol: {params['_symbol']}")
print(f"coins: {params['_coins']}")
print(f"implementation_id: {params['implementation_id']}")
print(f"A: {params['A']}")
print(f"gamma: {params['gamma']}")
print(f"mid_fee: {params['mid_fee']}")
print(f"out_fee: {params['out_fee']}")
print(f"fee_gamma: {params['fee_gamma']}")
print(f"allowed_extra_profit: {params['allowed_extra_profit']}")
print(f"adjustment_step: {params['adjustment_step']}")
print(f"ma_exp_time: {params['ma_exp_time']}")
print(f"initial_price: {params['initial_price']}")

if SIM:
    with boa.fork(RPC, allow_dirty=True):
        pool_address = factory_contract.deploy_pool(**params, sender=signer.address)
        print(f"Pool deployed to: {pool_address}")
else:
    pool_address = factory_contract.deploy_pool(
        **params, 
        sender=signer.address, 
        gas=5_500_000)
    print(f"Pool deployed to: {pool_address}")
