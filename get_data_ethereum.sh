# first source load environment variables
source .env
export RPC=$ETHEREUM_RPC
export XSCAN_API_KEY=$ETHEREUM_XSCAN_API_KEY

# then get data

python scripts/fill_missing_fxswap_data.py --index 18
python scripts/fill_missing_fxswap_data.py --index 8
python scripts/fill_missing_fxswap_data.py --index 13
python scripts/fill_missing_fxswap_data.py --index 7
python scripts/fill_missing_fxswap_data.py --index 12
#python scripts/get_historical_data.py --index 7
