# first source load environment variables
source .env_base

python scripts/fill_missing_fxswap_data.py --index 13
python scripts/fill_missing_fxswap_data.py --index 14
python scripts/fill_missing_fxswap_data.py --index 15
python scripts/fill_missing_fxswap_data.py --index 16
python scripts/fill_missing_fxswap_data.py --index 17
python scripts/fill_missing_fxswap_data.py --index 10
python scripts/fill_missing_fxswap_data.py --index 11
python scripts/fill_missing_fxswap_data.py --index 9
python scripts/fill_missing_fxswap_data.py --index 5
python scripts/fill_missing_fxswap_data.py --index 4
python scripts/fill_missing_fxswap_data.py --index 3
python scripts/fill_missing_fxswap_data.py --index 2
python scripts/fill_missing_fxswap_data.py --index 1
python scripts/fill_missing_fxswap_data.py --index 0