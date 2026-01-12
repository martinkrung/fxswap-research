# GitHub Actions - Automated Data Collection

This repository uses GitHub Actions to automatically collect FXSwap pool data from Alchemy every hour and store it as Parquet files.

## Overview

The automated data collection workflow:
- **Runs hourly** at the top of each hour (cron: `0 * * * *`)
- Can be **manually triggered** via GitHub's Actions tab
- Collects data for all configured pools in `config/fxswaps.json`
- Stores data as Parquet files in `data/{chain_name}/{pool_address}.parquet`
- Automatically commits and pushes updated data files
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

The workflow iterates through all configured pool indices and:
1. Runs `scripts/get_historical_data.py --index={pool_index}`
2. Collects historical blockchain data via Alchemy RPC
3. Updates existing Parquet files with new data
4. Implements smart caching to avoid redundant API calls

### Pools Monitored

Based on `config/fxswaps.json`, the following pools are monitored:
- **Pool 0**: USDC/WETH A2-5 (Base)
- **Pool 1**: USDC/WETH A5-5 (Base)
- **Pool 2**: USDC/WETH A20-5 (Base)
- **Pool 3**: USDC/WETH A40-5 (Base)
- **Pool 4**: USDC/AERO A20-15 (Base)
- **Pool 5**: USDC/WETH A80-5 (Base)
- **Pool 6**: USDC/WETH A80-5 2 (Base)
- **Pool 9**: USDC/EURC A50-5 (Base)
- **Pool 10**: USDC/BRZ (Base)
- **Pool 11**: USDC/IDRX (Base)
- **Pool 12**: YB crvUSD/tBTC new (Ethereum)

### Commit Behavior

The workflow only creates a commit if there are actual changes to the data files:
- **Commit message format**: `chore: automated data collection - {timestamp}`
- **Changed files**: Only updated `*.parquet` files in the `data/` directory
- **Logs**: Not committed (available as workflow artifacts)

### Logs and Artifacts

Each workflow run produces a log file that includes:
- Start/end timestamps
- Data collection status for each pool
- Success/failure counts
- Detailed output from the collection script

Logs are uploaded as GitHub Actions artifacts and retained for 30 days.

## Monitoring

### Check Workflow Status

1. Go to the **Actions** tab
2. View recent workflow runs
3. Click on a run to see detailed logs
4. Download log artifacts for offline analysis

### Troubleshooting

**Workflow fails with authentication errors:**
- Verify the `ALCHEMY_RPC_URL` secret is correctly set
- Check that the Alchemy API key is valid and has sufficient quota

**No data changes committed:**
- This is normal if the cache already contains recent data
- The script implements smart caching to avoid redundant queries
- Check workflow logs to confirm data collection completed successfully

**Rate limiting issues:**
- The workflow includes a 2-second delay between pool queries
- If rate limiting persists, adjust the delay in `.github/workflows/collect-data.yml`

**Specific pool failures:**
- Check the workflow artifacts for detailed error logs
- Verify the pool configuration in `config/fxswaps.json`
- Ensure the RPC endpoint supports the required chain (Base or Ethereum)

## Files Structure

```
.
├── .github/
│   └── workflows/
│       └── collect-data.yml          # GitHub Actions workflow definition
├── config/
│   └── fxswaps.json                  # Pool configurations
├── data/
│   ├── base/                         # Base chain data
│   │   └── {pool_address}.parquet    # Parquet files per pool
│   └── ethereum/                     # Ethereum chain data
│       └── {pool_address}.parquet    # Parquet files per pool
├── logs/                             # Local logs (not committed)
│   └── data_collection_*.log         # Timestamped log files
├── scripts/
│   └── get_historical_data.py        # Data collection script
└── requirements.txt                  # Python dependencies
```

## Cost Considerations

- **GitHub Actions**: 2,000 minutes/month free for public repos
- **Hourly runs**: ~5-10 minutes per run = ~150-240 hours/month
- **Alchemy API**: Check your plan's request limits

## Customization

### Adjust Collection Frequency

Edit `.github/workflows/collect-data.yml`:

```yaml
on:
  schedule:
    - cron: '0 */2 * * *'  # Every 2 hours
    # - cron: '0 0 * * *'  # Daily at midnight
```

### Add/Remove Pools

1. Update `config/fxswaps.json` with pool configurations
2. Update `POOL_INDICES` array in `.github/workflows/collect-data.yml`

### Change Python Version

Edit the workflow file:

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.11'  # or your preferred version
```

## Local Testing

To test data collection locally before deploying:

```bash
# Set up environment
source .venv/bin/activate
export RPC="your_alchemy_rpc_url"

# Test single pool
python scripts/get_historical_data.py --index=0

# Test all pools
for i in 0 1 2 3 4 5 6 9 10 11 12; do
  python scripts/get_historical_data.py --index=$i
done
```

## Security Notes

- **Never commit** your Alchemy API key or RPC URL to the repository
- Always use GitHub Secrets for sensitive credentials
- The `.env*` pattern is already in `.gitignore` to prevent accidental commits
- Review workflow permissions regularly

## Support

For issues or questions:
1. Check workflow run logs in the Actions tab
2. Review the artifact logs for detailed error information
3. Ensure all prerequisites are met (secrets configured, Actions enabled)
4. Verify Alchemy API quota and rate limits
