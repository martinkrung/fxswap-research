"""
Helper module for loading fxswap data from Parquet or JSON files.
Provides backward compatibility for reading both formats.
"""

import json
import pandas as pd
from pathlib import Path


def load_fxswap_data(file_path):
    """
    Load fxswap data from Parquet or JSON file.

    Args:
        file_path: Path to the data file (can be .parquet or .json)

    Returns:
        dict: Nested dictionary structure {block_number: {function_name: {value, epoch, human_readable}}}
    """
    file_path = Path(file_path)

    # Try Parquet first (preferred format)
    parquet_path = file_path.with_suffix('.parquet')
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        return dataframe_to_nested_dict(df)

    # Fall back to JSON for backward compatibility
    json_path = file_path.with_suffix('.json')
    if json_path.exists():
        with open(json_path, 'r') as f:
            return json.load(f)

    # If neither exists, raise error
    raise FileNotFoundError(f"Data file not found: tried {parquet_path} and {json_path}")


def dataframe_to_nested_dict(df):
    """
    Convert DataFrame to nested dictionary structure.

    Args:
        df: DataFrame with columns: block_number, function_name, value, epoch, human_readable

    Returns:
        dict: {block_number: {function_name: {value, epoch, human_readable}}}
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


def nested_dict_to_dataframe(data):
    """
    Convert nested dictionary to DataFrame.

    Args:
        data: dict {block_number: {function_name: {value, epoch, human_readable}}}

    Returns:
        DataFrame with columns: block_number, function_name, value, epoch, human_readable
    """
    records = []

    for block_number, block_data in data.items():
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
