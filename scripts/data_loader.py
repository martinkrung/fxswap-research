"""
Helper module for loading fxswap data from Parquet files.
"""

from pathlib import Path

from pathlib import Path

import pandas as pd


def build_parquet_index(data_dir: Path) -> dict[str, Path]:
    """Return mapping of lowercase address -> Parquet file path."""
    if not data_dir.exists():
        return {}

    index: dict[str, Path] = {}
    for path in data_dir.rglob("*.parquet"):
        index[path.stem.lower()] = path
    return index


def load_fxswap_data(file_path):
    """
    Load fxswap data from Parquet file.
    Creates empty file if it doesn't exist.

    Args:
        file_path: Path to the data file (can be .parquet or .json, but only .parquet is used)

    Returns:
        dict: Nested dictionary structure {block_number: {function_name: {value, epoch, human_readable}}}
    """
    file_path = Path(file_path)

    # Use Parquet (preferred and now only format)
    parquet_path = file_path.with_suffix(".parquet")
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        return dataframe_to_nested_dict(df)

    # If it doesn't exist, create an empty parquet file with the correct schema
    # Ensure the directory exists
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    # Create an empty DataFrame with the correct schema and dtypes
    empty_df = pd.DataFrame(
        {
            "block_number": pd.Series(dtype="int64"),
            "function_name": pd.Series(dtype="string"),
            "value": pd.Series(dtype="float64"),
            "epoch": pd.Series(dtype="int64"),
            "human_readable": pd.Series(dtype="string"),
        }
    )

    # Save the empty parquet file
    empty_df.to_parquet(
        parquet_path, engine="pyarrow", compression="snappy", index=False
    )

    # Return empty dict (no data yet)
    return {}


def dataframe_to_nested_dict(df):
    """
    Convert DataFrame to nested dictionary structure.

    Args:
        df: DataFrame with columns: block_number, function_name, value, epoch, human_readable

    Returns:
        dict: {block_number: {function_name: {value, epoch, human_readable}}}
    """
    result = {}

    for row in df.to_dict("records"):
        block_str = str(row["block_number"])
        if block_str not in result:
            result[block_str] = {}

        result[block_str][row["function_name"]] = {
            "value": row["value"],
            "epoch": int(row["epoch"]),
            "human_readable": row["human_readable"],
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
                records.append(
                    {
                        "block_number": int(block_number),
                        "function_name": function_name,
                        "value": function_data.get("value"),
                        "epoch": function_data.get("epoch"),
                        "human_readable": function_data.get("human_readable"),
                    }
                )

    df = pd.DataFrame(records)

    # Ensure proper data types
    if not df.empty:
        df["block_number"] = df["block_number"].astype("int64")
        df["function_name"] = df["function_name"].astype("string")
        df["value"] = df["value"].astype("float64")
        df["epoch"] = df["epoch"].astype("int64")
        df["human_readable"] = df["human_readable"].astype("string")

    return df
