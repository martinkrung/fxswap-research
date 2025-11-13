import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np
import json
import argparse
from pathlib import Path

# Plotting constants
PIXELS_PER_DAY = 288  # 1 day = 288 pixels width in the actual plot area
# Internal DPI for matplotlib conversion (not exposed, just for calculation)
_INTERNAL_DPI = 100  # Used only to convert pixels to cm for matplotlib figsize
# Margins: left=0.08, right=0.95, so plot area = 0.95 - 0.08 = 0.87 of figure width
PLOT_AREA_RATIO = 0.87  # Plot area takes up 87% of figure width with our margins
FIGURE_HEIGHT_CM = 35  # Fixed height in cm (approximately 14 inches equivalent)
MARKER_SIZE = 1  # Size of markers for all data points
MAKER = "."  # Use this constant instead of the literal maker string
BLUE = '#3465A4'
GREEN = '#4E9A06'
ORANGE = '#F57900'
TIME_WINDOW_HOURS = 2*24  # Time window for the time_window plot (in hours)

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
virtual_price_data = []
total_supply_data = []  # Add totalSupply data extraction
xcp_profit_data = []

# Track previous last_donation_release_ts to detect resets
# Reset detection: if last_donation_release_ts changes from previous value, it's a reset
prev_release_ts = None
# Track previous values for growth rate calculation
prev_donation_shares = None
prev_total_supply = None
prev_donation_shares_normalized = None  # Track normalized value to maintain continuity

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
    
    # Extract virtual_price (normalized: subtract 1 so it starts at 0)
    if 'virtual_price' in block_data:
        virtual_price_data.append({
            'timestamp': timestamp,
            'virtual_price': block_data['virtual_price']['value'] - 1
        })
    
    # Extract xcp_profit (normalized: subtract 1 so it starts at 0)
    if 'xcp_profit' in block_data:
        xcp_profit_data.append({
            'timestamp': timestamp,
            'xcp_profit': (block_data['xcp_profit']['value'] - 1) / 2
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
        # Check if it's a valid timestamp (not a very small number)
        if release_ts > 1000000000:  # Valid unix timestamp (after 2001)
            release_time = datetime.fromtimestamp(release_ts)
            donation_releases.append({
                'timestamp': timestamp,
                'release_time': release_time
            })
            
            # Detect reset: if last_donation_release_ts changes from previous value, it's a reset
            # This works across all chains regardless of block time
            is_reset = False
            if prev_release_ts is not None and release_ts != prev_release_ts:
                # Value changed from previous = reset detected
                is_reset = True
            
            if is_reset:
                donation_reset_timestamps.append(timestamp)
                # Reset tracking for growth rate calculation when reset happens
                if 'donation_shares' in block_data:
                    prev_donation_shares = block_data['donation_shares']['value']
                if 'totalSupply' in block_data:
                    prev_total_supply = block_data['totalSupply']['value']
                prev_donation_shares_normalized = None  # Reset normalized value
            
            # Update previous value
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
    # Based on check_refuel_usdc_eth_pools.py lines 342-350
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
print(f"Found {len(donation_shares_data)} refuel_shares entries")
print(f"Found {len(delta_price_data)} delta_price entries")
print(f"Found {len(balance_data)} balance entries")
print(f"Found {len(donation_releases)} refuel_release entries")
print(f"Found {len(donation_reset_timestamps)} refuel reset events")
print(f"Found {len(donation_shares_usd_data)} refuel_shares_usd entries")
print(f"Found {len(virtual_price_data)} virtual_price entries")
print(f"Found {len(total_supply_data)} totalSupply entries")
print(f"Found {len(xcp_profit_data)} xcp_profit entries")

# Create DataFrames
last_prices_df = pd.DataFrame(last_prices_data)
price_scale_df = pd.DataFrame(price_scale_data)
price_oracle_df = pd.DataFrame(price_oracle_data)
donation_shares_df = pd.DataFrame(donation_shares_data)
delta_price_df = pd.DataFrame(delta_price_data)
balance_df = pd.DataFrame(balance_data)
donation_releases_df = pd.DataFrame(donation_releases)
donation_shares_usd_df = pd.DataFrame(donation_shares_usd_data)
virtual_price_df = pd.DataFrame(virtual_price_data)
total_supply_df = pd.DataFrame(total_supply_data)
xcp_profit_df = pd.DataFrame(xcp_profit_data)

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
if not virtual_price_df.empty:
    virtual_price_df = virtual_price_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not total_supply_df.empty:
    total_supply_df = total_supply_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
if not xcp_profit_df.empty:
    xcp_profit_df = xcp_profit_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')

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
    
    # Calculate moving average of USD spend
    # Sort by timestamp and set as index for rolling window
    donation_shares_df = donation_shares_df.sort_values('timestamp').copy()
    donation_shares_df.set_index('timestamp', inplace=True)
    # Calculate rolling mean
    donation_shares_df['delta_usd_ma'] = donation_shares_df['delta_usd'].rolling(window='2h', min_periods=1).mean()
    donation_shares_df.reset_index(inplace=True)

def calculate_figure_dimensions(dataframes_list):
    """
    Calculate figure width based on time range in the data.

    Args:
        dataframes_list: List of dataframes to analyze for time range

    Returns:
        tuple: (figure_width_cm, figure_width_pixels, time_info_str)
    """
    all_timestamps = []
    for df in dataframes_list:
        if not df.empty and 'timestamp' in df.columns:
            all_timestamps.extend(df['timestamp'].tolist())

    if all_timestamps:
        min_time = min(all_timestamps)
        max_time = max(all_timestamps)
        time_range = max_time - min_time
        time_range_days = time_range.total_seconds() / (24 * 3600)
        time_range_hours = time_range.total_seconds() / 3600

        # Calculate plot area width in pixels
        if time_range_days >= 1:
            # For ranges >= 1 day: use days * PIXELS_PER_DAY
            plot_area_width_pixels = time_range_days * PIXELS_PER_DAY
            time_info = f"{time_range_days:.2f} days"
        else:
            # For ranges < 1 day: use hours * 12 (5 min = 1 px)
            plot_area_width_pixels = time_range_hours * 12
            time_info = f"{time_range_hours:.2f} hours of data"

        # Calculate figure width
        figure_width_pixels = plot_area_width_pixels / PLOT_AREA_RATIO
        figure_width_cm = (figure_width_pixels / _INTERNAL_DPI) * 2.54
        figure_width_cm = max(figure_width_cm, 20.0)

        return figure_width_cm, figure_width_pixels, time_info
    else:
        # Fallback
        figure_width_cm = 35.0
        figure_width_pixels = (figure_width_cm / 2.54) * _INTERNAL_DPI
        return figure_width_cm, figure_width_pixels, "0 days"


def create_refuel_chart(
    last_prices_df, price_scale_df, xcp_profit_df, virtual_price_df,
    donation_shares_df, delta_price_df, donation_reset_timestamps,
    figure_width_cm, name, output_path, plot_description=""
):
    """
    Create a 5-subplot refuel analysis chart.

    Args:
        last_prices_df: DataFrame with last_prices data
        price_scale_df: DataFrame with price_scale data
        xcp_profit_df: DataFrame with xcp_profit data
        virtual_price_df: DataFrame with virtual_price data
        donation_shares_df: DataFrame with donation_shares data
        delta_price_df: DataFrame with delta_price data
        donation_reset_timestamps: List of timestamps for refueling events
        figure_width_cm: Width of figure in cm
        name: Pool name for titles
        output_path: Path to save the chart
        plot_description: Optional description for logging (e.g., "Full plot", "48-hour plot")

    Returns:
        tuple: (figure, figure_width_pixels) - The matplotlib figure object and width in pixels
    """
    # Chart height ratios
    refueling_chart_height_ratio = 2
    regular_chart_height_ratio = 18

    # Create figure with 5 subplots
    fig, axes = plt.subplots(
        5, 1,
        figsize=(figure_width_cm/2.54, FIGURE_HEIGHT_CM/2.54),
        sharex=True,
        height_ratios=[regular_chart_height_ratio, regular_chart_height_ratio,
                      refueling_chart_height_ratio, regular_chart_height_ratio,
                      regular_chart_height_ratio]
    )
    ax0, ax1, ax2, ax3, ax4 = axes

    # ===== Chart 0: Spot and Scale Prices =====
    if not last_prices_df.empty:
        ax0.plot(last_prices_df['timestamp'], last_prices_df['last_price'],
                color=BLUE, label='spot price', linestyle='None', marker=MAKER, markersize=MARKER_SIZE)
    if not price_scale_df.empty:
        ax0.plot(price_scale_df['timestamp'], price_scale_df['price_scale'],
                color=GREEN, label='price scale', linestyle='None', marker=MAKER, markersize=MARKER_SIZE)

    # Add Price % of Max to chart 0
    ax1_twin = None
    if not last_prices_df.empty:
        max_price = last_prices_df['last_price'].max()
        last_prices_df_copy = last_prices_df.copy()
        last_prices_df_copy['price_change_pct'] = (last_prices_df_copy['last_price'] / max_price) * 100

        ax1_twin = ax0.twinx()
        ax1_twin.axhline(y=100, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
        ax1_twin.set_ylabel('Price % of Max', fontsize=12, color='black')
        ax1_twin.tick_params(axis='y', labelcolor='black')

    ax0.set_ylabel('Price (USD)', fontsize=12)
    ax0.set_title(f'{name}: Spot and Scale Prices Over Time', fontsize=14, fontweight='bold')

    # Chart 0 legend
    handles1, labels1 = ax0.get_legend_handles_labels()
    if ax1_twin is not None:
        handles_twin, labels_twin = ax1_twin.get_legend_handles_labels()
        if handles_twin:
            handles1.extend(handles_twin)
            labels1.extend(labels_twin)
    if handles1:
        ax0.legend(handles1, labels1, bbox_to_anchor=(1, -0.02), loc='upper right',
                  fontsize=9, ncol=len(handles1), frameon=False, columnspacing=1.0,
                  handlelength=2.0, markerscale=15)
    ax0.grid(True, alpha=0.3)

    # ===== Chart 1: xcp_profit and virtual_price =====
    if not xcp_profit_df.empty:
        ax1.plot(xcp_profit_df['timestamp'], xcp_profit_df['xcp_profit'],
                'green', linestyle='None', marker=MAKER, markersize=MARKER_SIZE,
                alpha=0.7, label='xcp_profit')

    if not virtual_price_df.empty:
        virtual_price_df_sorted = virtual_price_df.sort_values('timestamp')
        value_changed = virtual_price_df_sorted['virtual_price'].diff().abs() > 1e-10
        value_changed.iloc[0] = True

        changed_data = virtual_price_df_sorted[value_changed]
        if not changed_data.empty:
            ax1.plot(changed_data['timestamp'], changed_data['virtual_price'],
                    'red', marker=MAKER, markersize=MARKER_SIZE, linestyle='None',
                    label='virtual_price / 2', alpha=0.7)

    ax1.set_ylabel('Value', fontsize=12)
    ax1.set_title(f'{name}: xcp_profit and virtual_price / 2', fontsize=14, fontweight='bold')

    # Chart 1 legend
    handles2_new, labels2_new = ax1.get_legend_handles_labels()
    if handles2_new:
        ax1.legend(handles2_new, labels2_new, bbox_to_anchor=(1, -0.02), loc='upper right',
                  fontsize=9, ncol=len(handles2_new), frameon=False, columnspacing=1.0,
                  handlelength=2.0, markerscale=15)
    ax1.grid(True, alpha=0.3)

    # ===== Chart 2: Refueling events =====
    ax2.set_title('Refueling events (vertical lines)', fontsize=12, fontweight='bold')
    ax2.set_ylim(0, 1)
    ax2.set_yticks([])
    ax2.spines['top'].set_visible(True)
    ax2.spines['left'].set_visible(True)
    ax2.spines['bottom'].set_visible(True)
    ax2.spines['right'].set_visible(True)
    ax2.tick_params(axis='x', which='both', bottom=False, labelbottom=False)

    # ===== Chart 3: Donation shares =====
    ax3_twin_delta = None
    ax3_twin_normalized = None

    if not donation_shares_df.empty and 'delta_filtered' in donation_shares_df.columns:
        filtered_data = donation_shares_df[donation_shares_df['delta_filtered'] != 0].copy()
        if not filtered_data.empty:
            bar_width_days = 2 / PIXELS_PER_DAY
            bar_width = timedelta(days=bar_width_days)

            ax3.bar(filtered_data['timestamp'], filtered_data['delta_filtered'],
                   width=bar_width, color='purple', label='refuel in USD',
                   align='center', edgecolor='purple', linewidth=0.1)

            # Add USD value labels
            if 'delta_usd' in filtered_data.columns:
                for idx, row in filtered_data.iterrows():
                    delta_value = row['delta_filtered']
                    delta_usd = row.get('delta_usd', 0)

                    if delta_value < -0.001 and delta_usd > 0:
                        usd_label = f"${delta_usd:.4f}"
                        ax3.text(row['timestamp'], delta_value, usd_label,
                               fontsize=6, ha='center', va='top', rotation=0,
                               bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                       alpha=0.7, edgecolor='none'))

        # Add donation shares as black line
        if not donation_shares_df.empty and 'donation_shares' in donation_shares_df.columns:
            ax3_twin_normalized = ax3.twinx()
            ax3_twin_normalized.spines['right'].set_position(('outward', 60))
            ax3_twin_normalized.plot(donation_shares_df['timestamp'],
                                   donation_shares_df['donation_shares'],
                                   'black', label='refuel_shares', linestyle='-',
                                   linewidth=1.0, alpha=0.7)
            max_shares = donation_shares_df['donation_shares'].max()
            ax3_twin_normalized.set_ylim(0, max_shares)
            ax3_twin_normalized.set_yticks([])
            ax3_twin_normalized.spines['right'].set_visible(False)

        # Add moving average
        if 'delta_usd_ma' in donation_shares_df.columns:
            if ax3_twin_normalized is not None:
                ax3_twin_delta = ax3_twin_normalized.twinx()
                ax3_twin_delta.spines['right'].set_position(('outward', 0))
            else:
                ax3_twin_delta = ax3.twinx()
            ax3_twin_delta.plot(donation_shares_df['timestamp'],
                              donation_shares_df['delta_usd_ma'],
                              'orange', label='2h MA USD Spend', linestyle='None',
                              marker=MAKER, markersize=MARKER_SIZE, alpha=0.8)
            ax3_twin_delta.set_ylabel('2h Moving Average USD Spend', fontsize=12, color='orange')
            ax3_twin_delta.tick_params(axis='y', labelcolor='orange')

        ax3.set_ylabel('refuel in shares', fontsize=12)
        ax3.set_title(f'{name}: refuel shares used to rebalance', fontsize=12, fontweight='bold')

        # Chart 3 legend
        handles3, labels3 = ax3.get_legend_handles_labels()
        if ax3_twin_normalized is not None:
            handles_twin_norm, labels_twin_norm = ax3_twin_normalized.get_legend_handles_labels()
            handles3.extend(handles_twin_norm)
            labels3.extend(labels_twin_norm)
        if ax3_twin_delta is not None:
            handles_twin3, labels_twin3 = ax3_twin_delta.get_legend_handles_labels()
            handles3.extend(handles_twin3)
            labels3.extend(labels_twin3)
        if handles3:
            ax3.legend(handles3, labels3, bbox_to_anchor=(1, -0.02), loc='upper right',
                      fontsize=9, ncol=len(handles3), frameon=False, columnspacing=1.0,
                      handlelength=2.0, markerscale=15)
        ax3.grid(True, alpha=0.3)
        ax3.axhline(y=0, color='black', linestyle='--', linewidth=0.5, alpha=0.5)
    else:
        # Fallback: plot donation shares even if delta_filtered not available
        ax3_twin_normalized = None
        if not donation_shares_df.empty and 'donation_shares' in donation_shares_df.columns:
            ax3_twin_normalized = ax3.twinx()
            ax3_twin_normalized.plot(donation_shares_df['timestamp'],
                                   donation_shares_df['donation_shares'],
                                   'black', label='refuel_shares', linestyle='-',
                                   linewidth=1.0, alpha=0.7)
            max_shares = donation_shares_df['donation_shares'].max()
            ax3_twin_normalized.set_ylim(0, max_shares)
            ax3_twin_normalized.set_yticks([])
            ax3_twin_normalized.spines['right'].set_visible(False)

            handles3, labels3 = ax3.get_legend_handles_labels()
            if ax3_twin_normalized is not None:
                handles_twin_norm, labels_twin_norm = ax3_twin_normalized.get_legend_handles_labels()
                handles3.extend(handles_twin_norm)
                labels3.extend(labels_twin_norm)
            if handles3:
                ax3.legend(handles3, labels3, bbox_to_anchor=(1, -0.02), loc='upper right',
                          fontsize=9, ncol=len(handles3), frameon=False, columnspacing=1.0,
                          handlelength=2.0, markerscale=15)
        ax3.set_ylabel('refuel in shares', fontsize=12)
        ax3.set_title(f'{name}: refuel shares used to rebalance', fontsize=12, fontweight='bold')
        ax3.grid(True, alpha=0.3)

    # ===== Chart 4: Delta price =====
    ax4_twin = None
    if not delta_price_df.empty:
        delta_usd_data = delta_price_df[delta_price_df['delta_usd'].notna()]
        if not delta_usd_data.empty:
            ax4.plot(delta_usd_data['timestamp'], delta_usd_data['delta_usd'],
                    'c', label='Delta (USD)', linestyle='None', marker=MAKER, markersize=MARKER_SIZE)

        delta_percent_data = delta_price_df[delta_price_df['delta_percent'].notna()]
        if not delta_percent_data.empty:
            ax4_twin = ax4.twinx()
            ax4_twin.axhspan(-2, 2, color='blue', alpha=0.2, zorder=0)
            ax4_twin.plot(delta_percent_data['timestamp'], delta_percent_data['delta_percent'],
                        'm', label='Delta (%)', linestyle='None', marker=MAKER, markersize=MARKER_SIZE)
            ax4_twin.set_ylabel('Delta Price Last to Scale (%)', fontsize=10, color='m')
            ax4_twin.tick_params(axis='y', labelcolor='m')

        ax4.set_ylabel('Delta Price Last to Scale (USD)', fontsize=10, color='c')
        ax4.tick_params(axis='y', labelcolor='c')
        ax4.set_title('Price Delta: last_prices() - price_scale()', fontsize=12, fontweight='bold')
        ax4.grid(True, alpha=0.3)

        # Chart 4 legend
        handles4, labels4 = ax4.get_legend_handles_labels()
        if ax4_twin is not None:
            handles_twin4, labels_twin4 = ax4_twin.get_legend_handles_labels()
            handles4.extend(handles_twin4)
            labels4.extend(labels_twin4)
        if handles4:
            ax4.legend(handles4, labels4, bbox_to_anchor=(0.5, -0.15), loc='upper center',
                      fontsize=9, ncol=len(handles4), frameon=False, columnspacing=1.0,
                      handlelength=2.0, markerscale=15)
    else:
        ax4.set_ylabel('Delta Price (USD)', fontsize=12)
        ax4.set_title('Price Delta: last_prices() - price_scale()', fontsize=12, fontweight='bold')
        ax4.grid(True, alpha=0.3)

    # ===== Add refueling event lines =====
    if donation_reset_timestamps:
        for reset_time in donation_reset_timestamps:
            ax2.axvline(x=reset_time, color='black', linestyle='-', linewidth=1, alpha=0.7)

    # ===== Format x-axis =====
    ax4.set_xlabel('Time', fontsize=12)

    for ax in [ax0, ax1, ax3, ax4]:
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax.grid(True, alpha=0.3, which='major')
        ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0]))
        ax.grid(True, alpha=0.6, which='minor', linewidth=1.5, linestyle='-')

    # ===== Add title and adjust layout =====
    if not last_prices_df.empty:
        date_str = last_prices_df['timestamp'].min().strftime('%Y-%m-%d')
    else:
        date_str = datetime.now().strftime('%Y-%m-%d')

    plt.suptitle(f'Data from {date_str} (Values from JSON cache)', fontsize=10, y=1.02)
    plt.subplots_adjust(left=0.08, bottom=0.15, right=0.95, top=0.92, hspace=0.3)

    # ===== Save the plot =====
    figure_width_pixels = (figure_width_cm / 2.54) * _INTERNAL_DPI
    plt.savefig(output_path, dpi=_INTERNAL_DPI, bbox_inches=None)

    if plot_description:
        print(f"{plot_description} saved to: {output_path} ({figure_width_pixels:.0f} x {int((FIGURE_HEIGHT_CM/2.54)*_INTERNAL_DPI)} px)")
    else:
        print(f"Chart saved to: {output_path} ({figure_width_pixels:.0f} x {int((FIGURE_HEIGHT_CM/2.54)*_INTERNAL_DPI)} px)")

    return fig, figure_width_pixels


