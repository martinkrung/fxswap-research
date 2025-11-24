#!/bin/bash
# Wrapper script to view Parquet files
# This is a convenience script that calls the Python viewer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/view_parquet.py" "$@"
