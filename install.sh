#!/bin/bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install vyper
uv pip install titanoboa pandas matplotlib numpy web3 eth-utils pyarrow parquet-tools
