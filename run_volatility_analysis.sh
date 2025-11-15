#!/bin/bash

# Run volatility analysis for all pools in fxswaps.json
# This script generates volatility charts and analysis for each pool

echo "=========================================="
echo "FXSwap Volatility Analysis"
echo "=========================================="
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if config file exists
if [ ! -f "config/fxswaps.json" ]; then
    echo "ERROR: config/fxswaps.json not found!"
    exit 1
fi

# Count total number of pools
TOTAL_POOLS=$(python3 -c "import json; f=open('config/fxswaps.json'); d=json.load(f); print(len(d))")
echo "Found $TOTAL_POOLS pools to analyze"
echo ""

# Create plots and financial_statements directories if they don't exist
mkdir -p plots/base/volatility
mkdir -p plots/ethereum/volatility
mkdir -p financial_statements/base
mkdir -p financial_statements/ethereum

# Run analysis for each pool
SUCCESSFUL=0
FAILED=0

for i in $(seq 0 $((TOTAL_POOLS - 1))); do
    echo "[$((i+1))/$TOTAL_POOLS] Analyzing pool index $i..."

    # Get pool info
    POOL_INFO=$(python3 -c "import json; f=open('config/fxswaps.json'); d=json.load(f); p=d['$i']; print(f\"{p['name']} ({p['chain_name']})\")")
    echo "  Pool: $POOL_INFO"

    # Run the volatility analysis
    if python3 scripts/plot_volatility.py --index $i; then
        echo "  ✓ Volatility analysis success"

        # Generate financial statements
        if python3 scripts/generate_financial_statements.py --index $i; then
            echo "  ✓ Financial statements generated"
            SUCCESSFUL=$((SUCCESSFUL + 1))
        else
            echo "  ✗ Financial statements failed"
            FAILED=$((FAILED + 1))
        fi
    else
        echo "  ✗ Failed"
        FAILED=$((FAILED + 1))
    fi
    echo ""
done

echo "=========================================="
echo "Analysis Complete"
echo "=========================================="
echo "Successful: $SUCCESSFUL"
echo "Failed: $FAILED"
echo "Total: $TOTAL_POOLS"
echo ""
echo "Charts saved to:"
echo "  - plots/base/volatility/"
echo "  - plots/ethereum/volatility/"
echo ""
echo "Financial statements saved to:"
echo "  - financial_statements/base/"
echo "  - financial_statements/ethereum/"
echo "=========================================="
