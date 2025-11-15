#!/usr/bin/env python3
"""
View Parquet file contents in a human-readable format.

This script provides various ways to view and inspect Parquet files:
- Head/tail viewing
- Schema information
- Summary statistics
- Filtering by block number or function name
- Export to CSV or JSON
"""

import pandas as pd
import argparse
from pathlib import Path
import sys


def print_schema(df):
    """Print the schema of the Parquet file."""
    print("\n" + "="*80)
    print("SCHEMA")
    print("="*80)
    print(f"Columns: {len(df.columns)}")
    print(f"Rows: {len(df)}")
    print("\nColumn Details:")
    for col in df.columns:
        dtype = df[col].dtype
        null_count = df[col].isnull().sum()
        print(f"  {col:20s} {str(dtype):15s} (null: {null_count})")
    print()


def print_summary(df):
    """Print summary statistics."""
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)

    if 'block_number' in df.columns:
        print(f"\nBlock Numbers:")
        print(f"  Min: {df['block_number'].min()}")
        print(f"  Max: {df['block_number'].max()}")
        print(f"  Count: {df['block_number'].nunique()} unique blocks")

    if 'function_name' in df.columns:
        print(f"\nFunction Names:")
        functions = df['function_name'].unique()
        for func in sorted(functions):
            count = (df['function_name'] == func).sum()
            print(f"  {func:30s} {count:6d} entries")

    if 'value' in df.columns:
        print(f"\nValue Statistics:")
        print(f"  Mean: {df['value'].mean():.6f}")
        print(f"  Std:  {df['value'].std():.6f}")
        print(f"  Min:  {df['value'].min():.6f}")
        print(f"  Max:  {df['value'].max():.6f}")

    if 'epoch' in df.columns:
        print(f"\nTime Range:")
        from datetime import datetime, timezone
        min_epoch = df['epoch'].min()
        max_epoch = df['epoch'].max()
        min_time = datetime.fromtimestamp(min_epoch, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        max_time = datetime.fromtimestamp(max_epoch, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        print(f"  From: {min_time} (epoch: {min_epoch})")
        print(f"  To:   {max_time} (epoch: {max_epoch})")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='View and inspect Parquet file contents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View first 10 rows
  %(prog)s data/base/0xF30fcb00b7C3d2f6e12043157011bea7f848049D.parquet

  # View last 20 rows
  %(prog)s data/base/0xF30fcb00b7C3d2f6e12043157011bea7f848049D.parquet --tail 20

  # Show schema and summary
  %(prog)s data/base/0xF30fcb00b7C3d2f6e12043157011bea7f848049D.parquet --schema --summary

  # Filter by function name
  %(prog)s data/base/0xF30fcb00b7C3d2f6e12043157011bea7f848049D.parquet --function totalSupply

  # Filter by block range
  %(prog)s data/base/0xF30fcb00b7C3d2f6e12043157011bea7f848049D.parquet --block-min 37880000 --block-max 37881000

  # Export to CSV
  %(prog)s data/base/0xF30fcb00b7C3d2f6e12043157011bea7f848049D.parquet --export output.csv

  # Export to JSON (nested format)
  %(prog)s data/base/0xF30fcb00b7C3d2f6e12043157011bea7f848049D.parquet --export output.json --nested
        """
    )

    parser.add_argument('file', type=str, help='Path to Parquet file')
    parser.add_argument('--head', type=int, default=10, help='Number of rows to show from the beginning (default: 10)')
    parser.add_argument('--tail', type=int, help='Number of rows to show from the end')
    parser.add_argument('--all', action='store_true', help='Show all rows (use with caution for large files)')
    parser.add_argument('--schema', action='store_true', help='Show schema information')
    parser.add_argument('--summary', action='store_true', help='Show summary statistics')
    parser.add_argument('--function', type=str, help='Filter by function name')
    parser.add_argument('--block', type=int, help='Filter by specific block number')
    parser.add_argument('--block-min', type=int, help='Filter by minimum block number')
    parser.add_argument('--block-max', type=int, help='Filter by maximum block number')
    parser.add_argument('--export', type=str, help='Export to file (CSV or JSON based on extension)')
    parser.add_argument('--nested', action='store_true', help='Export to nested JSON format (original structure)')

    args = parser.parse_args()

    # Check if file exists
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return 1

    # Read Parquet file
    print(f"Reading {file_path}...")
    try:
        df = pd.read_parquet(file_path)
    except Exception as e:
        print(f"Error reading Parquet file: {e}")
        return 1

    print(f"Loaded {len(df)} rows")

    # Show schema if requested
    if args.schema:
        print_schema(df)

    # Show summary if requested
    if args.summary:
        print_summary(df)

    # Apply filters
    filtered_df = df.copy()

    if args.function:
        filtered_df = filtered_df[filtered_df['function_name'] == args.function]
        print(f"Filtered by function '{args.function}': {len(filtered_df)} rows")

    if args.block:
        filtered_df = filtered_df[filtered_df['block_number'] == args.block]
        print(f"Filtered by block {args.block}: {len(filtered_df)} rows")

    if args.block_min:
        filtered_df = filtered_df[filtered_df['block_number'] >= args.block_min]
        print(f"Filtered by block_min {args.block_min}: {len(filtered_df)} rows")

    if args.block_max:
        filtered_df = filtered_df[filtered_df['block_number'] <= args.block_max]
        print(f"Filtered by block_max {args.block_max}: {len(filtered_df)} rows")

    # Export if requested
    if args.export:
        export_path = Path(args.export)
        print(f"\nExporting to {export_path}...")

        if export_path.suffix == '.json':
            if args.nested:
                # Convert to nested structure
                result = {}
                for _, row in filtered_df.iterrows():
                    block_str = str(row['block_number'])
                    if block_str not in result:
                        result[block_str] = {}
                    result[block_str][row['function_name']] = {
                        'value': row['value'],
                        'epoch': int(row['epoch']),
                        'human_readable': row['human_readable']
                    }
                import json
                with open(export_path, 'w') as f:
                    json.dump(result, f, indent=2)
            else:
                filtered_df.to_json(export_path, orient='records', indent=2)
        elif export_path.suffix == '.csv':
            filtered_df.to_csv(export_path, index=False)
        else:
            print(f"Warning: Unknown export format '{export_path.suffix}', defaulting to CSV")
            filtered_df.to_csv(export_path, index=False)

        print(f"Exported {len(filtered_df)} rows to {export_path}")
        return 0

    # Display rows
    if not args.schema and not args.summary:
        print("\n" + "="*80)
        print("DATA")
        print("="*80)

        # Set display options for better formatting
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 50)

        if args.all:
            print(filtered_df.to_string(index=False))
        elif args.tail:
            print(filtered_df.tail(args.tail).to_string(index=False))
        else:
            print(filtered_df.head(args.head).to_string(index=False))

        if len(filtered_df) > args.head and not args.all and not args.tail:
            print(f"\n... ({len(filtered_df) - args.head} more rows)")

        print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
