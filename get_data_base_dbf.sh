# first source load environment variables
source .env
export RPC=$BASE_RPC
export XSCAN_API_KEY=$BASE_XSCAN_API_KEY

python scripts/get_historical_data.py --index 10
python scripts/get_historical_data.py --index 11
