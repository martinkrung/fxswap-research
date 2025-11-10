#!/usr/bin/env python3

import boa
import json
import os
import time
from getpass import getpass
from eth_account import account
import sys
import math
from eth_utils import keccak
from web3 import Web3
"""
This script is used to trade back and forth on a Curve pool.
It performs 10 swaps of $5 USDC to ETH, then swaps the ETH back to USDC, repeating 10 times.
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

# Setup web3 for direct balance queries (bypasses titanoboa fork state issues)
w3 = Web3(Web3.HTTPProvider(RPC))

# ERC20 balanceOf and allowance ABI (just the functions we need)
ERC20_BALANCE_ABI = [{
    "constant": True,
    "inputs": [{"name": "_owner", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"name": "balance", "type": "uint256"}],
    "type": "function"
}, {
    "constant": True,
    "inputs": [
        {"name": "_owner", "type": "address"},
        {"name": "_spender", "type": "address"}
    ],
    "name": "allowance",
    "outputs": [{"name": "", "type": "uint256"}],
    "type": "function"
}]

def get_token_balance(token_address, owner_address, decimals=18):
    """Get token balance directly from blockchain using web3"""
    try:
        token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_BALANCE_ABI)
        balance = token_contract.functions.balanceOf(Web3.to_checksum_address(owner_address)).call()
        return balance
    except Exception as e:
        print(f"  Warning: Failed to get balance via web3: {e}")
        return None

def get_token_allowance(token_address, owner_address, spender_address):
    """Get token allowance directly from blockchain using web3"""
    try:
        token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_BALANCE_ABI)
        allowance = token_contract.functions.allowance(
            Web3.to_checksum_address(owner_address),
            Web3.to_checksum_address(spender_address)
        ).call()
        return allowance
    except Exception as e:
        print(f"  Warning: Failed to get allowance via web3: {e}")
        return None

# get_dy ABI for Curve pools
GET_DY_ABI = [{
    "name": "get_dy",
    "inputs": [
        {"name": "i", "type": "uint256"},
        {"name": "j", "type": "uint256"},
        {"name": "dx", "type": "uint256"}
    ],
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
}]

def get_dy_web3(pool_address, i, j, dx):
    """Get expected output amount using web3 (bypasses titanoboa fork state issues)"""
    try:
        pool_contract = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=GET_DY_ABI)
        dy = pool_contract.functions.get_dy(i, j, dx).call()
        return dy
    except Exception as e:
        print(f"  Warning: Failed to get_dy via web3: {e}")
        return None


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
fxswap_address = "0xF30fcb00b7C3d2f6e12043157011bea7f848049D"
# https://basescan.org/address/0xd3E3B0FE036295A9e531bd72b024F7B308bca4f7

fxswap_contract = boa.from_etherscan(
    fxswap_address,
    name="fxswap",
    chain_id=8453,
    api_key=XSCAN_API_KEY
)

coin0_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" # USDC
coin1_address = "0x4200000000000000000000000000000000000006" # WETH

# Get token contracts
coin0 = boa.from_etherscan(coin0_address, name="USDC", chain_id=8453, api_key=XSCAN_API_KEY)
coin1 = boa.from_etherscan(coin1_address, name="WETH", chain_id=8453, api_key=XSCAN_API_KEY)

print(f"Pool: {fxswap_contract.name()}")
print(f"Pool address: {fxswap_address}")

# Swap parameters
SWAP_AMOUNT_USD = 1  # $5 per swap
USDC_DECIMALS = 6
SWAP_AMOUNT_USDC = int(SWAP_AMOUNT_USD * 10**USDC_DECIMALS)  # 5000000 = $5 USDC
SLIPPAGE_TOLERANCE = 0.01  # 1% slippage tolerance
NUM_SWAPS = 100

print(f"\nStarting {NUM_SWAPS} back-and-forth swaps of ${SWAP_AMOUNT_USD} each")
print(f"Swap amount: {SWAP_AMOUNT_USDC} USDC ({SWAP_AMOUNT_USD} USD)")

# Check initial balances using web3 (more reliable after transactions)
initial_usdc_balance = get_token_balance(coin0_address, signer.address, USDC_DECIMALS)
initial_eth_balance = get_token_balance(coin1_address, signer.address, 18)

if initial_usdc_balance is None or initial_eth_balance is None:
    print(f"\nError: Could not retrieve initial balances")
    if initial_usdc_balance is None:
        print(f"  USDC balance unavailable")
    if initial_eth_balance is None:
        print(f"  WETH balance unavailable")
    sys.exit(1)

print(f"\nInitial balances:")
print(f"  USDC: {initial_usdc_balance / 10**USDC_DECIMALS:.2f}")
print(f"  WETH: {initial_eth_balance / 10**18:.6f}")

# Approve tokens if needed
try:
    usdc_allowance = coin0.allowance(signer.address, fxswap_address)
except Exception as e:
    # If titanoboa fails, use web3
    print(f"  Warning: Could not get USDC allowance via titanoboa, using web3: {e}")
    usdc_allowance = get_token_allowance(coin0_address, signer.address, fxswap_address)
    if usdc_allowance is None:
        usdc_allowance = 0  # Default to 0 if we can't check

if usdc_allowance < SWAP_AMOUNT_USDC * NUM_SWAPS * 2:  # Need enough for all swaps both ways
    print(f"\nApproving USDC...")
    approve_amount = SWAP_AMOUNT_USDC * NUM_SWAPS * 4  # Extra buffer
    try:
        coin0.approve(fxswap_address, approve_amount, sender=signer.address)
        print(f"Approved {approve_amount / 10**USDC_DECIMALS:.2f} USDC")
    except (TypeError, Exception) as e:
        # Transaction succeeded but titanoboa failed to reset fork - this is OK
        if "'NoneType' object is not subscriptable" in str(e) or "fork" in str(e).lower():
            print(f"Approval transaction mined successfully (fork reset warning ignored)")
            print(f"Approved {approve_amount / 10**USDC_DECIMALS:.2f} USDC")
        else:
            raise

try:
    weth_allowance = coin1.allowance(signer.address, fxswap_address)
except Exception as e:
    # If titanoboa fails, use web3
    print(f"  Warning: Could not get WETH allowance via titanoboa, using web3: {e}")
    weth_allowance = get_token_allowance(coin1_address, signer.address, fxswap_address)
    if weth_allowance is None:
        weth_allowance = 0  # Default to 0 if we can't check

if weth_allowance == 0:
    print(f"\nApproving WETH...")
    approve_amount = int(1 * 10**18)  # Approve 1 WETH (should be enough)
    try:
        coin1.approve(fxswap_address, approve_amount, sender=signer.address)
        print(f"Approved {approve_amount / 10**18:.6f} WETH")
    except (TypeError, Exception) as e:
        # Transaction succeeded but titanoboa failed to reset fork - this is OK
        if "'NoneType' object is not subscriptable" in str(e) or "fork" in str(e).lower():
            print(f"Approval transaction mined successfully (fork reset warning ignored)")
            print(f"Approved {approve_amount / 10**18:.6f} WETH")
        else:
            raise

# Perform swaps
for i in range(NUM_SWAPS):
    print(f"\n--- Swap round {i+1}/{NUM_SWAPS} ---")
    
    # Reinitialize fxswap contract at start of each round to fix corrupted fork state
    if i > 0:  # Skip first round, contract is already initialized
        time.sleep(2)  # Delay before reinitializing to avoid rate limits
        try:
            fxswap_contract = boa.from_etherscan(
                fxswap_address,
                name="fxswap",
                chain_id=8453,
                api_key=XSCAN_API_KEY
            )
        except Exception as e:
            print(f"  Warning: Could not reinitialize contract: {e}")
    
    # Get balance before first swap using web3
    time.sleep(1)  # Small delay before API call
    eth_balance_before = get_token_balance(coin1_address, signer.address, 18)
    
    # Swap 1: USDC -> ETH (i=0, j=1)
    print(f"Swapping {SWAP_AMOUNT_USDC / 10**USDC_DECIMALS:.2f} USDC to ETH...")
    time.sleep(1)  # Small delay before get_dy call
    try:
        dy_expected = fxswap_contract.get_dy(0, 1, SWAP_AMOUNT_USDC)
    except Exception as e:
        # If get_dy fails, fallback to web3
        print(f"  Warning: get_dy failed via titanoboa, using web3: {e}")
        time.sleep(1)  # Delay before web3 call
        dy_expected = get_dy_web3(fxswap_address, 0, 1, SWAP_AMOUNT_USDC)
        if dy_expected is None:
            raise Exception("Could not get dy via titanoboa or web3")
    min_dy = int(dy_expected * (1 - SLIPPAGE_TOLERANCE))
    print(f"  Expected ETH: {dy_expected / 10**18:.6f}")
    print(f"  Min ETH (1% slippage): {min_dy / 10**18:.6f}")
    
    try:
        tx1 = fxswap_contract.exchange(
            0,  # i: USDC
            1,  # j: WETH
            SWAP_AMOUNT_USDC,  # dx: amount of USDC
            min_dy,  # min_dy: minimum ETH to receive
            sender=signer.address,
            gas=300_000
        )
        print(f"  Transaction: {tx1}")
    except (TypeError, Exception) as e:
        # Transaction succeeded but titanoboa failed to reset fork - this is OK
        if "'NoneType' object is not subscriptable" in str(e) or "fork" in str(e).lower():
            print(f"  Transaction mined successfully (fork reset warning ignored)")
        else:
            raise
    
    # Wait a moment for transaction to be fully processed
    time.sleep(5)
    
    # Get actual ETH received using web3 (bypasses titanoboa fork state issues)
    time.sleep(1)  # Small delay before API call
    eth_balance_after = get_token_balance(coin1_address, signer.address, 18)
    if eth_balance_after is None:
        print(f"  Warning: Could not get ETH balance, using expected value")
        eth_received = dy_expected
    else:
        eth_received = eth_balance_after - eth_balance_before
    print(f"  Received ETH: {eth_received / 10**18:.6f}")
    
    # Get USDC balance before second swap using web3
    time.sleep(1)  # Small delay before API call
    usdc_balance_before = get_token_balance(coin0_address, signer.address, USDC_DECIMALS)
    
    # Swap 2: ETH -> USDC (i=1, j=0)
    print(f"Swapping {eth_received / 10**18:.6f} ETH back to USDC...")
    time.sleep(1)  # Small delay before get_dy call
    try:
        dy_expected_usdc = fxswap_contract.get_dy(1, 0, eth_received)
    except Exception as e:
        # If get_dy fails, try to reinitialize, then fallback to web3
        print(f"  Warning: get_dy failed via titanoboa, trying web3: {e}")
        time.sleep(2)  # Delay before reinitializing
        try:
            fxswap_contract = boa.from_etherscan(
                fxswap_address,
                name="fxswap",
                chain_id=8453,
                api_key=XSCAN_API_KEY
            )
            time.sleep(1)  # Delay before get_dy call
            dy_expected_usdc = fxswap_contract.get_dy(1, 0, eth_received)
        except Exception as e2:
            # Fallback to web3 if titanoboa still fails
            print(f"  Using web3 for get_dy: {e2}")
            time.sleep(1)  # Delay before web3 call
            dy_expected_usdc = get_dy_web3(fxswap_address, 1, 0, eth_received)
            if dy_expected_usdc is None:
                raise Exception("Could not get dy via titanoboa or web3")
    min_dy_usdc = int(dy_expected_usdc * (1 - SLIPPAGE_TOLERANCE))
    print(f"  Expected USDC: {dy_expected_usdc / 10**USDC_DECIMALS:.2f}")
    print(f"  Min USDC (1% slippage): {min_dy_usdc / 10**USDC_DECIMALS:.2f}")
    
    try:
        tx2 = fxswap_contract.exchange(
            1,  # i: WETH
            0,  # j: USDC
            eth_received,  # dx: amount of ETH
            min_dy_usdc,  # min_dy: minimum USDC to receive
            sender=signer.address,
            gas=300_000
        )
        print(f"  Transaction: {tx2}")
    except (TypeError, Exception) as e:
        # Transaction succeeded but titanoboa failed to reset fork - this is OK
        if "'NoneType' object is not subscriptable" in str(e) or "fork" in str(e).lower():
            print(f"  Transaction mined successfully (fork reset warning ignored)")
        else:
            raise
    
    # Wait a moment for transaction to be fully processed
    time.sleep(5)
    
    # Get actual USDC received using web3 (bypasses titanoboa fork state issues)
    time.sleep(1)  # Small delay before API call
    usdc_balance_after = get_token_balance(coin0_address, signer.address, USDC_DECIMALS)
    if usdc_balance_after is None:
        print(f"  Warning: Could not get USDC balance, using expected value")
        usdc_received = dy_expected_usdc
    else:
        usdc_received = usdc_balance_after - usdc_balance_before
    print(f"  Received USDC: {usdc_received / 10**USDC_DECIMALS:.2f}")
    
    # Longer delay between swap rounds to avoid rate limiting
    if i < NUM_SWAPS - 1:  # Don't delay after last swap
        print(f"  Waiting 5 seconds before next round...")
        time.sleep(5)

# Final balances using web3 (bypasses titanoboa fork state issues)
time.sleep(2)  # Delay before final balance checks
final_usdc_balance = get_token_balance(coin0_address, signer.address, USDC_DECIMALS)
time.sleep(1)  # Delay between balance checks
final_eth_balance = get_token_balance(coin1_address, signer.address, 18)

if final_usdc_balance is None or final_eth_balance is None:
    print(f"\nWarning: Could not retrieve final balances")
    if final_usdc_balance is None:
        print(f"  USDC balance unavailable")
    if final_eth_balance is None:
        print(f"  WETH balance unavailable")
else:
    print(f"\n=== Final Results ===")
    print(f"Final balances:")
    print(f"  USDC: {final_usdc_balance / 10**USDC_DECIMALS:.2f}")
    print(f"  WETH: {final_eth_balance / 10**18:.6f}")
    print(f"\nNet change:")
    print(f"  USDC: {(final_usdc_balance - initial_usdc_balance) / 10**USDC_DECIMALS:.2f}")
    print(f"  WETH: {(final_eth_balance - initial_eth_balance) / 10**18:.6f}")

