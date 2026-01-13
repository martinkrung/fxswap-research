#!/usr/bin/env python3
"""Update fxswap config with earliest cached blocks and deployment blocks.

This utility augments each entry inside ``config/fxswaps.json`` with two new
fields:

``first_block``
    The earliest ``block_number`` present in the cached Parquet dataset for the
    pool (if available).

``deployed_at_block``
    The block number where the swap contract bytecode first appeared on-chain.

Usage examples
--------------

    # Dry-run (no file modifications), summary only
    ./scripts/update_fxswap_blocks.py --dry-run

    # Update the config file in-place, writing a backup copy first
    ./scripts/update_fxswap_blocks.py --backup

    # Provide explicit RPC endpoints (otherwise environment variables are used)
    ./scripts/update_fxswap_blocks.py --rpc-base "https://..." --rpc-ethereum "https://..."

Requirements:
    - ``pyarrow`` (to stream Parquet files efficiently)
    - ``web3``
    - Working RPC endpoints for each chain referenced in the config.

Environment discovery
---------------------
For each chain the script automatically looks for RPC endpoints in the
following order (unless an explicit ``--rpc-<chain>`` argument is provided):

1. ``.env_<chain>`` at the project root (e.g. ``.env_base`` or ``.env_ethereum``)
   – keys inspected: ``RPC``, plus any chain-specific variants such as
   ``BASE_RPC_URL``.
2. Process environment variables (same key order as above).

If multiple chains are processed and only a generic ``RPC`` variable is found in
step 2, the script aborts with an explicit error to avoid ambiguity.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


try:
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(
        "pyarrow is required to inspect cached Parquet files. Install it via `pip install pyarrow`."
    ) from exc

try:
    from web3 import Web3
    from web3.exceptions import BlockNotFound

    try:
        from web3.middleware import (
            geth_poa_middleware as _poa_middleware,  # type: ignore[attr-defined]
        )
    except ImportError:
        from web3.middleware.proof_of_authority import (
            ExtraDataToPOAMiddleware as _poa_middleware,  # type: ignore[import-not-found]
        )
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(
        "web3 is required to query deployment blocks. Install it via `pip install web3`."
    ) from exc

POA_MIDDLEWARE = _poa_middleware


DEFAULT_CONFIG = Path("config/fxswaps.json")
DEFAULT_DATA_DIR = Path("data")

# Mapping of chain_name -> candidate environment variable names for RPC URLs.
RPC_ENV_HINTS: dict[str, tuple[str, ...]] = {
    "base": ("BASE_RPC_URL", "BASE_RPC", "RPC_BASE", "RPC"),
    "ethereum": (
        "ETHEREUM_RPC_URL",
        "MAINNET_RPC_URL",
        "ETH_RPC",
        "RPC_ETHEREUM",
        "RPC",
    ),
}

ROOT_DIR = Path(__file__).resolve().parent.parent


def env_file_for_chain(chain: str) -> Path:
    chain_norm = re.sub(r"[^a-z0-9]", "", chain.lower())
    return ROOT_DIR / f".env_{chain_norm}"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and value[0] in {'"', "'"} and value[-1:] == value[0]:
            value = value[1:-1]
        # Remove inline comments that follow at least one whitespace
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def candidate_keys_for_chain(chain: str) -> Sequence[str]:
    hints = RPC_ENV_HINTS.get(chain.lower(), ())
    # Ensure "RPC" is checked first to support simple .env exports
    unique_keys = ["RPC"]
    for key in hints:
        if key not in unique_keys:
            unique_keys.append(key)
    return tuple(unique_keys)


@dataclass
class PoolMetadata:
    """Computed metadata for a single pool entry."""

    first_block: int | None
    deployed_at_block: int | None
    parquet_path: Path | None


class RpcRegistry:
    """Resolve and cache Web3 providers per chain."""

    def __init__(self, args: argparse.Namespace, chains: Iterable[str]) -> None:
        self._args = args
        self._chains = {chain.lower() for chain in chains}
        self._providers: dict[str, Web3] = {}
        self._resolved_urls: dict[str, str] = {}
        self._env_cache: dict[str, dict[str, str]] = {}
        self._resolve_urls()

    def _load_chain_env(self, chain: str) -> dict[str, str]:
        if chain not in self._env_cache:
            path = env_file_for_chain(chain)
            self._env_cache[chain] = load_env_file(path)
        return self._env_cache[chain]

    def _resolve_urls(self) -> None:
        ambiguous_chains = len(self._chains) > 1
        for chain in self._chains:
            explicit = getattr(self._args, f"rpc_{chain}", None)
            if explicit:
                self._resolved_urls[chain] = explicit
                continue

            env_values = self._load_chain_env(chain)
            for key in candidate_keys_for_chain(chain):
                value = env_values.get(key)
                if value:
                    self._resolved_urls[chain] = value
                    break
            if chain in self._resolved_urls:
                continue

            for key in candidate_keys_for_chain(chain):
                value = os.getenv(key)
                if value:
                    if key == "RPC" and ambiguous_chains:
                        raise SystemExit(
                            "Environment variable RPC is ambiguous across multiple chains. "
                            "Provide chain-specific variables, per-chain .env files, or --rpc-<chain> arguments."
                        )
                    self._resolved_urls[chain] = value
                    break
            if chain not in self._resolved_urls:
                env_path = env_file_for_chain(chain)
                raise SystemExit(
                    f"No RPC endpoint found for chain '{chain}'. Provide --rpc-{chain}, set one of "
                    f"{', '.join(candidate_keys_for_chain(chain))}, or add it to {env_path}."
                )

    def get(self, chain: str) -> Web3:
        chain_lower = chain.lower()
        if chain_lower not in self._resolved_urls:
            raise SystemExit(f"No RPC endpoint configured for chain '{chain_lower}'.")
        if chain_lower not in self._providers:
            url = self._resolved_urls[chain_lower]
            logging.info("Creating Web3 provider for %s", chain_lower)
            provider = Web3(Web3.HTTPProvider(url))
            if chain_lower in {"base", "arb", "arbitrum", "polygon", "bsc"}:
                provider.middleware_onion.inject(POA_MIDDLEWARE, layer=0)
            self._providers[chain_lower] = provider
        return self._providers[chain_lower]


def build_parquet_index(data_dir: Path) -> dict[str, Path]:
    """Return mapping of lowercase address -> Parquet file path."""
    if not data_dir.exists():
        raise SystemExit(f"Data directory not found: {data_dir}")

    index: dict[str, Path] = {}
    for path in data_dir.rglob("*.parquet"):
        index[path.stem.lower()] = path
    return index


def find_first_block(parquet_path: Path) -> int | None:
    """Stream Parquet batches to locate the minimum block number."""
    try:
        parquet_file = pq.ParquetFile(parquet_path)
    except FileNotFoundError:
        logging.warning("Parquet file missing: %s", parquet_path)
        return None
    except Exception as exc:  # pragma: no cover - unexpected parquet failure
        logging.error("Failed to open %s: %s", parquet_path, exc)
        return None

    min_block: int | None = None
    try:
        for batch in parquet_file.iter_batches(
            columns=["block_number"], batch_size=50_000
        ):
            if batch.num_rows == 0:
                continue
            column = batch.column(0)
            try:
                batch_min = column.min()
            except AttributeError:
                # Fallback for older pyarrow versions
                batch_min = min(
                    (val for val in column.to_pylist() if val is not None), default=None
                )
            if batch_min is None:
                continue
            candidate = int(batch_min)
            min_block = candidate if min_block is None else min(min_block, candidate)
    except KeyError:
        logging.warning("Column 'block_number' not found in %s", parquet_path)
        return None
    except Exception as exc:  # pragma: no cover - unexpected streaming failure
        logging.error("Failed to stream %s: %s", parquet_path, exc)
        return None

    return min_block


def contract_deployment_block(
    web3: Web3, address: str, hint_block: int | None = None
) -> int | None:
    """Binary-search the first block containing contract bytecode."""
    checksum = Web3.to_checksum_address(address)
    try:
        latest_block = web3.eth.block_number
    except Exception as exc:  # pragma: no cover - RPC failure
        logging.error("Unable to query latest block for %s: %s", checksum, exc)
        return None

    try:
        code_latest = web3.eth.get_code(checksum, block_identifier=latest_block)
    except Exception as exc:
        logging.error("eth_getCode failed for %s (latest block): %s", checksum, exc)
        return None

    if not code_latest or len(code_latest) == 0:
        logging.warning("No bytecode found for address %s", checksum)
        return None

    low = 0
    high = latest_block

    if hint_block is not None:
        candidate_high = min(latest_block, max(hint_block, 0))
        try:
            code_at_candidate = web3.eth.get_code(
                checksum, block_identifier=candidate_high
            )
        except Exception:
            code_at_candidate = None
        if code_at_candidate and len(code_at_candidate) > 0:
            high = candidate_high

    deploy_block = high

    while low <= high:
        mid = (low + high) // 2
        try:
            code = web3.eth.get_code(checksum, block_identifier=mid)
        except BlockNotFound:
            high = mid - 1
            continue
        except ValueError as exc:
            message = str(exc)
            if "header not found" in message or "missing block" in message:
                high = mid - 1
                continue
            logging.error(
                "eth_getCode failed for %s at block %s: %s", checksum, mid, exc
            )
            return deploy_block if deploy_block != latest_block else None
        except Exception as exc:  # pragma: no cover - RPC failure
            logging.error(
                "eth_getCode failed for %s at block %s: %s", checksum, mid, exc
            )
            return deploy_block if deploy_block != latest_block else None

        if code and len(code) > 0:
            deploy_block = mid
            high = mid - 1
        else:
            low = mid + 1

    return deploy_block


def load_config(path: Path) -> dict[int, dict[str, object]]:
    with path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    config: dict[int, dict[str, object]] = {int(k): v for k, v in raw.items()}
    return config


def dump_config(path: Path, config: dict[int, dict[str, object]], backup: bool) -> None:
    ordered = {str(idx): config[idx] for idx in sorted(config.keys())}
    if backup:
        backup_path = path.with_suffix(path.suffix + ".bak")
        backup_path.write_text(json.dumps(ordered, indent=4) + "\n", encoding="utf-8")
        logging.info("Wrote backup to %s", backup_path)
    path.write_text(json.dumps(ordered, indent=4) + "\n", encoding="utf-8")
    logging.info("Updated config written to %s", path)


def process(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config_path = Path(args.config)
    data_dir = Path(args.data_dir)

    logging.info("Loading config from %s", config_path)
    config = load_config(config_path)
    parquet_index = build_parquet_index(data_dir)
    logging.info("Indexed %d parquet datasets", len(parquet_index))

    chains = {
        str(entry["chain_name"]).lower()
        for entry in config.values()
        if entry.get("chain_name")
    }
    rpc_registry = RpcRegistry(args, chains)

    metadata_cache: dict[str, PoolMetadata] = {}

    for idx in sorted(config.keys()):
        entry = config[idx]
        address = entry.get("address")
        chain = entry.get("chain_name")
        if not address:
            logging.error("Entry #%s is missing an address; skipping", idx)
            continue
        if not chain:
            logging.error(
                "Entry #%s (%s) has no chain_name; skipping", idx, entry.get("name")
            )
            continue

        address_str = str(address)
        chain_str = str(chain)
        address_lower = address_str.lower()
        chain_lower = chain_str.lower()
        logging.info("Processing #%s (%s on %s)", idx, entry.get("name"), chain_str)

        metadata = metadata_cache.get(address_lower)
        if not metadata:
            metadata = PoolMetadata(None, None, None)
            metadata_cache[address_lower] = metadata

        parquet_path = parquet_index.get(address_lower) or metadata.parquet_path
        if parquet_path is None:
            logging.warning("No cached data found for address %s", address)
        else:
            metadata.parquet_path = parquet_path
            if metadata.first_block is None:
                metadata.first_block = find_first_block(parquet_path)

        first_block = metadata.first_block

        if metadata.deployed_at_block is None:
            w3 = rpc_registry.get(chain_lower)
            metadata.deployed_at_block = contract_deployment_block(
                w3, address_str, hint_block=first_block
            )

        deployment_block = metadata.deployed_at_block

        if first_block is not None:
            entry["first_block"] = int(first_block)
        else:
            entry.pop("first_block", None)

        if deployment_block is not None:
            entry["deployed_at_block"] = int(deployment_block)
        else:
            entry.pop("deployed_at_block", None)

    totals = len(config)
    with_first_block = sum(1 for entry in config.values() if "first_block" in entry)
    with_deployment = sum(
        1 for entry in config.values() if "deployed_at_block" in entry
    )
    logging.info(
        "Computed metadata for %s pools (first_block: %s, deployed_at_block: %s)",
        totals,
        with_first_block,
        with_deployment,
    )

    if args.dry_run:
        logging.info("Dry-run complete. No files were modified.")
        return

    dump_config(config_path, config, args.backup)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG), help="Path to fxswap config JSON file"
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Root directory containing cached Parquet data",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute metadata without writing the config",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Write <config>.bak before updating the config file",
    )
    parser.add_argument(
        "--rpc-base", dest="rpc_base", help="RPC endpoint for the Base network"
    )
    parser.add_argument(
        "--rpc-ethereum",
        dest="rpc_ethereum",
        help="RPC endpoint for the Ethereum network",
    )
    if argv is None:
        return parser.parse_args()
    return parser.parse_args(list(argv))


if __name__ == "__main__":
    process(parse_args())
