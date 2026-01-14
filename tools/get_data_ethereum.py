#!/usr/bin/env python3
import json
import subprocess
import sys


def main():
    # Load config
    try:
        with open("config/fxswaps.json") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: config/fxswaps.json not found")
        sys.exit(1)

    # Filter base market IDs and sort them descending to mimic previous script behavior
    base_ids = [int(k) for k, v in data.items() if v.get("chain_name") == "ethereum"]
    base_ids.sort(reverse=True)

    # Run the processing script for each ID
    for idx in base_ids:
        print(f"--- Processing Index {idx} ---")
        try:
            subprocess.run(
                ["python3", "scripts/fill_missing_fxswap_data.py", "--index", str(idx)],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Error processing index {idx}: {e}")
            # Continue with next index or fail? Usually safer to continue in a batch script
            continue


if __name__ == "__main__":
    main()
