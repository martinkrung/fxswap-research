# GitHub Actions - Automated Data Collection

This repository uses GitHub Actions to automatically collect FXSwap pool data from Alchemy every hour and store it as Parquet files.

## Overview

The automated data collection workflow:
- **Runs hourly** at minute 19 (cron: `19 9-18/2 * * *`)
- Can be **manually triggered** via GitHub's Actions tab
- Collects data for all configured pools in `config/fxswaps.json`
- Uses specialized tools in the `tools/` directory for each chain
- Stores data as Parquet files in `data/{chain_name}/{pool_address}.parquet`
- Automatically commits and pushes updated data files and configuration
- Uploads execution logs as artifacts (retained for 30 days)

## Setup Instructions

### 1. Configure GitHub Secret

The workflow requires an Alchemy RPC URL to be stored as a GitHub secret:

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add a secret with:
   - **Name**: `ALCHEMY_RPC_URL`
   - **Value**: Your Alchemy RPC endpoint URL (e.g., `https://base-mainnet.g.alchemy.com/v2/YOUR_API_KEY`)

### 2. Enable GitHub Actions

1. Go to your repository's **Actions** tab
2. If Actions are disabled, click **"I understand my workflows, go ahead and enable them"**
3. The workflow will automatically run on the next hour

### 3. Manual Triggering

To manually trigger a data collection:

1. Go to **Actions** tab
2. Select **"Collect FXSwap Data Hourly"** workflow
3. Click **"Run workflow"**
4. Select the branch and click **"Run workflow"**

## Workflow Details

### Data Collection Process

The workflow uses the following tools:
1. `tools/get_data_base.py`: Iterates through all Base pools and fills missing data.
2. `tools/get_data_ethereum.py`: Iterates through all Ethereum pools and fills missing data.
3. `scripts/update_fxswap_blocks.py`: Updates `config/fxswaps.json` with the latest block metadata.

These tools internally utilize `scripts/fill_missing_fxswap_data.py` for efficient back-filling via Multicall.

### Commit Behavior

The workflow only creates a commit if there are actual changes to the data files or configuration:
- **Commit message format**: `chore: automated data collection - {timestamp}`
- **Changed files**: 
  - Updated `*.parquet` files in the `data/` directory
  - Updated `config/fxswaps.json`
- **Logs**: Not committed (available as workflow artifacts)

## Files Structure

```
.
├── .github/
│   └── workflows/
│       └── collect-data.yml          # GitHub Actions workflow definition
├── tools/
│   ├── get_data_base.py              # Base chain collection tool
│   └── get_data_ethereum.py          # Ethereum chain collection tool
├── config/
│   └── fxswaps.json                  # Pool configurations
├── data/
│   ├── base/                         # Base chain data
│   │   └── {pool_address}.parquet    # Parquet files per pool
│   └── ethereum/                     # Ethereum chain data
│       └── {pool_address}.parquet    # Parquet files per pool
├── scripts/
│   ├── fill_missing_fxswap_data.py   # Core back-fill logic
│   └── update_fxswap_blocks.py       # Metadata update script
└── requirements.txt                  # Python dependencies
```

## Local Testing

To test data collection locally:

```bash
# Set up environment
export RPC_BASE="your_base_rpc_url"
export RPC_ETHEREUM="your_eth_rpc_url"

# Run collection tools
python tools/get_data_base.py
python tools/get_data_ethereum.py
```
