import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np
import json
import argparse
from collections import Counter
from pathlib import Path

# Plotting constants
PIXELS_PER_DAY = 288  # 1 day = 288 pixels width in the actual plot area
# Internal DPI for matplotlib conversion (not exposed, just for calculation)
_INTERNAL_DPI = 100  # Used only to convert pixels to cm for matplotlib figsize
# Margins: left=0.08, right=0.95, so plot area = 0.95 - 0.08 = 0.87 of figure width
PLOT_AREA_RATIO = 0.87  # Plot area takes up 87% of figure width with our margins
FIGURE_HEIGHT_CM = 35  # Fixed height in cm (approximately 14 inches equivalent)

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
parser = argparse.ArgumentParser(description='Collect historical data for fxswap pools')
parser.add_argument('--index', type=int, default=0, help='Index of the pool to query (default: 0)')
args = parser.parse_args()

index = args.index
fxswap_address = fxswap_addresses[index]["address"]
name = fxswap_addresses[index]["name"]
chain_name = fxswap_addresses[index]["chain_name"]

json_file_path = f'data/{chain_name}/{fxswap_address}.json'
with open(json_file_path, 'r') as f:
    data = json.load(f)

def has_USDC(name):
    """
    Returns True if 'USDC' appears anywhere in the input pool name, else returns False.
    """
    if not isinstance(name, str):
        return False
    if "USDC" in name:
        return True
    return False

if has_USDC(name):
    token0_decimals = 6
    token1_decimals = 18
else:
    token0_decimals = 18
    token1_decimals = 18

print(f"token0_decimals: {token0_decimals}")
print(f"token1_decimals: {token1_decimals}")   

# Parse the data from JSON
last_prices_data = []
price_scale_data = []
price_oracle_data = []
donation_shares_data = []
donation_releases = []
donation_reset_timestamps = []  # Track when last_donation_release_ts resets
delta_price_data = []
balance_data = []
donation_shares_usd_data = []
xcp_profit_data = []
total_supply_data = []  # Add totalSupply data extraction

# Track previous last_donation_release_ts to detect resets
prev_release_ts = None
prev_delta = None  # Track previous delta to detect sudden changes
# Track previous values for growth rate calculation
prev_donation_shares = None
prev_total_supply = None
prev_donation_shares_normalized = None  # Track normalized value to maintain continuity

# First, detect the block interval from the data
# Look at block differences to determine if it's 100 or 200 blocks (or mixed)
block_numbers = sorted([int(k) for k in data.keys()])
block_intervals = []
for i in range(1, len(block_numbers)):  # Check all intervals
    interval = block_numbers[i] - block_numbers[i-1]
    if interval > 0:
        block_intervals.append(interval)

# Determine the block interval(s) present in the data
if block_intervals:
    interval_counts = Counter(block_intervals)
    most_common_interval = interval_counts.most_common(1)[0][0]
    
    # If we have mixed intervals (both 100 and 200), use the smaller one for threshold
    # This ensures we don't miss resets in 100-block sections
    if 100 in interval_counts and 200 in interval_counts:
        detected_interval = 100  # Use smaller interval for more sensitive detection
        print(f"Detected mixed block intervals: {interval_counts}")
        print(f"Using smaller interval ({detected_interval} blocks) for reset detection threshold")
    else:
        detected_interval = most_common_interval
        print(f"Detected block interval: {detected_interval} blocks")
    
    # Calculate threshold based on block interval
    # Block time is ~2 seconds per block, so interval * 2 gives us seconds
    # When a reset happens, last_donation_release_ts is set to current block time,
    # so delta should be within the block interval time (with some buffer for variation)
    block_interval_seconds = detected_interval * 2  # 2 seconds per block
    # Add 20% buffer to account for block time variation (e.g., 180-240s for 100 blocks)
    reset_threshold_seconds = int(block_interval_seconds * 1.2)
    reset_threshold_minutes = reset_threshold_seconds / 60
    print(f"Using reset detection threshold: {reset_threshold_minutes:.2f} minutes ({reset_threshold_seconds} seconds)")
else:
    # Fallback to default (200 blocks = 400 seconds * 1.2 = 480 seconds = 8 minutes)
    detected_interval = 200
    block_interval_seconds = detected_interval * 2
    reset_threshold_seconds = int(block_interval_seconds * 1.2)
    reset_threshold_minutes = reset_threshold_seconds / 60
    print(f"Could not detect block interval, using default: {detected_interval} blocks, threshold: {reset_threshold_minutes:.2f} minutes ({reset_threshold_seconds} seconds)")

