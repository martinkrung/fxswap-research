#!/usr/bin/env python3
"""
Script to convert existing JSON data files to Parquet format.

This script:
1. Finds all JSON files in the data directory
2. Converts them to Parquet format with proper schema
3. Optionally removes the original JSON files
"""

import json
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import argparse


def json_to_dataframe(json_data):
    """
    Convert nested JSON structure to a flat DataFrame.

    Input structure: {block_number: {function_name: {value, epoch, human_readable}}}
    Output DataFrame columns: block_number, function_name, value, epoch, human_readable
    """
    records = []

    for block_number, block_data in json_data.items():
        for function_name, function_data in block_data.items():
            if isinstance(function_data, dict):
                records.append({
                    'block_number': int(block_number),
                    'function_name': function_name,
                    'value': function_data.get('value'),
                    'epoch': function_data.get('epoch'),
                    'human_readable': function_data.get('human_readable')
                })

    df = pd.DataFrame(records)

    # Ensure proper data types
    if not df.empty:
        df['block_number'] = df['block_number'].astype('int64')
        df['function_name'] = df['function_name'].astype('string')
        df['value'] = df['value'].astype('float64')
        df['epoch'] = df['epoch'].astype('int64')
        df['human_readable'] = df['human_readable'].astype('string')

    return df


def dataframe_to_json(df):
    """
    Convert DataFrame back to nested JSON structure.

    Input DataFrame columns: block_number, function_name, value, epoch, human_readable
    Output structure: {block_number: {function_name: {value, epoch, human_readable}}}
    """
    result = {}

    for _, row in df.iterrows():
        block_str = str(row['block_number'])
        if block_str not in result:
            result[block_str] = {}

        result[block_str][row['function_name']] = {
            'value': row['value'],
            'epoch': int(row['epoch']),
            'human_readable': row['human_readable']
        }

    return result


def convert_json_to_parquet(json_file_path, remove_json=False):
    """
    Convert a single JSON file to Parquet format.

    Args:
        json_file_path: Path to the JSON file
        remove_json: If True, remove the original JSON file after conversion

    Returns:
        Path to the created Parquet file
    """
    json_file_path = Path(json_file_path)

    # Read JSON file
    print(f"Reading {json_file_path}...")
    with open(json_file_path, 'r') as f:
        json_data = json.load(f)

    # Convert to DataFrame
    print(f"Converting to DataFrame (found {len(json_data)} blocks)...")
    df = json_to_dataframe(json_data)

    # Create Parquet file path (same name, different extension)
    parquet_file_path = json_file_path.with_suffix('.parquet')

    # Write to Parquet
    print(f"Writing to {parquet_file_path}...")
    df.to_parquet(
        parquet_file_path,
        engine='pyarrow',
        compression='snappy',
        index=False
    )

    # Verify the conversion by reading back and comparing
    print(f"Verifying conversion...")
    df_read = pd.read_parquet(parquet_file_path)
    json_reconstructed = dataframe_to_json(df_read)

    # Basic verification: check number of blocks
    if len(json_data) != len(json_reconstructed):
        print(f"  WARNING: Block count mismatch! Original: {len(json_data)}, Reconstructed: {len(json_reconstructed)}")
    else:
        print(f"  ✓ Verification passed ({len(json_data)} blocks)")

    # Get file sizes
    json_size = json_file_path.stat().st_size / (1024 * 1024)  # MB
    parquet_size = parquet_file_path.stat().st_size / (1024 * 1024)  # MB
    compression_ratio = (1 - parquet_size / json_size) * 100

    print(f"  JSON size: {json_size:.2f} MB")
    print(f"  Parquet size: {parquet_size:.2f} MB")
    print(f"  Compression: {compression_ratio:.1f}% reduction")

    # Remove JSON file if requested
    if remove_json:
        print(f"  Removing original JSON file...")
        json_file_path.unlink()

    return parquet_file_path


def main():
    parser = argparse.ArgumentParser(description='Convert JSON data files to Parquet format')
    parser.add_argument('--remove-json', action='store_true',
                        help='Remove original JSON files after conversion')
    parser.add_argument('--data-dir', type=str, default='data',
                        help='Base data directory (default: data)')
    parser.add_argument('--file', type=str, default=None,
                        help='Convert a specific file instead of all files')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    if not data_dir.exists():
        print(f"Error: Data directory {data_dir} does not exist")
        return 1

    # Find all JSON files
    if args.file:
        json_files = [Path(args.file)]
    else:
        json_files = list(data_dir.rglob('*.json'))

    if not json_files:
        print(f"No JSON files found in {data_dir}")
        return 0

    print(f"Found {len(json_files)} JSON file(s) to convert")
    print("=" * 80)

    successful = 0
    failed = 0

    for json_file in json_files:
        try:
            print(f"\n[{successful + failed + 1}/{len(json_files)}] Converting {json_file.relative_to(data_dir)}")
            convert_json_to_parquet(json_file, remove_json=args.remove_json)
            successful += 1
        except Exception as e:
            print(f"  ERROR: Failed to convert {json_file}: {e}")
            failed += 1

    print("\n" + "=" * 80)
    print(f"Conversion complete!")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    exit(main())
