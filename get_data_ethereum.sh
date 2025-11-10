# first source .env_ethereum
source .env_ethereum

# then get data
python scripts/get_historical_data.py --index 8
python scripts/get_historical_data.py --index 7