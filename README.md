# Python Ethereum Development Environment


## some helper contract to help with fxswap research

Results are in plot folder and financial_statements folder:

<img width="787" height="1377" alt="USDC_WETHA5-5_pool_price_analysis_48h" src="https://github.com/user-attachments/assets/fb9a86cf-be45-4156-8875-3a0a821d3217" />

### Financial Statements

For each pool, the system generates comprehensive financial statements showing:
- **On Start**: Initial pool state with token amounts and USD values
- **Hodl**: What you would have if you just held the tokens
- **Impermanent Loss**: Calculation of IL with price ratios
- **Real Pool**: Actual pool state including fees earned
- **Refuel Events**: All refueling transactions with USD values
- **APR Calculations**: Annual percentage rate based on fees and time

Statements are generated for two timeframes:
- Full history (from start of data)
- Last 7 days

Outputs are saved as:
- CSV format (for spreadsheet applications)
- Markdown format (for easy reading)


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
source .env_base
```

## add the pool to plot data on config/fxswap.json

run with:

```bash
# get data
python scripts/get_historical_data.py --index=1

# To plot data for index 1, run:
python scripts/plot_refule.py --index=1
python scripts/plot_supply_shares.py --index=1

# To generate financial statements for index 1:
python scripts/generate_financial_statements.py --index=1

# Or use the automated scripts that do everything:
./plot_base.sh        # For all Base chain pools
./plot_ethereum.sh    # For Ethereum pools
./run_volatility_analysis.sh  # For all pools with volatility analysis
```