# Process each block in the JSON
for block_number, block_data in sorted(data.items(), key=lambda x: int(x[0])):
    # Get timestamp from any field (they should all have the same epoch)
    timestamp = None
    if 'last_prices' in block_data:
        timestamp = datetime.fromtimestamp(block_data['last_prices']['epoch'])
    elif 'price_scale' in block_data:
        timestamp = datetime.fromtimestamp(block_data['price_scale']['epoch'])
    else:
        continue  # Skip blocks without timestamp info
    
    # Extract last_prices
    if 'last_prices' in block_data:
        last_prices_data.append({
            'timestamp': timestamp,
            'last_price': block_data['last_prices']['value']
        })
    
    # Extract price_scale
    if 'price_scale' in block_data:
        price_scale_data.append({
            'timestamp': timestamp,
            'price_scale': block_data['price_scale']['value']
        })
    
    # Extract price_oracle
    if 'price_oracle' in block_data:
        price_oracle_data.append({
            'timestamp': timestamp,
            'price_oracle': block_data['price_oracle']['value']
        })
    
    # Extract donation_shares (normalized value)
    if 'donation_shares' in block_data:
        donation_shares_data.append({
            'timestamp': timestamp,
            'donation_shares': block_data['donation_shares']['value']
        })
    
    # Extract totalSupply
    if 'totalSupply' in block_data:
        total_supply_data.append({
            'timestamp': timestamp,
            'totalSupply': block_data['totalSupply']['value']
        })
    
    # Extract xcp_profit
    if 'xcp_profit' in block_data:
        xcp_profit_data.append({
            'timestamp': timestamp,
            'xcp_profit': block_data['xcp_profit']['value']
        })
    
    # Extract balances
    balance_0 = None
    balance_1 = None
    if 'balances(0)' in block_data:
        balance_0 = block_data['balances(0)']['value']
    if 'balances(1)' in block_data:
        balance_1 = block_data['balances(1)']['value']
    
    if balance_0 is not None or balance_1 is not None:
        balance_data.append({
            'timestamp': timestamp,
            'balance_0': balance_0,
            'balance_1': balance_1
        })
    
    # Extract last_donation_release_ts and track resets
    if 'last_donation_release_ts' in block_data:
        release_ts = block_data['last_donation_release_ts']['value']
        # Get block timestamp as epoch
        block_epoch = None
        if 'last_prices' in block_data:
            block_epoch = block_data['last_prices']['epoch']
        elif 'price_scale' in block_data:
            block_epoch = block_data['price_scale']['epoch']
        # Check if it's a valid timestamp (not a very small number)
        if release_ts > 1000000000 and block_epoch is not None:  # Valid unix timestamp (after 2001)
            release_time = datetime.fromtimestamp(release_ts)
            donation_releases.append({
                'timestamp': timestamp,
                'release_time': release_time
            })
            
            # Detect reset: delta between release_ts and block_epoch
            # When reset happens, release_ts is set to current block time (delta ~0)
            # But we sample every 100 blocks, so by next sample, delta could be up to block_interval_seconds
            # So we detect when delta is within the block interval range (recent reset)
            delta = abs(release_ts - block_epoch)
            
            # Detect reset if:
            # 1. Delta is within block interval range (reset happened recently, within last sampling period)
            # 2. OR delta suddenly decreased from large to small (reset just happened)
            is_reset = False
            if delta <= block_interval_seconds * 1.2:  # Within block interval + buffer
                # Check if this is a new reset (delta decreased significantly from previous)
                if prev_delta is None or prev_delta > block_interval_seconds * 2:
                    # Previous delta was large (or first check), current is small = reset detected
                    is_reset = True
                elif prev_delta is not None and prev_delta > delta + block_interval_seconds:
                    # Delta decreased significantly = reset happened
                    is_reset = True
            
            if is_reset:
                donation_reset_timestamps.append(timestamp)
                # Reset tracking for growth rate calculation when reset happens
                if 'donation_shares' in block_data:
                    prev_donation_shares = block_data['donation_shares']['value']
                if 'totalSupply' in block_data:
                    prev_total_supply = block_data['totalSupply']['value']
                prev_donation_shares_normalized = None  # Reset normalized value
            
            # Update previous delta for next iteration
            prev_delta = delta
        
        # Update previous value (only if valid, otherwise keep previous)
        if release_ts > 1000000000:
            prev_release_ts = release_ts
        elif prev_release_ts is not None and release_ts <= 1000000000:
            # Value became invalid after being valid - this is also a reset
            donation_reset_timestamps.append(timestamp)
            prev_release_ts = None
            # Reset tracking for growth rate calculation when reset happens
            if 'donation_shares' in block_data:
                prev_donation_shares = block_data['donation_shares']['value']
            if 'totalSupply' in block_data:
                prev_total_supply = block_data['totalSupply']['value']
            prev_donation_shares_normalized = None  # Reset normalized value
    
    # Calculate delta_price_last_to_scale (in USD and %)
    if 'last_prices' in block_data and 'price_scale' in block_data:
        last_price = block_data['last_prices']['value']
        price_scale = block_data['price_scale']['value']
        delta_usd = last_price - price_scale
        delta_percent = (delta_usd / price_scale) * 100 if price_scale != 0 else 0
        
        delta_price_data.append({
            'timestamp': timestamp,
            'delta_usd': delta_usd,
            'delta_percent': delta_percent
        })
    
    # Calculate donation shares normalized (0-1) and USD value
    # Based on check_refule_usdc_eth_pools.py lines 342-350
    if ('donation_shares' in block_data and 
        'totalSupply' in block_data and 
        'balances(0)' in block_data and 
        'balances(1)' in block_data and
        'last_prices' in block_data):
        
        donation_shares = block_data['donation_shares']['value']
        total_supply = block_data['totalSupply']['value']
        balance_0 = block_data['balances(0)']['value']
        balance_1 = block_data['balances(1)']['value']
        last_price = block_data['last_prices']['value']
        
        # Normalize donation_shares based on growth rate comparison
        # Key insight from contract: fees increase totalSupply but NOT donation_shares
        # When shares are used (burned), both decrease proportionally
        # So: if donation_shares grows at same rate as total_supply = no usage
        #     if donation_shares grows slower = shares were used
        donation_shares_normalized = None
        donation_shares_used_delta = None  # Track how much was used (in shares)
        
        if prev_donation_shares is not None and prev_total_supply is not None and prev_total_supply > 0 and total_supply > 0:
            # Calculate growth rate of total_supply
            total_supply_growth_rate = (total_supply - prev_total_supply) / prev_total_supply
            
            # Calculate expected donation_shares if it grew at same rate as total_supply
            # This accounts for fee inflation of totalSupply
            expected_donation_shares = prev_donation_shares * (1 + total_supply_growth_rate)
            
            # Calculate actual growth rate of donation_shares
            if prev_donation_shares > 0:
                donation_shares_growth_rate = (donation_shares - prev_donation_shares) / prev_donation_shares
            else:
                donation_shares_growth_rate = 0
            
            # Tolerance for comparing growth rates (account for floating point precision)
            growth_rate_tolerance = 1e-8
            
            # If donation_shares grew at same rate (or very close), no shares were used
            if abs(donation_shares_growth_rate - total_supply_growth_rate) < growth_rate_tolerance:
                # Same growth rate: normalized value stays constant (horizontal line)
                if prev_donation_shares_normalized is not None:
                    donation_shares_normalized = prev_donation_shares_normalized
                else:
                    # First data point: initialize to 1.0 (100% of shares available)
                    donation_shares_normalized = 1.0
                donation_shares_used_delta = 0
            else:
                # Different growth rates: calculate how much was used
                # If expected > actual, the difference was used (burned)
                donation_shares_used_delta = max(0, expected_donation_shares - donation_shares)
                
                # Update normalized value: decrease proportionally to usage
                if prev_donation_shares_normalized is not None and prev_donation_shares > 0:
                    # Calculate usage ratio relative to previous donation_shares
                    usage_ratio = donation_shares_used_delta / prev_donation_shares if prev_donation_shares > 0 else 0
                    # Decrease normalized value by usage ratio
                    donation_shares_normalized = prev_donation_shares_normalized * (1 - usage_ratio)
                    # Ensure it doesn't go negative
                    donation_shares_normalized = max(0, donation_shares_normalized)
                else:
                    # First data point: start at 1.0, then adjust if there was usage
                    if donation_shares_used_delta > 0 and prev_donation_shares > 0:
                        usage_ratio = donation_shares_used_delta / prev_donation_shares
                        donation_shares_normalized = 1.0 * (1 - usage_ratio)
                    else:
                        donation_shares_normalized = 1.0
        else:
            # First data point or missing previous values: initialize to 1.0
            donation_shares_normalized = 1.0
            donation_shares_used_delta = 0
        
        # Update previous values for next iteration
        prev_donation_shares = donation_shares
        prev_total_supply = total_supply
        prev_donation_shares_normalized = donation_shares_normalized
        
        # Calculate USD value using current total_supply (original calculation)
        # Values in JSON are already normalized (divided by decimals)

        token0_amount_normalized = (donation_shares / total_supply) * balance_0
        token1_amount_normalized = (donation_shares / total_supply) * balance_1

        # Convert to USD
        token0_usd = token0_amount_normalized
        token1_usd = token1_amount_normalized * last_price

        donation_shares_usd = token0_usd + token1_usd
        
        # Calculate USD value of used shares (delta)
        donation_shares_used_usd = None
        if donation_shares_used_delta is not None and donation_shares_used_delta > 0:
            # Calculate USD value of the used shares
            # Used shares as ratio of total supply
            used_ratio = donation_shares_used_delta / total_supply if total_supply > 0 else 0
            used_token0_amount = used_ratio * balance_0
            used_token1_amount = used_ratio * balance_1
            used_token0_usd = used_token0_amount
            used_token1_usd = used_token1_amount * last_price
            donation_shares_used_usd = used_token0_usd + used_token1_usd
        
        donation_shares_usd_data.append({
            'timestamp': timestamp,
            'donation_shares_normalized': donation_shares_normalized,
            'donation_shares_usd': donation_shares_usd,
            'donation_shares_used_delta': donation_shares_used_delta,
            'donation_shares_used_usd': donation_shares_used_usd
        })

