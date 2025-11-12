# first source load environment variables
source .env_base

python scripts/get_historical_data.py --index 10
python scripts/get_historical_data.py --index 11
python scripts/get_historical_data.py --index 9
python scripts/get_historical_data.py --index 5
python scripts/get_historical_data.py --index 4
python scripts/get_historical_data.py --index 3
python scripts/get_historical_data.py --index 2
python scripts/get_historical_data.py --index 1
python scripts/get_historical_data.py --index 0