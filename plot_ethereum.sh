# first source .env_ethereum
source .env_ethereum

# then plot data
python scripts/plot_refule.py --index=8
python scripts/plot_supply_shares.py --index=8
python scripts/plot_refule.py --index=7
python scripts/plot_supply_shares.py --index=7