print(f"Found {len(last_prices_data)} last_prices entries")
print(f"Found {len(price_scale_data)} price_scale entries")
print(f"Found {len(price_oracle_data)} price_oracle entries")
print(f"Found {len(donation_shares_data)} donation_shares entries")
print(f"Found {len(delta_price_data)} delta_price entries")
print(f"Found {len(balance_data)} balance entries")
print(f"Found {len(donation_releases)} donation_release entries")
print(f"Found {len(donation_reset_timestamps)} donation reset events")
print(f"Found {len(donation_shares_usd_data)} donation_shares_usd entries")
print(f"Found {len(xcp_profit_data)} xcp_profit entries")
print(f"Found {len(total_supply_data)} totalSupply entries")

# Create DataFrames
last_prices_df = pd.DataFrame(last_prices_data)
price_scale_df = pd.DataFrame(price_scale_data)
price_oracle_df = pd.DataFrame(price_oracle_data)
donation_shares_df = pd.DataFrame(donation_shares_data)
delta_price_df = pd.DataFrame(delta_price_data)
balance_df = pd.DataFrame(balance_data)
donation_releases_df = pd.DataFrame(donation_releases)
donation_shares_usd_df = pd.DataFrame(donation_shares_usd_data)
xcp_profit_df = pd.DataFrame(xcp_profit_data)
total_supply_df = pd.DataFrame(total_supply_data)

# Remove duplicates and sort
if not last_prices_df.empty:
    last_prices_df = last_prices_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not price_scale_df.empty:
    price_scale_df = price_scale_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not price_oracle_df.empty:
    price_oracle_df = price_oracle_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not donation_shares_df.empty:
    donation_shares_df = donation_shares_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not delta_price_df.empty:
    delta_price_df = delta_price_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not balance_df.empty:
    balance_df = balance_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not donation_releases_df.empty:
    donation_releases_df = donation_releases_df.drop_duplicates(subset=['release_time']).sort_values('timestamp')
if not donation_shares_usd_df.empty:
    donation_shares_usd_df = donation_shares_usd_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not xcp_profit_df.empty:
    xcp_profit_df = xcp_profit_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    # Normalize xcp_profit: first value -> 0, last value -> 1
    if len(xcp_profit_df) > 0:
        first_value = xcp_profit_df['xcp_profit'].iloc[0]
        last_value = xcp_profit_df['xcp_profit'].iloc[-1]
        if last_value != first_value:
            xcp_profit_df['xcp_profit_normalized'] = (xcp_profit_df['xcp_profit'] - first_value) / (last_value - first_value)
        else:
            xcp_profit_df['xcp_profit_normalized'] = 0.0
if not total_supply_df.empty:
    total_supply_df = total_supply_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')

# Calculate donation shares delta (change from previous value) - same as plot_supply_shares.py
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
    
    # Split balance_df into balance_0_df and balance_1_df for merging
    balance_0_df = balance_df[['timestamp', 'balance_0']].copy() if not balance_df.empty else pd.DataFrame()
    balance_1_df = balance_df[['timestamp', 'balance_1']].copy() if not balance_df.empty else pd.DataFrame()
    
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

