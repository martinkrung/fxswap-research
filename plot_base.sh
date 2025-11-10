# first source load environment variables
source .env_base

# then plot data
python scripts/plot_refule.py --index=6
python scripts/plot_supply_shares.py --index=6
python scripts/plot_refule.py --index=5
python scripts/plot_supply_shares.py --index=5
python scripts/plot_refule.py --index=4
python scripts/plot_supply_shares.py --index=4
python scripts/plot_refule.py --index=3
python scripts/plot_supply_shares.py --index=3
python scripts/plot_refule.py --index=2
python scripts/plot_supply_shares.py --index=2
python scripts/plot_refule.py --index=1
python scripts/plot_supply_shares.py --index=1
python scripts/plot_refule.py --index=0
python scripts/plot_supply_shares.py --index=0