# first source load environment variables
source .env
export RPC=$ETHEREUM_RPC
export XSCAN_API_KEY=$ETHEREUM_XSCAN_API_KEY

# then plot data
python scripts/plot_refule.py --index=8
python scripts/plot_supply_shares.py --index=8
python scripts/plot_refule.py --index=7
python scripts/plot_supply_shares.py --index=7
python scripts/plot_refule.py --index=12
python scripts/plot_supply_shares.py --index=12