# Calculate time range to determine figure width
# Find the earliest and latest timestamps from all dataframes
all_timestamps = []
for df in [last_prices_df, price_scale_df, price_oracle_df, donation_shares_df, 
           delta_price_df, balance_df, donation_shares_usd_df, xcp_profit_df, total_supply_df]:
    if not df.empty and 'timestamp' in df.columns:
        all_timestamps.extend(df['timestamp'].tolist())

if all_timestamps:
    min_time = min(all_timestamps)
    max_time = max(all_timestamps)
    time_range = max_time - min_time
    time_range_days = time_range.total_seconds() / (24 * 3600)
    # Calculate plot area width in pixels: time_range_days * PIXELS_PER_DAY
    plot_area_width_pixels = time_range_days * PIXELS_PER_DAY
    # Calculate figure width in pixels: plot_area / PLOT_AREA_RATIO (to account for margins)
    figure_width_pixels = plot_area_width_pixels / PLOT_AREA_RATIO
    # Convert pixels to cm for matplotlib figsize: (pixels / DPI) * 2.54
    figure_width_cm = (figure_width_pixels / _INTERNAL_DPI) * 2.54
    # Ensure minimum width for readability (minimum ~20 cm)
    figure_width_cm = max(figure_width_cm, 20.0)
    print(f"Full plot: {time_range_days:.2f} days, width: {figure_width_pixels:.0f} px ({figure_width_cm:.1f} cm)")
else:
    # Fallback to default if no data (~35 cm width)
    figure_width_cm = 35.0
    figure_width_pixels = (figure_width_cm / 2.54) * _INTERNAL_DPI

# Create the plot with more subplots
# Width is calculated to maintain 288 pixels per day, height stays constant
fig, axes = plt.subplots(3, 1, figsize=(figure_width_cm/2.54, FIGURE_HEIGHT_CM/2.54), sharex=True)
ax1, ax2, ax3 = axes

# Plot last_prices, price_scale, and price_oracle
ax1_twin = None
if not last_prices_df.empty:
    ax1.plot(last_prices_df['timestamp'], last_prices_df['last_price'], 
             'b-', label='last_prices()', linewidth=2, marker='o', markersize=1)
if not price_scale_df.empty:
    ax1.plot(price_scale_df['timestamp'], price_scale_df['price_scale'], 
             'r-', label='price_scale()', linewidth=2, marker='s', markersize=1)
if not price_oracle_df.empty:
    ax1.plot(price_oracle_df['timestamp'], price_oracle_df['price_oracle'], 
             'g-', label='price_oracle()', linewidth=2, marker='^', markersize=1)

# Plot xcp_profit (normalized) on right axis
if not xcp_profit_df.empty and 'xcp_profit_normalized' in xcp_profit_df.columns:
    ax1_twin = ax1.twinx()
    # Plot line for all points
    ax1_twin.plot(xcp_profit_df['timestamp'], xcp_profit_df['xcp_profit_normalized'], 
                 'brown', linewidth=1, label='xcp_profit (normalized)', linestyle='None', marker='None')
    
    # Find where values change (only show markers where value changed)
    xcp_profit_df_sorted = xcp_profit_df.sort_values('timestamp')
    value_changed = xcp_profit_df_sorted['xcp_profit_normalized'].diff().abs() > 1e-10
    # First point always shows a marker
    value_changed.iloc[0] = True
    
    # Plot markers only where value changed
    changed_data = xcp_profit_df_sorted[value_changed]
    if not changed_data.empty:
        ax1_twin.plot(changed_data['timestamp'], changed_data['xcp_profit_normalized'], 
                     'brown', marker='*', markersize=1, linestyle='None', label='_nolegend_')
    
    ax1_twin.set_ylabel('xcp_profit (normalized 0-1)', fontsize=12, color='brown')
    ax1_twin.tick_params(axis='y', labelcolor='brown')
    ax1_twin.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=10, ncol=1, frameon=False)

ax1.set_ylabel('Price (USD)', fontsize=12)
ax1.set_title(f'{name}: Price Metrics Over Time', fontsize=14, fontweight='bold')
if not last_prices_df.empty or not price_scale_df.empty or not price_oracle_df.empty:
    ax1.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=10, ncol=3, frameon=False)
ax1.grid(True, alpha=0.3)

# Add donation release markers
if not donation_releases_df.empty:
    unique_releases = donation_releases_df['release_time'].unique()
    for release_time in unique_releases:
        # Find the closest timestamp in price data
        if not last_prices_df.empty:
            closest_idx = (last_prices_df['timestamp'] - release_time).abs().idxmin()
            closest_time = last_prices_df.loc[closest_idx, 'timestamp']
            closest_price = last_prices_df.loc[closest_idx, 'last_price']
            
            #ax1.axvline(x=release_time, color='green', linestyle='--', alpha=0.5)
            '''
            ax1.annotate(f'Donation Release\n{release_time.strftime("%H:%M:%S")}', 
                        xy=(release_time, closest_price),
                        xytext=(10, 20), textcoords='offset points',
                        fontsize=8, color='green',
                        bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.3),
                        arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
            '''

# Plot donation shares delta (absolute) - filtered (only negative, zero excluded) - same as plot_supply_shares.py
ax2_twin = None
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
                      'orange', linewidth=2, label='4h MA USD Spend', linestyle='-', alpha=0.8)
        ax2_twin.set_ylabel('4h Moving Average USD Spend', fontsize=12, color='orange')
        ax2_twin.tick_params(axis='y', labelcolor='orange')
        ax2_twin.legend(bbox_to_anchor=(1.0, 1.15), loc='upper left', fontsize=10, ncol=1, frameon=False)
    
    ax2.set_ylabel('donation_shares delta (absolute, filtered)', fontsize=12)
    ax2.set_title(f'{name}: donation_shares Delta Over Time (Filtered: Negative Only)', fontsize=12, fontweight='bold')
    ax2.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=10, ncol=1, frameon=False)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color='black', linestyle='--', linewidth=0.5, alpha=0.5)
else:
    ax2.set_ylabel('donation_shares delta (absolute, filtered)', fontsize=12)
    ax2.set_title(f'{name}: donation_shares Delta Over Time (Filtered: Negative Only)', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3)