# Calculate time range to determine figure width
# Find the earliest and latest timestamps from all dataframes
dataframes_for_dimension_calc = [
    last_prices_df, price_scale_df, price_oracle_df, donation_shares_df,
    delta_price_df, balance_df, donation_shares_usd_df, virtual_price_df, total_supply_df
]
figure_width_cm, figure_width_pixels, time_info = calculate_figure_dimensions(dataframes_for_dimension_calc)
print(f"Full plot: {time_info}, width: {figure_width_pixels:.0f} px ({figure_width_cm:.1f} cm)")

# ===== Create full version chart =====
plot_dir = Path("plots") / chain_name
plot_dir.mkdir(parents=True, exist_ok=True)

output_path = plot_dir / f'{name.replace("/", "_").replace(" ", "")}_refuel_analysis_all.png'
fig, _ = create_refuel_chart(
    last_prices_df, price_scale_df, xcp_profit_df, virtual_price_df,
    donation_shares_df, delta_price_df, donation_reset_timestamps,
    figure_width_cm, name, output_path, plot_description="Full chart"
)

# ===== Create TIME_WINDOW version chart =====
# Calculate timestamps for filtering
all_timestamps = []
for df in dataframes_for_dimension_calc:
    if not df.empty and 'timestamp' in df.columns:
        all_timestamps.extend(df['timestamp'].tolist())

