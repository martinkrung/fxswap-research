#!/bin/bash
set -euo pipefail

UPDATE_CONFIG=0
if [[ "${1:-}" == "--update-config" ]]; then
  UPDATE_CONFIG=1
  shift
fi

uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install vyper
uv pip install titanoboa pandas matplotlib numpy web3 eth-utils pyarrow parquet-tools seaborn scipy tqdm

if [[ ${UPDATE_CONFIG} -eq 1 ]]; then
  python scripts/update_fxswap_blocks.py "$@"
else
  echo "To populate first_liq_block and deployed_at_block run:"
  echo "  python scripts/update_fxswap_blocks.py --dry-run"
fi