# Plot delta_price_last_to_scale in USD and %
ax3_twin = None
if not delta_price_df.empty:
    # Plot delta in USD
    delta_usd_data = delta_price_df[delta_price_df['delta_usd'].notna()]
    if not delta_usd_data.empty:
        ax3.plot(delta_usd_data['timestamp'], delta_usd_data['delta_usd'], 
                 'c-', linewidth=2, label='Delta (USD)', marker='o', markersize=1)
    
    # Plot delta in % on twin axis
    delta_percent_data = delta_price_df[delta_price_df['delta_percent'].notna()]
    if not delta_percent_data.empty:
        ax3_twin = ax3.twinx()
        ax3_twin.plot(delta_percent_data['timestamp'], delta_percent_data['delta_percent'], 
                     'm-', linewidth=2, label='Delta (%)', marker='s', markersize=1)
        ax3_twin.set_ylabel('Delta Price Last to Scale (%)', fontsize=10, color='m')
        ax3_twin.tick_params(axis='y', labelcolor='m')
    
    ax3.set_ylabel('Delta Price Last to Scale (USD)', fontsize=10, color='c')
    ax3.tick_params(axis='y', labelcolor='c')
    ax3.set_title('Price Delta: last_prices() - price_scale()', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    # Combine legends from both axes
    lines1, labels1 = ax3.get_legend_handles_labels()
    if ax3_twin is not None:
        lines2, labels2 = ax3_twin.get_legend_handles_labels()
        ax3.legend(lines1 + lines2, labels1 + labels2, 
                  bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=9, ncol=2, frameon=False)
    else:
        ax3.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=9, ncol=1, frameon=False)
else:
    ax3.set_ylabel('Delta Price (USD)', fontsize=12)
    ax3.set_title('Price Delta: last_prices() - price_scale()', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.3)

# Add thin black vertical lines for donation share resets (after all twin axes are created)
# Note: Chart 2 (ax2) does not show these lines
if donation_reset_timestamps:
    for reset_time in donation_reset_timestamps:
        ax1.axvline(x=reset_time, color='black', linestyle='-', linewidth=0.5, alpha=0.7)
        # ax2.axvline removed - user requested no refueling lines on chart 2
        ax3.axvline(x=reset_time, color='black', linestyle='-', linewidth=0.5, alpha=0.7)
        if ax1_twin is not None:
            ax1_twin.axvline(x=reset_time, color='black', linestyle='-', linewidth=0.5, alpha=0.7)
        # ax2_twin.axvline removed - user requested no refueling lines on chart 2
        if ax3_twin is not None:
            ax3_twin.axvline(x=reset_time, color='black', linestyle='-', linewidth=0.5, alpha=0.7)

ax3.set_xlabel('Time', fontsize=12)

# Format x-axis - use 6-hour intervals at fixed times (00:00, 6:00, 12:00, 18:00)
for ax in [ax1, ax2, ax3]:
    # Use HourLocator with byhour to set fixed hours: 0, 6, 12, 18
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    # Format to show date and time for 6-hour intervals
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    # Ensure grid is enabled and follows major ticks (6-hour intervals)
    ax.grid(True, alpha=0.3, which='major')
    
    # Add thicker grid lines at midnight (00:00)
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0]))
    ax.grid(True, alpha=0.6, which='minor', linewidth=1.5, linestyle='-')

# Get date range from data
if not last_prices_df.empty:
    date_str = last_prices_df['timestamp'].min().strftime('%Y-%m-%d')
else:
    date_str = datetime.now().strftime('%Y-%m-%d')

plt.suptitle(f'Data from {date_str} (Values from JSON cache)', 
             fontsize=10, y=1.02)

# Use subplots_adjust to set consistent margins (left, bottom, right, top)
# This ensures the plot area has the correct width regardless of labels
# Increased top margin to accommodate legends above the plots
plt.subplots_adjust(left=0.08, bottom=0.08, right=0.95, top=0.92, hspace=0.3)

# Save the plot
# Don't use bbox_inches='tight' as it crops the image and reduces the actual size
# Use the full figure size to preserve our calculated pixel-per-day ratio

plot_dir = Path("plots") / chain_name
plot_dir.mkdir(parents=True, exist_ok=True)

output_path = plot_dir / f'{name.replace("/", "_").replace(" ", "")}_pool_price_analysis.png'
plt.savefig(output_path, dpi=_INTERNAL_DPI, bbox_inches=None)
print(f"Chart saved to: {output_path} ({figure_width_pixels:.0f} x {int((FIGURE_HEIGHT_CM/2.54)*_INTERNAL_DPI)} px)")

