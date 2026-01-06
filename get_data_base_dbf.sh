# first source load environment variables
source .env_base

python scripts/get_historical_data.py --index 10
python scripts/get_historical_data.py --index 11
