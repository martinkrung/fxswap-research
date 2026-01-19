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

## add the pool to plot data on config/fxswap.json

run with:

```bash
# get data
python scripts/get_historical_data.py --index=1

# To plot data for index 1, run:
python scripts/plot_refule.py --index=1
python scripts/plot_supply_shares.py --index=1
```