# Create second plot for last 48 hours only
if all_timestamps:
    max_time_48h = max(all_timestamps)
    min_time_48h = max_time_48h - timedelta(hours=48)
    
    # Filter all dataframes to last 48 hours
    last_prices_df_48h = last_prices_df[last_prices_df['timestamp'] >= min_time_48h].copy() if not last_prices_df.empty else pd.DataFrame()
    price_scale_df_48h = price_scale_df[price_scale_df['timestamp'] >= min_time_48h].copy() if not price_scale_df.empty else pd.DataFrame()
    price_oracle_df_48h = price_oracle_df[price_oracle_df['timestamp'] >= min_time_48h].copy() if not price_oracle_df.empty else pd.DataFrame()
    donation_shares_df_48h = donation_shares_df[donation_shares_df['timestamp'] >= min_time_48h].copy() if not donation_shares_df.empty else pd.DataFrame()
    delta_price_df_48h = delta_price_df[delta_price_df['timestamp'] >= min_time_48h].copy() if not delta_price_df.empty else pd.DataFrame()
    balance_df_48h = balance_df[balance_df['timestamp'] >= min_time_48h].copy() if not balance_df.empty else pd.DataFrame()
    donation_shares_usd_df_48h = donation_shares_usd_df[donation_shares_usd_df['timestamp'] >= min_time_48h].copy() if not donation_shares_usd_df.empty else pd.DataFrame()
    xcp_profit_df_48h = xcp_profit_df[xcp_profit_df['timestamp'] >= min_time_48h].copy() if not xcp_profit_df.empty else pd.DataFrame()
    total_supply_df_48h = total_supply_df[total_supply_df['timestamp'] >= min_time_48h].copy() if not total_supply_df.empty else pd.DataFrame()
    donation_releases_df_48h = donation_releases_df[donation_releases_df['timestamp'] >= min_time_48h].copy() if not donation_releases_df.empty else pd.DataFrame()
    
    # Filter reset timestamps to last 48 hours
    donation_reset_timestamps_48h = [ts for ts in donation_reset_timestamps if ts >= min_time_48h]
    
    # Calculate actual time range in the filtered data
    all_timestamps_48h = []
    for df in [last_prices_df_48h, price_scale_df_48h, price_oracle_df_48h, donation_shares_df_48h, 
               delta_price_df_48h, balance_df_48h, donation_shares_usd_df_48h, xcp_profit_df_48h, total_supply_df_48h]:
        if not df.empty and 'timestamp' in df.columns:
            all_timestamps_48h.extend(df['timestamp'].tolist())
    
    if all_timestamps_48h:
        min_time_48h_actual = min(all_timestamps_48h)
        max_time_48h_actual = max(all_timestamps_48h)
        time_range_48h = max_time_48h_actual - min_time_48h_actual
        time_range_hours_48h = time_range_48h.total_seconds() / 3600
        
        # Calculate width based on actual time range
        # Scale: 5 min = 1 px, so 1 hour = 12 px, 1 day = 288 px
        # Convert hours to pixels: hours * 12
        plot_area_width_pixels_48h = time_range_hours_48h * 12  # 12 pixels per hour (5 min = 1 px)
        figure_width_pixels_48h = plot_area_width_pixels_48h / PLOT_AREA_RATIO
        # Convert pixels to cm for matplotlib figsize: (pixels / DPI) * 2.54
        figure_width_cm_48h = (figure_width_pixels_48h / _INTERNAL_DPI) * 2.54
        # Ensure minimum width for readability (minimum ~20 cm)
        figure_width_cm_48h = max(figure_width_cm_48h, 20.0)
        
        print(f"\nCreating 48-hour plot: {time_range_hours_48h:.2f} hours of data, width: {figure_width_pixels_48h:.0f} px ({figure_width_cm_48h:.1f} cm)")
        
        # Create the 48-hour plot
        fig_48h, axes_48h = plt.subplots(3, 1, figsize=(figure_width_cm_48h/2.54, FIGURE_HEIGHT_CM/2.54), sharex=True)
        ax1_48h, ax2_48h, ax3_48h = axes_48h
        
        # Plot last_prices, price_scale, and price_oracle
        ax1_twin_48h = None
        if not last_prices_df_48h.empty:
            ax1_48h.plot(last_prices_df_48h['timestamp'], last_prices_df_48h['last_price'], 
                     'b-', label='last_prices()', linewidth=2, marker='o', markersize=1)
        if not price_scale_df_48h.empty:
            ax1_48h.plot(price_scale_df_48h['timestamp'], price_scale_df_48h['price_scale'], 
                     'r-', label='price_scale()', linewidth=2, marker='s', markersize=1)
        if not price_oracle_df_48h.empty:
            ax1_48h.plot(price_oracle_df_48h['timestamp'], price_oracle_df_48h['price_oracle'], 
                     'g-', label='price_oracle()', linewidth=2, marker='^', markersize=1)
        
        # Plot xcp_profit (normalized) on right axis
        if not xcp_profit_df_48h.empty and 'xcp_profit_normalized' in xcp_profit_df_48h.columns:
            ax1_twin_48h = ax1_48h.twinx()
            ax1_twin_48h.plot(xcp_profit_df_48h['timestamp'], xcp_profit_df_48h['xcp_profit_normalized'], 
                         'brown', linewidth=1, label='xcp_profit (normalized)', linestyle='None', marker='None')
            
            xcp_profit_df_48h_sorted = xcp_profit_df_48h.sort_values('timestamp')
            value_changed_48h = xcp_profit_df_48h_sorted['xcp_profit_normalized'].diff().abs() > 1e-10
            value_changed_48h.iloc[0] = True
            
            changed_data_48h = xcp_profit_df_48h_sorted[value_changed_48h]
            if not changed_data_48h.empty:
                ax1_twin_48h.plot(changed_data_48h['timestamp'], changed_data_48h['xcp_profit_normalized'], 
                             'brown', marker='*', markersize=1, linestyle='None', label='_nolegend_')
            
            ax1_twin_48h.set_ylabel('xcp_profit (normalized 0-1)', fontsize=12, color='brown')
            ax1_twin_48h.tick_params(axis='y', labelcolor='brown')
            ax1_twin_48h.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=10, ncol=1, frameon=False)
        
        ax1_48h.set_ylabel('Price (USD)', fontsize=12)
        ax1_48h.set_title(f'{name}: Price Metrics Over Time (Last 48 Hours)', fontsize=14, fontweight='bold')
        if not last_prices_df_48h.empty or not price_scale_df_48h.empty or not price_oracle_df_48h.empty:
            ax1_48h.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=10, ncol=3, frameon=False)
        ax1_48h.grid(True, alpha=0.3)
        
        # Plot donation shares delta (absolute) - filtered (only negative, zero excluded) - same as plot_supply_shares.py
        ax2_twin_48h = None
        # Filter donation_shares_df to 48h for delta plot
        donation_shares_df_48h = donation_shares_df[donation_shares_df['timestamp'] >= min_time_48h].copy() if not donation_shares_df.empty else pd.DataFrame()
        
        if not donation_shares_df_48h.empty and 'delta_filtered' in donation_shares_df_48h.columns:
            # Only plot non-zero values (negative deltas) as bars
            filtered_data_48h = donation_shares_df_48h[donation_shares_df_48h['delta_filtered'] != 0].copy()
            if not filtered_data_48h.empty:
                # Calculate bar width based on time spacing
                bar_width_days = 2 / PIXELS_PER_DAY
                bar_width = timedelta(days=bar_width_days)
                
                ax2_48h.bar(filtered_data_48h['timestamp'], filtered_data_48h['delta_filtered'], 
                        width=bar_width, color='purple', label='donation_shares delta (filtered: only negative)', 
                        align='center', edgecolor='purple', linewidth=0.1)
                
                # Add USD value labels for bars with delta < -0.001
                if 'delta_usd' in filtered_data_48h.columns:
                    for idx, row in filtered_data_48h.iterrows():
                        delta_value = row['delta_filtered']
                        delta_usd = row.get('delta_usd', 0)
                        
                        if delta_value < -0.001 and delta_usd > 0:
                            usd_label = f"${delta_usd:.4f}"
                            ax2_48h.text(row['timestamp'], delta_value, usd_label, 
                                    fontsize=6, ha='center', va='top', rotation=0,
                                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor='none'))
            
            # Add 4-hour moving average of USD spend on right y-axis
            if 'delta_usd_4h_ma' in donation_shares_df_48h.columns:
                ax2_twin_48h = ax2_48h.twinx()
                ax2_twin_48h.plot(donation_shares_df_48h['timestamp'], donation_shares_df_48h['delta_usd_4h_ma'], 
                              'orange', linewidth=2, label='4h MA USD Spend', linestyle='-', alpha=0.8)
                ax2_twin_48h.set_ylabel('4h Moving Average USD Spend', fontsize=12, color='orange')
                ax2_twin_48h.tick_params(axis='y', labelcolor='orange')
                ax2_twin_48h.legend(bbox_to_anchor=(1.0, 1.15), loc='upper left', fontsize=10, ncol=1, frameon=False)
            
            ax2_48h.set_ylabel('donation_shares delta (absolute, filtered)', fontsize=12)
            ax2_48h.set_title(f'{name}: donation_shares Delta Over Time (Filtered: Negative Only)', fontsize=12, fontweight='bold')
            ax2_48h.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=10, ncol=1, frameon=False)
            ax2_48h.grid(True, alpha=0.3)
            ax2_48h.axhline(y=0, color='black', linestyle='--', linewidth=0.5, alpha=0.5)
        else:
            ax2_48h.set_ylabel('donation_shares delta (absolute, filtered)', fontsize=12)
            ax2_48h.set_title(f'{name}: donation_shares Delta Over Time (Filtered: Negative Only)', fontsize=12, fontweight='bold')
            ax2_48h.grid(True, alpha=0.3)
        
        # Plot delta_price_last_to_scale in USD and %
        ax3_twin_48h = None
        if not delta_price_df_48h.empty:
            delta_usd_data_48h = delta_price_df_48h[delta_price_df_48h['delta_usd'].notna()]
            if not delta_usd_data_48h.empty:
                ax3_48h.plot(delta_usd_data_48h['timestamp'], delta_usd_data_48h['delta_usd'], 
                         'c-', linewidth=2, label='Delta (USD)', marker='o', markersize=1)
            
            delta_percent_data_48h = delta_price_df_48h[delta_price_df_48h['delta_percent'].notna()]
            if not delta_percent_data_48h.empty:
                ax3_twin_48h = ax3_48h.twinx()
                ax3_twin_48h.plot(delta_percent_data_48h['timestamp'], delta_percent_data_48h['delta_percent'], 
                             'm-', linewidth=2, label='Delta (%)', marker='s', markersize=1)
                ax3_twin_48h.set_ylabel('Delta Price Last to Scale (%)', fontsize=10, color='m')
                ax3_twin_48h.tick_params(axis='y', labelcolor='m')
            
            ax3_48h.set_ylabel('Delta Price Last to Scale (USD)', fontsize=10, color='c')
            ax3_48h.tick_params(axis='y', labelcolor='c')
            ax3_48h.set_title('Price Delta: last_prices() - price_scale()', fontsize=12, fontweight='bold')
            ax3_48h.grid(True, alpha=0.3)
            # Combine legends from both axes
            lines1_48h, labels1_48h = ax3_48h.get_legend_handles_labels()
            if ax3_twin_48h is not None:
                lines2_48h, labels2_48h = ax3_twin_48h.get_legend_handles_labels()
                ax3_48h.legend(lines1_48h + lines2_48h, labels1_48h + labels2_48h, 
                              bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=9, ncol=2, frameon=False)
            else:
                ax3_48h.legend(bbox_to_anchor=(1.0, 1.15), loc='upper right', fontsize=9, ncol=1, frameon=False)
        else:
            ax3_48h.set_ylabel('Delta Price (USD)', fontsize=12)
            ax3_48h.set_title('Price Delta: last_prices() - price_scale()', fontsize=12, fontweight='bold')
            ax3_48h.grid(True, alpha=0.3)
        
        # Add thin black vertical lines for donation share resets
        # Note: Chart 2 (ax2_48h) does not show these lines
        if donation_reset_timestamps_48h:
            for reset_time in donation_reset_timestamps_48h:
                ax1_48h.axvline(x=reset_time, color='black', linestyle='-', linewidth=0.5, alpha=0.7)
                # ax2_48h.axvline removed - user requested no refueling lines on chart 2
                ax3_48h.axvline(x=reset_time, color='black', linestyle='-', linewidth=0.5, alpha=0.7)
                if ax1_twin_48h is not None:
                    ax1_twin_48h.axvline(x=reset_time, color='black', linestyle='-', linewidth=0.5, alpha=0.7)
                # ax2_twin_48h.axvline removed - user requested no refueling lines on chart 2
                if ax3_twin_48h is not None:
                    ax3_twin_48h.axvline(x=reset_time, color='black', linestyle='-', linewidth=0.5, alpha=0.7)
        
        ax3_48h.set_xlabel('Time', fontsize=12)
        
        # Format x-axis - adjust interval based on time range
        # For shorter time ranges, use smaller intervals
        if time_range_hours_48h <= 4:
            # For 4 hours or less, use 30-minute intervals
            major_interval = mdates.MinuteLocator(byminute=[0, 30])
            minor_interval = mdates.MinuteLocator(byminute=[0])
            date_format = '%H:%M'
        elif time_range_hours_48h <= 12:
            # For up to 12 hours, use 1-hour intervals
            major_interval = mdates.HourLocator(interval=1)
            minor_interval = mdates.HourLocator(byhour=[0])
            date_format = '%H:%M'
        elif time_range_hours_48h <= 24:
            # For up to 24 hours, use 2-hour intervals
            major_interval = mdates.HourLocator(interval=2)
            minor_interval = mdates.HourLocator(byhour=[0])
            date_format = '%m/%d %H:%M'
        else:
            # For 24-48 hours, use 4-hour intervals
            major_interval = mdates.HourLocator(interval=4)
            minor_interval = mdates.HourLocator(byhour=[0])
            date_format = '%m/%d %H:%M'
        
        for ax in [ax1_48h, ax2_48h, ax3_48h]:
            ax.xaxis.set_major_locator(major_interval)
            ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
            ax.grid(True, alpha=0.3, which='major')
            ax.xaxis.set_minor_locator(minor_interval)
            ax.grid(True, alpha=0.6, which='minor', linewidth=1.5, linestyle='-')
        
        # Get date range from data
        if not last_prices_df_48h.empty:
            date_str_48h = f"{last_prices_df_48h['timestamp'].min().strftime('%Y-%m-%d %H:%M')} to {last_prices_df_48h['timestamp'].max().strftime('%Y-%m-%d %H:%M')}"
        else:
            date_str_48h = datetime.now().strftime('%Y-%m-%d')
        
        plt.suptitle(f'Last 48 Hours: {date_str_48h} (Values from JSON cache)', 
                     fontsize=10, y=1.02)
        
        plt.subplots_adjust(left=0.08, bottom=0.08, right=0.95, top=0.92, hspace=0.3)
        
        # Save the 48-hour plot
        output_path_48h = plot_dir / f'{name.replace("/", "_").replace(" ", "")}_pool_price_analysis_48h.png'
        plt.savefig(output_path_48h, dpi=_INTERNAL_DPI, bbox_inches=None)
        print(f"48-hour chart saved to: {output_path_48h} ({figure_width_pixels_48h:.0f} x {int((FIGURE_HEIGHT_CM/2.54)*_INTERNAL_DPI)} px)")
        plt.close(fig_48h)

