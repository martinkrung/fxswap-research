#!/usr/bin/env python3
"""
Plot donation_shares, user_supply, and totalSupply over time.
Creates 3 charts:
1. donation_shares (absolute)
2. donation_shares delta (filtered: only negative)
3. USD Value Distribution and Ratio
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np
import json
import argparse
from pathlib import Path
import os

DATA_DIR = Path(os.getenv('DATA_DIR', 'data'))

# Plotting constants
PIXELS_PER_DAY = 288  # 1 day = 288 pixels width in the actual plot area
_INTERNAL_DPI = 100  # Used only to convert pixels to cm for matplotlib figsize
PLOT_AREA_RATIO = 0.87  # Plot area takes up 87% of figure width with our margins
FIGURE_HEIGHT_CM = 20  # Height in cm for individual charts
MARKER_SIZE = 1  # Size of markers for all data points
MAKER = "."  # Use this constant instead of the literal maker string

# Load fxswap_addresses from fxswaps.json if file exists, else use default.
fxswaps_path = Path(__file__).parent.parent / "config" / "fxswaps.json"
print(f"fxswaps_path: {fxswaps_path}")
fxswap_addresses = {}
if fxswaps_path.exists():
    try:
        with open(fxswaps_path, 'r') as f:
            fxswap_addresses_raw = json.load(f)
            # Convert string keys to integers (JSON requires string keys)
            fxswap_addresses = {int(k): v for k, v in fxswap_addresses_raw.items()}
        print(f"Loaded {len(fxswap_addresses)} pools from fxswaps.json")
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"Error loading fxswaps.json: {e}")
        print("Using empty fxswap_addresses dictionary")
        fxswap_addresses = {}
else:
    print(f"fxswaps.json not found at {fxswaps_path}, using empty dictionary")
    fxswap_addresses = {}

# Parse command line arguments
parser = argparse.ArgumentParser(description='Plot supply and shares data')
parser.add_argument('--index', type=int, default=0, help='Index of the pool to query (default: 0)')
args = parser.parse_args()

index = args.index
fxswap_address = fxswap_addresses[index]["address"]
name = fxswap_addresses[index]["name"]
chain_name = fxswap_addresses[index]["chain_name"]
json_file_path = f'data/{chain_name}/{fxswap_address}.json'
with open(json_file_path, 'r') as f:
    data = json.load(f)

# Token decimals (USDC=6, WETH=18)
token0_decimals = 18
token1_decimals = 18

# Parse the data from JSON
donation_shares_data = []
user_supply_data = []
total_supply_data = []
balance_0_data = []
balance_1_data = []
last_prices_data = []
fee_data = []

# Process each block in the JSON
for block_number, block_data in sorted(data.items(), key=lambda x: int(x[0])):
    # Get timestamp from any field
    timestamp = None
    if 'donation_shares' in block_data:
        timestamp = datetime.fromtimestamp(block_data['donation_shares']['epoch'])
    elif 'user_supply' in block_data:
        timestamp = datetime.fromtimestamp(block_data['user_supply']['epoch'])
    elif 'totalSupply' in block_data:
        timestamp = datetime.fromtimestamp(block_data['totalSupply']['epoch'])
    elif 'balances(0)' in block_data:
        timestamp = datetime.fromtimestamp(block_data['balances(0)']['epoch'])
    elif 'last_prices' in block_data:
        timestamp = datetime.fromtimestamp(block_data['last_prices']['epoch'])
    elif 'fee' in block_data:
        timestamp = datetime.fromtimestamp(block_data['fee']['epoch'])
    else:
        continue
    
    # Extract donation_shares
    if 'donation_shares' in block_data:
        donation_shares_data.append({
            'timestamp': timestamp,
            'donation_shares': block_data['donation_shares']['value']
        })
    
    # Extract user_supply
    if 'user_supply' in block_data:
        user_supply_data.append({
            'timestamp': timestamp,
            'user_supply': block_data['user_supply']['value']
        })
    
    # Extract totalSupply
    if 'totalSupply' in block_data:
        total_supply_data.append({
            'timestamp': timestamp,
            'totalSupply': block_data['totalSupply']['value']
        })
    
    # Extract balances(0) - USDC
    if 'balances(0)' in block_data:
        balance_0_data.append({
            'timestamp': timestamp,
            'balance_0': block_data['balances(0)']['value']
        })
    
    # Extract balances(1) - WETH
    if 'balances(1)' in block_data:
        balance_1_data.append({
            'timestamp': timestamp,
            'balance_1': block_data['balances(1)']['value']
        })
    
    # Extract last_prices for USD calculations
    if 'last_prices' in block_data:
        last_prices_data.append({
            'timestamp': timestamp,
            'last_price': block_data['last_prices']['value']
        })
    
    # Extract fee
    if 'fee' in block_data:
        fee_data.append({
            'timestamp': timestamp,
            'fee': block_data['fee']['value']
        })

print(f"Found {len(donation_shares_data)} donation_shares entries")
print(f"Found {len(user_supply_data)} user_supply entries")
print(f"Found {len(total_supply_data)} totalSupply entries")
print(f"Found {len(balance_0_data)} balance_0 entries")
print(f"Found {len(balance_1_data)} balance_1 entries")
print(f"Found {len(last_prices_data)} last_prices entries")
print(f"Found {len(fee_data)} fee entries")

# Create DataFrames
donation_shares_df = pd.DataFrame(donation_shares_data)
user_supply_df = pd.DataFrame(user_supply_data)
total_supply_df = pd.DataFrame(total_supply_data)
balance_0_df = pd.DataFrame(balance_0_data)
balance_1_df = pd.DataFrame(balance_1_data)
last_prices_df = pd.DataFrame(last_prices_data)
fee_df = pd.DataFrame(fee_data)

# Remove duplicates and sort
if not donation_shares_df.empty:
    donation_shares_df = donation_shares_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not user_supply_df.empty:
    user_supply_df = user_supply_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not total_supply_df.empty:
    total_supply_df = total_supply_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not balance_0_df.empty:
    balance_0_df = balance_0_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not balance_1_df.empty:
    balance_1_df = balance_1_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not last_prices_df.empty:
    last_prices_df = last_prices_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not fee_df.empty:
    fee_df = fee_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')

# Calculate USD values for balances
# Merge balances with last_prices to calculate USD values
if not balance_0_df.empty and not balance_1_df.empty and not last_prices_df.empty:
    # Merge all balance and price data
    balance_usd_df = pd.merge(balance_0_df, balance_1_df, on='timestamp', how='outer', suffixes=('', '_1'))
    balance_usd_df = pd.merge(balance_usd_df, last_prices_df, on='timestamp', how='outer', suffixes=('', '_price'))
    balance_usd_df = balance_usd_df.sort_values('timestamp')
    
    # Calculate USD values
    # balance_0 is USDC, so USD value = balance_0 (already in USD)
    # balance_1 is WETH, so USD value = balance_1 * last_price
    balance_usd_df['balance_0_usd'] = balance_usd_df['balance_0'].fillna(0)
    balance_usd_df['balance_1_usd'] = (balance_usd_df['balance_1'].fillna(0) * balance_usd_df['last_price'].fillna(0))
    balance_usd_df['total_usd'] = balance_usd_df['balance_0_usd'] + balance_usd_df['balance_1_usd']
    
    # Calculate ratio (balance_0_usd / balance_1_usd or balance_0_usd / total_usd)
    balance_usd_df['ratio_0_to_1'] = balance_usd_df.apply(
        lambda row: row['balance_0_usd'] / row['balance_1_usd'] if row['balance_1_usd'] > 0 else 0, axis=1
    )
    balance_usd_df['ratio_0_to_total'] = balance_usd_df.apply(
        lambda row: row['balance_0_usd'] / row['total_usd'] * 100 if row['total_usd'] > 0 else 0, axis=1
    )
    balance_usd_df['ratio_1_to_total'] = balance_usd_df.apply(
        lambda row: row['balance_1_usd'] / row['total_usd'] * 100 if row['total_usd'] > 0 else 0, axis=1
    )
else:
    balance_usd_df = pd.DataFrame()

# Calculate time range to determine figure width and set common x-axis limits
all_timestamps = []
for df in [donation_shares_df, user_supply_df, total_supply_df, balance_0_df, balance_1_df, balance_usd_df, fee_df]:
    if not df.empty and 'timestamp' in df.columns:
        all_timestamps.extend(df['timestamp'].tolist())

if all_timestamps:
    min_time = min(all_timestamps)
    max_time = max(all_timestamps)
    time_range = max_time - min_time
    time_range_days = time_range.total_seconds() / (24 * 3600)
    plot_area_width_pixels = time_range_days * PIXELS_PER_DAY
    figure_width_pixels = plot_area_width_pixels / PLOT_AREA_RATIO
    figure_width_cm = (figure_width_pixels / _INTERNAL_DPI) * 2.54
    figure_width_cm = max(figure_width_cm, 20.0)
    print(f"Full plot: {time_range_days:.2f} days, width: {figure_width_pixels:.0f} px ({figure_width_cm:.1f} cm)")
    print(f"Time range: {min_time} to {max_time}")
else:
    figure_width_cm = 35.0
    figure_width_pixels = (figure_width_cm / 2.54) * _INTERNAL_DPI
    min_time = None
    max_time = None

# Helper function to normalize data (0-1 range)
def normalize_data(values):
    """Normalize values to 0-1 range"""
    if len(values) == 0:
        return values
    min_val = min(values)
    max_val = max(values)
    if max_val == min_val:
        return [0.5] * len(values)  # All same value, return middle
    return [(v - min_val) / (max_val - min_val) for v in values]

# Calculate donation_shares delta (change from previous value)
if not donation_shares_df.empty:
    donation_shares_df = donation_shares_df.copy()
    donation_shares_df['delta'] = donation_shares_df['donation_shares'].diff()
    donation_shares_df['delta'] = donation_shares_df['delta'].fillna(0)  # First value has no previous, set to 0
    
    # Filter: only show negative values (exclude zero and positive)
    # Remove all positive values and zero to focus only on negative changes (share usage)
    donation_shares_df['delta_filtered'] = donation_shares_df['delta'].copy()
    donation_shares_df.loc[donation_shares_df['delta'] >= 0, 'delta_filtered'] = 0
    
    # Calculate USD value for deltas
    # Merge with totalSupply, balances, and last_prices to calculate USD value
    if not total_supply_df.empty:
        donation_shares_df = pd.merge(donation_shares_df, total_supply_df, on='timestamp', how='left', suffixes=('', '_total'))
    
    if not balance_0_df.empty:
        donation_shares_df = pd.merge(donation_shares_df, balance_0_df, on='timestamp', how='left', suffixes=('', '_b0'))
    
    if not balance_1_df.empty:
        donation_shares_df = pd.merge(donation_shares_df, balance_1_df, on='timestamp', how='left', suffixes=('', '_b1'))
    
    if not last_prices_df.empty:
        donation_shares_df = pd.merge(donation_shares_df, last_prices_df, on='timestamp', how='left', suffixes=('', '_price'))
    
    # Calculate USD value of delta
    # USD value = (delta / totalSupply) * (balance_0 + balance_1 * last_price)
    donation_shares_df['delta_usd'] = donation_shares_df.apply(
        lambda row: (
            (abs(row['delta_filtered']) / row['totalSupply'] * row['balance_0']) +
            (abs(row['delta_filtered']) / row['totalSupply'] * row['balance_1'] * row['last_price'])
        ) if (row['delta_filtered'] != 0 and pd.notna(row['totalSupply']) and row['totalSupply'] > 0 and 
              pd.notna(row['balance_0']) and pd.notna(row['balance_1']) and pd.notna(row['last_price'])) else 0,
        axis=1
    )
    
    # Calculate 4-hour moving average of USD spend
    # Sort by timestamp and set as index for rolling window
    donation_shares_df = donation_shares_df.sort_values('timestamp').copy()
    donation_shares_df.set_index('timestamp', inplace=True)
    # Calculate rolling mean over 4 hours
    donation_shares_df['delta_usd_4h_ma'] = donation_shares_df['delta_usd'].rolling(window='4h', min_periods=1).mean()
    donation_shares_df.reset_index(inplace=True)

# Create subplots: 3 charts total
fig = plt.figure(figsize=(figure_width_cm/2.54, (FIGURE_HEIGHT_CM * 3)/2.54))
gs = fig.add_gridspec(3, 1, hspace=0.3)

# Chart 1: donation_shares (absolute)
ax1 = fig.add_subplot(gs[0, 0])
if not donation_shares_df.empty:
    ax1.plot(donation_shares_df['timestamp'], donation_shares_df['donation_shares'], 
             'purple', linestyle='None', label='donation_shares', marker=MAKER, markersize=MARKER_SIZE)
ax1.set_ylabel('donation_shares (absolute)', fontsize=12)
ax1.set_title(f'{name}: donation_shares Over Time (Absolute)', fontsize=14, fontweight='bold')
ax1.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=10, ncol=1, frameon=False)
ax1.grid(True, alpha=0.3)

# Chart 2: donation_shares delta (absolute) - filtered (only negative, zero excluded)
ax2 = fig.add_subplot(gs[1, 0])
if not donation_shares_df.empty and 'delta_filtered' in donation_shares_df.columns:
    # Only plot non-zero values (negative deltas) as bars
    filtered_data = donation_shares_df[donation_shares_df['delta_filtered'] != 0].copy()
    if not filtered_data.empty:
        # Calculate bar width based on time spacing
        # Use a small width that represents about 2 pixels at the output DPI
        # Convert 2 pixels to days: 2px / PIXELS_PER_DAY
        bar_width_days = 2 / PIXELS_PER_DAY
        bar_width = timedelta(days=bar_width_days)
        
        ax2.bar(filtered_data['timestamp'], filtered_data['delta_filtered'], 
                width=bar_width, color='purple', label='donation_shares delta (filtered: only negative)', 
                align='center', edgecolor='purple', linewidth=0.1)
        
        # Add USD value labels for bars with delta < -0.001
        if 'delta_usd' in filtered_data.columns:
            # Label only bars where delta is less than -0.001 (more negative)
            for idx, row in filtered_data.iterrows():
                delta_value = row['delta_filtered']
                delta_usd = row.get('delta_usd', 0)
                
                # Only label if delta is less than -0.001
                if delta_value < -0.001 and delta_usd > 0:
                    # Format USD value (tiny amounts, show cents or less)
                    usd_label = f"${delta_usd:.4f}"
                    
                    # Add label at the end of the bar (bottom since delta is negative)
                    ax2.text(row['timestamp'], delta_value, usd_label, 
                            fontsize=6, ha='center', va='top', rotation=0,
                            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor='none'))
    
    # Add 4-hour moving average of USD spend on right y-axis
    if 'delta_usd_4h_ma' in donation_shares_df.columns:
        ax2_twin = ax2.twinx()
        # Plot moving average line
        ax2_twin.plot(donation_shares_df['timestamp'], donation_shares_df['delta_usd_4h_ma'], 
                      'orange', linestyle='None', label='4h MA USD Spend', marker=MAKER, markersize=MARKER_SIZE, alpha=0.8)

# Chart 3: USD Value Ratio (stacked area showing percentage of total USD)
ax10 = fig.add_subplot(gs[2, 0])
if not balance_usd_df.empty:
    timestamps_ratio = balance_usd_df['timestamp'].tolist()
    ratio_0 = balance_usd_df['ratio_0_to_total'].tolist()
    ratio_1 = balance_usd_df['ratio_1_to_total'].tolist()
    
    ax10.fill_between(timestamps_ratio, 0, ratio_0, alpha=0.7, color='cyan', label='USDC % of Total USD')
    ax10.fill_between(timestamps_ratio, ratio_0, [r0 + r1 for r0, r1 in zip(ratio_0, ratio_1)], 
                      alpha=0.7, color='orange', label='WETH % of Total USD')
    
    # Also plot the ratio line (balance_0_usd / balance_1_usd)
    ax10_twin = ax10.twinx()
    ratio_line = balance_usd_df['ratio_0_to_1'].tolist()
    ax10_twin.plot(timestamps_ratio, ratio_line, 'red', linestyle='None', label='USDC/WETH Ratio', marker=MAKER, markersize=MARKER_SIZE)
    ax10_twin.set_ylabel('USDC/WETH Ratio', fontsize=12, color='red')
    ax10_twin.tick_params(axis='y', labelcolor='red')
    ax10_twin.legend(bbox_to_anchor=(1.0, 1.15), loc='upper left', fontsize=10, ncol=1, frameon=False)
    
    ax10.set_ylabel('Percentage of Total USD (%)', fontsize=12)
    ax10.set_title(f'{name}: USD Value Distribution and Ratio Over Time', fontsize=14, fontweight='bold')
    ax10.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=10, ncol=2, frameon=False)
    ax10.grid(True, alpha=0.3)
    ax10.set_ylim(0, 100)

# Format x-axis for all subplots and set common time range
for ax in [ax1, ax2, ax10]:
    # Set the same x-axis limits for all charts so they align vertically
    if min_time is not None and max_time is not None:
        ax.set_xlim(min_time, max_time)
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    ax.grid(True, alpha=0.3, which='major')
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0]))
    ax.grid(True, alpha=0.6, which='minor', linewidth=1.5, linestyle='-')

# Set xlabel only on last subplot
ax10.set_xlabel('Time', fontsize=12)

# Get date range from data
if not donation_shares_df.empty:
    date_str = donation_shares_df['timestamp'].min().strftime('%Y-%m-%d')
elif not user_supply_df.empty:
    date_str = user_supply_df['timestamp'].min().strftime('%Y-%m-%d')
elif not total_supply_df.empty:
    date_str = total_supply_df['timestamp'].min().strftime('%Y-%m-%d')
else:
    date_str = datetime.now().strftime('%Y-%m-%d')

plt.suptitle(f'Supply and Shares Analysis: {name} (Data from {date_str})', 
             fontsize=12, y=0.995)

# Adjust layout
plt.subplots_adjust(left=0.08, bottom=0.03, right=0.95, top=0.98, hspace=0.3)

# Save the plot

plot_dir = Path("plots") / chain_name
plot_dir.mkdir(parents=True, exist_ok=True)


output_path = plot_dir / f'{name.replace("/", "_").replace(" ", "")}_secondary_refuel_analysis.png' 
plt.savefig(output_path, dpi=_INTERNAL_DPI, bbox_inches=None)
print(f"Chart saved to: {output_path} ({figure_width_pixels:.0f} x {int((FIGURE_HEIGHT_CM*3/2.54)*_INTERNAL_DPI)} px)")

# Print summary statistics
print("\n=== Summary Statistics ===")
if not donation_shares_df.empty:
    print(f"\ndonation_shares (absolute):")
    print(f"  Min: {donation_shares_df['donation_shares'].min():.6f}")
    print(f"  Max: {donation_shares_df['donation_shares'].max():.6f}")
    print(f"  Mean: {donation_shares_df['donation_shares'].mean():.6f}")
    print(f"  Latest: {donation_shares_df['donation_shares'].iloc[-1]:.6f}")

if not user_supply_df.empty:
    print(f"\nuser_supply (absolute):")
    print(f"  Min: {user_supply_df['user_supply'].min():.6f}")
    print(f"  Max: {user_supply_df['user_supply'].max():.6f}")
    print(f"  Mean: {user_supply_df['user_supply'].mean():.6f}")
    print(f"  Latest: {user_supply_df['user_supply'].iloc[-1]:.6f}")

if not total_supply_df.empty:
    print(f"\ntotalSupply (absolute):")
    print(f"  Min: {total_supply_df['totalSupply'].min():.6f}")
    print(f"  Max: {total_supply_df['totalSupply'].max():.6f}")
    print(f"  Mean: {total_supply_df['totalSupply'].mean():.6f}")
    print(f"  Latest: {total_supply_df['totalSupply'].iloc[-1]:.6f}")

if not balance_0_df.empty:
    print(f"\nbalance_0 (USDC) - absolute:")
    print(f"  Min: {balance_0_df['balance_0'].min():.2f}")
    print(f"  Max: {balance_0_df['balance_0'].max():.2f}")
    print(f"  Mean: {balance_0_df['balance_0'].mean():.2f}")
    print(f"  Latest: {balance_0_df['balance_0'].iloc[-1]:.2f}")

if not balance_1_df.empty:
    print(f"\nbalance_1 (WETH) - absolute:")
    print(f"  Min: {balance_1_df['balance_1'].min():.6f}")
    print(f"  Max: {balance_1_df['balance_1'].max():.6f}")
    print(f"  Mean: {balance_1_df['balance_1'].mean():.6f}")
    print(f"  Latest: {balance_1_df['balance_1'].iloc[-1]:.6f}")

if not balance_usd_df.empty:
    print(f"\nUSD Values:")
    print(f"  balance_0 (USDC) USD - Min: ${balance_usd_df['balance_0_usd'].min():.2f}")
    print(f"  balance_0 (USDC) USD - Max: ${balance_usd_df['balance_0_usd'].max():.2f}")
    print(f"  balance_0 (USDC) USD - Mean: ${balance_usd_df['balance_0_usd'].mean():.2f}")
    print(f"  balance_0 (USDC) USD - Latest: ${balance_usd_df['balance_0_usd'].iloc[-1]:.2f}")
    print(f"  balance_1 (WETH) USD - Min: ${balance_usd_df['balance_1_usd'].min():.2f}")
    print(f"  balance_1 (WETH) USD - Max: ${balance_usd_df['balance_1_usd'].max():.2f}")
    print(f"  balance_1 (WETH) USD - Mean: ${balance_usd_df['balance_1_usd'].mean():.2f}")
    print(f"  balance_1 (WETH) USD - Latest: ${balance_usd_df['balance_1_usd'].iloc[-1]:.2f}")
    print(f"  Total USD - Min: ${balance_usd_df['total_usd'].min():.2f}")
    print(f"  Total USD - Max: ${balance_usd_df['total_usd'].max():.2f}")
    print(f"  Total USD - Mean: ${balance_usd_df['total_usd'].mean():.2f}")
    print(f"  Total USD - Latest: ${balance_usd_df['total_usd'].iloc[-1]:.2f}")
    print(f"\nUSD Ratio (USDC/WETH):")
    print(f"  Min: {balance_usd_df['ratio_0_to_1'].min():.4f}")
    print(f"  Max: {balance_usd_df['ratio_0_to_1'].max():.4f}")
    print(f"  Mean: {balance_usd_df['ratio_0_to_1'].mean():.4f}")
    print(f"  Latest: {balance_usd_df['ratio_0_to_1'].iloc[-1]:.4f}")

if not fee_df.empty:
    print(f"\nfee (absolute):")
    print(f"  Min: {fee_df['fee'].min():.8f}")
    print(f"  Max: {fee_df['fee'].max():.8f}")
    print(f"  Mean: {fee_df['fee'].mean():.8f}")
    print(f"  Latest: {fee_df['fee'].iloc[-1]:.8f}")