if all_timestamps:
    max_time_window = max(all_timestamps)
    min_time_window = max_time_window - timedelta(hours=TIME_WINDOW_HOURS)

    # Filter all dataframes to time window
    last_prices_df_window = last_prices_df[last_prices_df['timestamp'] >= min_time_window].copy() if not last_prices_df.empty else pd.DataFrame()
    price_scale_df_window = price_scale_df[price_scale_df['timestamp'] >= min_time_window].copy() if not price_scale_df.empty else pd.DataFrame()
    xcp_profit_df_window = xcp_profit_df[xcp_profit_df['timestamp'] >= min_time_window].copy() if not xcp_profit_df.empty else pd.DataFrame()
    virtual_price_df_window = virtual_price_df[virtual_price_df['timestamp'] >= min_time_window].copy() if not virtual_price_df.empty else pd.DataFrame()
    donation_shares_df_window = donation_shares_df[donation_shares_df['timestamp'] >= min_time_window].copy() if not donation_shares_df.empty else pd.DataFrame()
    delta_price_df_window = delta_price_df[delta_price_df['timestamp'] >= min_time_window].copy() if not delta_price_df.empty else pd.DataFrame()

    # Filter reset timestamps to time window
    donation_reset_timestamps_window = [ts for ts in donation_reset_timestamps if ts >= min_time_window]

    # Calculate figure dimensions for time window data
    dataframes_window = [
        last_prices_df_window, price_scale_df_window, xcp_profit_df_window,
        virtual_price_df_window, donation_shares_df_window, delta_price_df_window
    ]
    figure_width_cm_window, figure_width_pixels_window, time_info_window = calculate_figure_dimensions(dataframes_window)
    print(f"\nCreating {TIME_WINDOW_HOURS}-hour plot: {time_info_window}, width: {figure_width_pixels_window:.0f} px ({figure_width_cm_window:.1f} cm)")

    # Create and save time window chart
    time_window_days = TIME_WINDOW_HOURS // 24
    output_path_window = plot_dir / f'{name.replace("/", "_").replace(" ", "")}_refuel_analysis_{time_window_days}d.png'
    fig_window, _ = create_refuel_chart(
        last_prices_df_window, price_scale_df_window, xcp_profit_df_window, virtual_price_df_window,
        donation_shares_df_window, delta_price_df_window, donation_reset_timestamps_window,
        figure_width_cm_window, name, output_path_window,
        plot_description=f"{TIME_WINDOW_HOURS}-hour window chart"
    )
    plt.close(fig_window)

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
    print(f"\nRefule Shares (USD):")
    print(f"  Min: ${donation_shares_usd_df['donation_shares_usd'].min():.2f}")
    print(f"  Max: ${donation_shares_usd_df['donation_shares_usd'].max():.2f}")
    print(f"  Mean: ${donation_shares_usd_df['donation_shares_usd'].mean():.2f}")
    print(f"  Latest: ${donation_shares_usd_df['donation_shares_usd'].iloc[-1]:.2f}")

if not donation_shares_df.empty:
    print(f"\nRefule Shares (raw):")
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
    print(f"\nRefule Releases:")
    print(f"  Number of unique releases detected: {len(donation_releases_df['release_time'].unique())}")