# Print summary statistics
print("\n=== Summary Statistics ===")
if not last_prices_df.empty:
    print(f"\nLast Prices (USD):")
    print(f"  Min: ${last_prices_df['last_price'].min():.2f}")
    print(f"  Max: ${last_prices_df['last_price'].max():.2f}")
    print(f"  Mean: ${last_prices_df['last_price'].mean():.2f}")
    print(f"  Latest: ${last_prices_df['last_price'].iloc[-1]:.2f}")

if not price_scale_df.empty:
    print(f"\nPrice Scale (USD):")
    print(f"  Min: ${price_scale_df['price_scale'].min():.2f}")
    print(f"  Max: ${price_scale_df['price_scale'].max():.2f}")
    print(f"  Mean: ${price_scale_df['price_scale'].mean():.2f}")
    print(f"  Latest: ${price_scale_df['price_scale'].iloc[-1]:.2f}")

if not price_oracle_df.empty:
    print(f"\nPrice Oracle (USD):")
    print(f"  Min: ${price_oracle_df['price_oracle'].min():.2f}")
    print(f"  Max: ${price_oracle_df['price_oracle'].max():.2f}")
    print(f"  Mean: ${price_oracle_df['price_oracle'].mean():.2f}")
    print(f"  Latest: ${price_oracle_df['price_oracle'].iloc[-1]:.2f}")

