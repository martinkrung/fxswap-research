#!/bin/bash
# first source load environment variables
source .env
export RPC=$BASE_RPC
export XSCAN_API_KEY=$BASE_XSCAN_API_KEY

# Run the dynamic Python script
python3 get_data_base.py
