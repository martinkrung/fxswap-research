# Python Ethereum Development Environment


## some helper contract to help with fxswap research

Results are in plot folder:

<img width="787" height="1377" alt="USDC_WETHA5-5_pool_price_analysis_48h" src="https://github.com/user-attachments/assets/fb9a86cf-be45-4156-8875-3a0a821d3217" />


## Automated Data Collection

This repository includes a GitHub Actions workflow that automatically collects FXSwap pool data from Alchemy every hour. The data is stored as Parquet files and automatically committed to the repository.

### Quick Setup

1. Add your Alchemy RPC URL as a GitHub secret named `ALCHEMY_RPC_URL`
2. Enable GitHub Actions in your repository settings
3. The workflow will run automatically every hour

For detailed setup instructions, see [GITHUB_ACTIONS.md](GITHUB_ACTIONS.md).

## Installation

### Quick Install

Use our installation script to set up everything automatically:

```bash
chmod +x install.sh
./install.sh
```

## Usage

After installation, make sure your virtual environment is activated. Copy example.env and update with your data.


```bash
source .venv/bin/activate
source .env
```

## Add the pool to plot data on config/fxswap.json

run with:

```bash
# get data
python scripts/get_historical_data.py --index=1

# To plot data for index 1, run:
python scripts/plot_refule.py --index=1
python scripts/plot_supply_shares.py --index=1
```

## Adding a New Pool

### 1. Add pool entry to `config/fxswaps.json`

Pick the next available numeric index and add an entry:

```json
"21": {
    "name": "TOKEN0/TOKEN1 A20-5",
    "chain_name": "base",
    "chain_id": 8453,
    "address": "0xYourPoolAddress",
    "explorer": "https://basescan.org/address/0xYourPoolAddress",
    "curve": "https://www.curve.finance/dex/base/pools/factory-twocrypto-XXX/deposit",
    "deployed_at_block": 12345678
}
```

Required fields:
- **name** — human-readable pool name
- **chain_name** — lowercase chain identifier (e.g. `base`, `ethereum`, `gnosis`)
- **chain_id** — numeric chain ID (`8453` for Base, `1` for Ethereum, `100` for Gnosis)
- **address** — checksummed pool contract address
- **deployed_at_block** — block number at which the pool was deployed

Optional fields:
- **explorer** — block explorer URL
- **curve** — Curve UI deposit link
- **first_liq_block** — block of first liquidity (filled in step 3)

### 2. If adding a new chain: configure env and update scripts

Add RPC and explorer env vars to your `.env`:

```bash
export NEWCHAIN_RPC="https://your-rpc-url"
export XSCAN_API_KEY="yourapikey"
```

Then add entries to `scripts/update_data.py`:

- **`STRIDES`** — blocks between data points (e.g. `100` for fast chains, `20` for Ethereum):
  ```python
  STRIDES = {
      8453: 100,  # Base
      1: 20,      # Ethereum
      100: 20,    # Gnosis  <-- add new chain
  }
  ```
- **`RPC_ENV_HINTS`** — env var names the script checks for the RPC URL:
  ```python
  RPC_ENV_HINTS = {
      ...
      "gnosis": ("GNOSIS_RPC", "GNOSIS_RPC_URL", "RPC_GNOSIS", "RPC"),  # <-- add new chain
  }
  ```

### 3. Find the first liquidity block

```bash
python tools/find_first_liquidity.py --index=21
```

This binary-searches for the first block where `totalSupply > 0`. Copy the result into `first_liq_block` in `config/fxswaps.json`.

### 4. Fetch historical data

```bash
python scripts/get_historical_data.py --index=21
```

Data is saved as a Parquet file under `data/<chain_name>/<address>.parquet`.

### 5. Generate plots

```bash
python scripts/plot_refule.py --index=21
python scripts/plot_supply_shares.py --index=21
```

Plots are written to the `plot/` folder.