if not delta_price_df.empty:
    delta_usd_data = delta_price_df[delta_price_df['delta_usd'].notna()]
    delta_percent_data = delta_price_df[delta_price_df['delta_percent'].notna()]
    print(f"\nDelta Price Last to Scale:")
    if not delta_usd_data.empty:
        print(f"  USD - Min: ${delta_usd_data['delta_usd'].min():.2f}")
        print(f"  USD - Max: ${delta_usd_data['delta_usd'].max():.2f}")
        print(f"  USD - Mean: ${delta_usd_data['delta_usd'].mean():.2f}")
        print(f"  USD - Latest: ${delta_usd_data['delta_usd'].iloc[-1]:.2f}")
    if not delta_percent_data.empty:
        print(f"  % - Min: {delta_percent_data['delta_percent'].min():.4f}%")
        print(f"  % - Max: {delta_percent_data['delta_percent'].max():.4f}%")
        print(f"  % - Mean: {delta_percent_data['delta_percent'].mean():.4f}%")
        print(f"  % - Latest: {delta_percent_data['delta_percent'].iloc[-1]:.4f}%")

if not donation_shares_usd_df.empty:
    print(f"\nDonation Shares (USD):")
    print(f"  Min: ${donation_shares_usd_df['donation_shares_usd'].min():.2f}")
    print(f"  Max: ${donation_shares_usd_df['donation_shares_usd'].max():.2f}")
    print(f"  Mean: ${donation_shares_usd_df['donation_shares_usd'].mean():.2f}")
    print(f"  Latest: ${donation_shares_usd_df['donation_shares_usd'].iloc[-1]:.2f}")

if not donation_shares_df.empty:
    print(f"\nDonation Shares (raw):")
    print(f"  Total Shares (latest): {donation_shares_df['donation_shares'].iloc[-1]:.6f}")
    if 'delta_filtered' in donation_shares_df.columns:
        # Calculate total shares used from negative deltas
        total_shares_used = abs(donation_shares_df['delta_filtered'].sum())
        print(f"  Total Shares Used: {total_shares_used:.6f}")
    else:
        # Fallback: calculate from diff if delta_filtered not available
        shares_used = -donation_shares_df['donation_shares'].diff()
        shares_used = shares_used.fillna(0)
        print(f"  Total Shares Used: {shares_used[shares_used > 0].sum():.6f}")
    
if not donation_releases_df.empty:
    print(f"\nDonation Releases:")
    print(f"  Number of unique releases detected: {len(donation_releases_df['release_time'].unique())}")
