import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np
import json
import argparse
from pathlib import Path
import seaborn as sns
from scipy import stats
from data_loader import load_fxswap_data

# Plotting constants (reused from plot_refule.py)
PIXELS_PER_DAY = 288
_INTERNAL_DPI = 100
PLOT_AREA_RATIO = 0.87
FIGURE_HEIGHT_CM = 35
MARKER_SIZE = 1
MAKER = "."
BLUE = '#3465A4'
GREEN = '#4E9A06'
ORANGE = '#F57900'
RED = '#CC0000'
PURPLE = '#75507B'
YELLOW = '#EDD400'

# Volatility calculation window (7 days as requested)
VOLATILITY_WINDOW = '7D'
VOLATILITY_WINDOW_HOURS = 7 * 24

# Load fxswap_addresses from fxswaps.json
fxswaps_path = Path(__file__).parent.parent / "config" / "fxswaps.json"
print(f"fxswaps_path: {fxswaps_path}")
fxswap_addresses = {}
if fxswaps_path.exists():
    try:
        with open(fxswaps_path, 'r') as f:
            fxswap_addresses_raw = json.load(f)
            fxswap_addresses = {int(k): v for k, v in fxswap_addresses_raw.items()}
        print(f"Loaded {len(fxswap_addresses)} pools from fxswaps.json")
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"Error loading fxswaps.json: {e}")
        fxswap_addresses = {}
else:
    print(f"fxswaps.json not found at {fxswaps_path}")
    fxswap_addresses = {}

# Parse command line arguments
parser = argparse.ArgumentParser(description='Analyze volatility and rebalancing costs for fxswap pools')
parser.add_argument('--index', type=int, default=0, help='Index of the pool to query (default: 0)')
args = parser.parse_args()

index = args.index

# Security: Validate index exists
if index not in fxswap_addresses:
    print(f"Error: Index {index} not found in fxswap_addresses")
    print(f"Available indices: {list(fxswap_addresses.keys())}")
    exit(1)

# Security: Validate required keys exist
required_keys = ["address", "name", "chain_name"]
for key in required_keys:
    if key not in fxswap_addresses[index]:
        print(f"Error: Missing required key '{key}' in fxswap_addresses[{index}]")
        exit(1)

fxswap_address = fxswap_addresses[index]["address"]
name = fxswap_addresses[index]["name"]
chain_name = fxswap_addresses[index]["chain_name"]

# Security: Validate and sanitize path components to prevent path traversal
# Remove any path separators and dangerous characters
def sanitize_path_component(component):
    """Sanitize a path component to prevent path traversal attacks."""
    if not isinstance(component, str):
        raise ValueError(f"Path component must be a string, got {type(component)}")
    # Remove path separators and dangerous characters
    sanitized = component.replace('/', '_').replace('\\', '_').replace('..', '__').replace('\x00', '')
    # Replace spaces with underscores (common in filenames)
    sanitized = sanitized.replace(' ', '_')
    # Remove any remaining dangerous characters, keep alphanumeric and safe punctuation
    sanitized = ''.join(c for c in sanitized if c.isalnum() or c in ['-', '_', '.'])
    if not sanitized:
        raise ValueError(f"Path component '{component}' became empty after sanitization")
    return sanitized

try:
    safe_chain_name = sanitize_path_component(chain_name)
    safe_address = sanitize_path_component(fxswap_address)
    safe_name = sanitize_path_component(name)
except ValueError as e:
    print(f"Error: Invalid path component: {e}")
    exit(1)

# Security: Use Path objects and resolve to prevent path traversal
base_data_dir = Path("data")
data_file_path = (base_data_dir / safe_chain_name / safe_address).resolve()

# Security: Ensure the resolved path is still within the base_data_dir
try:
    data_file_path.relative_to(base_data_dir.resolve())
except ValueError:
    print(f"Error: Path traversal detected! Refusing to access: {data_file_path}")
    exit(1)

# Load data (supports both Parquet and JSON for backward compatibility)
try:
    data = load_fxswap_data(data_file_path)
except FileNotFoundError as e:
    print(f"Error: {e}")
    exit(1)

def has_USDC(name):
    """Returns True if 'USDC' appears anywhere in the input pool name."""
    if not isinstance(name, str):
        return False
    return "USDC" in name

if has_USDC(name):
    token0_decimals = 6
    token1_decimals = 18
else:
    token0_decimals = 18
    token1_decimals = 18

print(f"Analyzing pool: {name}")
print(f"token0_decimals: {token0_decimals}, token1_decimals: {token1_decimals}")

# Parse the data from JSON
price_data = []
donation_data = []
balance_data = []
supply_data = []

# Track previous values for rebalancing detection
prev_release_ts = None

for block_number, block_data in sorted(data.items(), key=lambda x: int(x[0])):
    # Get timestamp
    timestamp = None
    if 'last_prices' in block_data:
        timestamp = datetime.fromtimestamp(block_data['last_prices']['epoch'])
    elif 'price_scale' in block_data:
        timestamp = datetime.fromtimestamp(block_data['price_scale']['epoch'])
    else:
        continue

    # Extract price data
    if 'last_prices' in block_data and 'price_scale' in block_data and 'price_oracle' in block_data:
        price_data.append({
            'timestamp': timestamp,
            'last_price': block_data['last_prices']['value'],
            'price_scale': block_data['price_scale']['value'],
            'price_oracle': block_data['price_oracle']['value']
        })

    # Extract donation/rebalancing data
    if 'donation_shares' in block_data and 'last_donation_release_ts' in block_data:
        release_ts = block_data['last_donation_release_ts']['value']
        is_rebalance = False

        # Detect rebalancing event (when last_donation_release_ts changes)
        if prev_release_ts is not None and release_ts != prev_release_ts and release_ts > 1000000000:
            is_rebalance = True

        donation_data.append({
            'timestamp': timestamp,
            'donation_shares': block_data['donation_shares']['value'],
            'is_rebalance': is_rebalance
        })

        if release_ts > 1000000000:
            prev_release_ts = release_ts

    # Extract balance and supply data
    if ('balances(0)' in block_data and 'balances(1)' in block_data and
        'totalSupply' in block_data and 'last_prices' in block_data):

        balance_0 = block_data['balances(0)']['value']
        balance_1 = block_data['balances(1)']['value']
        total_supply = block_data['totalSupply']['value']
        last_price = block_data['last_prices']['value']

        # Calculate TVL in USD
        token0_usd = balance_0
        token1_usd = balance_1 * last_price
        tvl_usd = token0_usd + token1_usd

        supply_data.append({
            'timestamp': timestamp,
            'balance_0': balance_0,
            'balance_1': balance_1,
            'totalSupply': total_supply,
            'tvl_usd': tvl_usd
        })

# Create DataFrames
price_df = pd.DataFrame(price_data).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
donation_df = pd.DataFrame(donation_data).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
supply_df = pd.DataFrame(supply_data).drop_duplicates(subset=['timestamp']).sort_values('timestamp')

print(f"Found {len(price_df)} price entries")
print(f"Found {len(donation_df)} donation entries")
print(f"Found {len(supply_df)} supply/TVL entries")

if price_df.empty:
    print("ERROR: No price data found. Cannot calculate volatility.")
    exit(1)

# Calculate returns and volatility metrics
price_df = price_df.set_index('timestamp')

# 1. Calculate returns (using last_price)
price_df['returns'] = price_df['last_price'].pct_change()
price_df['log_returns'] = np.log(price_df['last_price'] / price_df['last_price'].shift(1))

# 2. Calculate price range for each observation
price_df['price_range'] = price_df['last_price'].rolling(window='1h').max() - price_df['last_price'].rolling(window='1h').min()
price_df['price_range_pct'] = (price_df['price_range'] / price_df['last_price']) * 100

# 3. Rolling volatility metrics (7-day window)
# Standard deviation of returns (annualized)
price_df['volatility_std'] = price_df['returns'].rolling(window=VOLATILITY_WINDOW).std() * np.sqrt(365)

# Realized volatility (sum of squared returns)
price_df['volatility_realized'] = np.sqrt(
    price_df['returns'].pow(2).rolling(window=VOLATILITY_WINDOW).sum()
) * np.sqrt(365)

# Mean absolute deviation
price_df['volatility_mad'] = price_df['returns'].abs().rolling(window=VOLATILITY_WINDOW).mean() * np.sqrt(365)

# Price range volatility (high-low over window)
price_df['high_7d'] = price_df['last_price'].rolling(window=VOLATILITY_WINDOW).max()
price_df['low_7d'] = price_df['last_price'].rolling(window=VOLATILITY_WINDOW).min()
price_df['volatility_range'] = (price_df['high_7d'] - price_df['low_7d']) / price_df['last_price']

# Coefficient of variation (normalized volatility)
price_df['cv'] = (price_df['last_price'].rolling(window=VOLATILITY_WINDOW).std() /
                  price_df['last_price'].rolling(window=VOLATILITY_WINDOW).mean())

# Delta between last_price and price_scale (measure of pool imbalance)
price_df['delta_price'] = price_df['last_price'] - price_df['price_scale']
price_df['delta_price_pct'] = (price_df['delta_price'] / price_df['price_scale']) * 100
price_df['delta_abs_ma'] = price_df['delta_price_pct'].abs().rolling(window=VOLATILITY_WINDOW).mean()

price_df = price_df.reset_index()

# Calculate rebalancing costs
donation_df = donation_df.set_index('timestamp')
donation_df['donation_delta'] = donation_df['donation_shares'].diff()

# Detect when donation shares are used (negative delta)
donation_df['shares_used'] = -donation_df['donation_delta'].clip(upper=0)

# Merge with supply data to calculate USD costs
donation_df = donation_df.reset_index()
donation_df = pd.merge(donation_df, supply_df, on='timestamp', how='left')

# Calculate USD value of shares used
donation_df['cost_usd'] = donation_df.apply(
    lambda row: (row['shares_used'] / row['totalSupply']) * row['tvl_usd']
    if pd.notna(row['totalSupply']) and row['totalSupply'] > 0 and pd.notna(row['tvl_usd']) and row['shares_used'] > 0
    else 0,
    axis=1
)

# Calculate cost as percentage of TVL
donation_df['cost_pct_tvl'] = donation_df.apply(
    lambda row: (row['cost_usd'] / row['tvl_usd']) * 100
    if pd.notna(row['tvl_usd']) and row['tvl_usd'] > 0 and row['cost_usd'] > 0
    else 0,
    axis=1
)

donation_df = donation_df.set_index('timestamp')

# Rolling sum of costs (7-day window)
donation_df['cost_usd_7d'] = donation_df['cost_usd'].rolling(window=VOLATILITY_WINDOW).sum()
donation_df['cost_pct_tvl_7d'] = donation_df['cost_pct_tvl'].rolling(window=VOLATILITY_WINDOW).sum()

# Rebalancing frequency (count of events in 7-day window)
donation_df['rebalance_count_7d'] = donation_df['is_rebalance'].rolling(window=VOLATILITY_WINDOW).sum()

donation_df = donation_df.reset_index()

# Merge price and donation data for correlation analysis
merged_df = pd.merge(price_df, donation_df, on='timestamp', how='outer').sort_values('timestamp')
merged_df = merged_df.set_index('timestamp')

# Forward fill TVL for correlation analysis
if 'tvl_usd' in merged_df.columns:
    merged_df['tvl_usd'] = merged_df['tvl_usd'].ffill()

merged_df = merged_df.reset_index()

# Calculate correlation for non-NaN values
correlation_cols = ['volatility_std', 'volatility_realized', 'volatility_range', 'delta_abs_ma',
                    'cost_usd_7d', 'cost_pct_tvl_7d', 'rebalance_count_7d']
correlation_data = merged_df[correlation_cols].dropna()

print(f"\n=== Correlation Analysis ===")
print(f"Correlation matrix shape: {correlation_data.shape}")

if len(correlation_data) > 10:
    corr_matrix = correlation_data.corr()
    print("\nCorrelation Matrix:")
    print(corr_matrix)

    # Key correlations of interest
    print("\n=== Key Correlations ===")
    if 'volatility_std' in corr_matrix.columns and 'cost_pct_tvl_7d' in corr_matrix.columns:
        print(f"Volatility (Std) vs Cost/TVL: {corr_matrix.loc['volatility_std', 'cost_pct_tvl_7d']:.3f}")
    if 'volatility_std' in corr_matrix.columns and 'rebalance_count_7d' in corr_matrix.columns:
        print(f"Volatility (Std) vs Rebalance Frequency: {corr_matrix.loc['volatility_std', 'rebalance_count_7d']:.3f}")
    if 'delta_abs_ma' in corr_matrix.columns and 'cost_pct_tvl_7d' in corr_matrix.columns:
        print(f"Price Delta (abs) vs Cost/TVL: {corr_matrix.loc['delta_abs_ma', 'cost_pct_tvl_7d']:.3f}")
else:
    print("Not enough data for correlation analysis")
    corr_matrix = None

# Summary statistics
print("\n=== Summary Statistics ===")
print(f"\nPrice Statistics:")
if not price_df.empty:
    print(f"  Mean Price: ${price_df['last_price'].mean():.4f}")
    print(f"  Price Range: ${price_df['last_price'].min():.4f} - ${price_df['last_price'].max():.4f}")
    print(f"  Mean 7D Volatility (Std): {price_df['volatility_std'].mean():.2%}")
    print(f"  Mean 7D Volatility (Realized): {price_df['volatility_realized'].mean():.2%}")
    print(f"  Mean 7D Price Range: {price_df['volatility_range'].mean():.2%}")

print(f"\nRebalancing Cost Statistics:")
if not donation_df.empty:
    total_cost = donation_df['cost_usd'].sum()
    total_rebalances = donation_df['is_rebalance'].sum()
    print(f"  Total Rebalancing Events: {int(total_rebalances)}")
    print(f"  Total Cost (USD): ${total_cost:.2f}")
    if total_rebalances > 0:
        print(f"  Average Cost per Event: ${total_cost / total_rebalances:.2f}")
    if 'tvl_usd' in donation_df.columns:
        mean_tvl = donation_df['tvl_usd'].mean()
        if mean_tvl > 0:
            print(f"  Mean TVL: ${mean_tvl:.2f}")
            print(f"  Total Cost as % of Mean TVL: {(total_cost / mean_tvl) * 100:.4f}%")

# ====================
# PLOTTING SECTION
# ====================

# Calculate figure width based on time range
if not merged_df.empty:
    min_time = merged_df['timestamp'].min()
    max_time = merged_df['timestamp'].max()
    time_range = max_time - min_time
    time_range_days = time_range.total_seconds() / (24 * 3600)
    plot_area_width_pixels = time_range_days * PIXELS_PER_DAY
    figure_width_pixels = plot_area_width_pixels / PLOT_AREA_RATIO
    figure_width_cm = (figure_width_pixels / _INTERNAL_DPI) * 2.54
    figure_width_cm = max(figure_width_cm, 30.0)
    print(f"\nFigure dimensions: {time_range_days:.2f} days, width: {figure_width_pixels:.0f} px ({figure_width_cm:.1f} cm)")
else:
    figure_width_cm = 40.0

# Create output directory (using sanitized chain_name)
plot_dir = Path("plots") / safe_chain_name / "volatility"
plot_dir.mkdir(parents=True, exist_ok=True)

# ====================
# CHART 1: Comprehensive Time Series (8 subplots)
# ====================
print("\n=== Creating Chart 1: Comprehensive Time Series ===")
fig1, axes1 = plt.subplots(8, 1, figsize=(figure_width_cm/2.54, 50/2.54), sharex=True)

# Subplot 1: Price with high/low bands
ax = axes1[0]
if not price_df.empty:
    ax.plot(price_df['timestamp'], price_df['last_price'], color=BLUE, label='Spot Price',
            linestyle='None', marker=MAKER, markersize=MARKER_SIZE)
    ax.plot(price_df['timestamp'], price_df['price_scale'], color=GREEN, label='Price Scale',
            linestyle='None', marker=MAKER, markersize=MARKER_SIZE, alpha=0.5)
    # Add 7-day high/low bands
    ax.fill_between(price_df['timestamp'], price_df['low_7d'], price_df['high_7d'],
                     color=BLUE, alpha=0.1, label='7D Range')
ax.set_ylabel('Price (USD)', fontsize=10)
ax.set_title(f'{name}: Price with 7-Day Range', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='upper right', markerscale=10)
ax.grid(True, alpha=0.3)

# Subplot 2: Multiple volatility metrics
ax = axes1[1]
if not price_df.empty:
    # Plot all volatility metrics
    vol_data = price_df.dropna(subset=['volatility_std'])
    if not vol_data.empty:
        ax.plot(vol_data['timestamp'], vol_data['volatility_std'] * 100, color=RED,
                label='Std Dev (annualized)', linestyle='-', linewidth=1, alpha=0.8)

    vol_data = price_df.dropna(subset=['volatility_realized'])
    if not vol_data.empty:
        ax.plot(vol_data['timestamp'], vol_data['volatility_realized'] * 100, color=ORANGE,
                label='Realized Vol', linestyle='-', linewidth=1, alpha=0.8)

    vol_data = price_df.dropna(subset=['volatility_range'])
    if not vol_data.empty:
        ax.plot(vol_data['timestamp'], vol_data['volatility_range'] * 100, color=PURPLE,
                label='Range Vol (7D)', linestyle='-', linewidth=1, alpha=0.8)
ax.set_ylabel('Volatility (%)', fontsize=10)
ax.set_title('Volatility Metrics (7-Day Rolling)', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='upper right')
ax.grid(True, alpha=0.3)

# Subplot 3: Price delta (spot vs scale)
ax = axes1[2]
if not price_df.empty:
    ax.plot(price_df['timestamp'], price_df['delta_price_pct'], color='cyan',
            label='Delta %', linestyle='None', marker=MAKER, markersize=MARKER_SIZE)
    ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.axhspan(-2, 2, color='blue', alpha=0.1, label='±2% Band')
ax.set_ylabel('Price Delta (%)', fontsize=10)
ax.set_title('Spot Price - Price Scale (%)', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='upper right', markerscale=10)
ax.grid(True, alpha=0.3)

# Subplot 4: Absolute delta moving average
ax = axes1[3]
if not price_df.empty:
    delta_data = price_df.dropna(subset=['delta_abs_ma'])
    if not delta_data.empty:
        ax.plot(delta_data['timestamp'], delta_data['delta_abs_ma'], color='magenta',
                label='|Delta| 7D MA', linestyle='-', linewidth=1.5)
ax.set_ylabel('|Delta| 7D MA (%)', fontsize=10)
ax.set_title('Absolute Price Delta (7-Day Moving Average)', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='upper right')
ax.grid(True, alpha=0.3)

# Subplot 5: TVL
ax = axes1[4]
if not supply_df.empty:
    ax.plot(supply_df['timestamp'], supply_df['tvl_usd'], color=GREEN,
            label='TVL (USD)', linestyle='-', linewidth=1.5)
    ax.fill_between(supply_df['timestamp'], 0, supply_df['tvl_usd'], color=GREEN, alpha=0.2)
ax.set_ylabel('TVL (USD)', fontsize=10)
ax.set_title('Total Value Locked', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='upper right')
ax.grid(True, alpha=0.3)

# Subplot 6: Rebalancing events (vertical lines)
ax = axes1[5]
rebalance_events = donation_df[donation_df['is_rebalance'] == True]
if not rebalance_events.empty:
    for idx, row in rebalance_events.iterrows():
        ax.axvline(x=row['timestamp'], color=RED, linestyle='-', linewidth=1, alpha=0.7)
ax.set_ylabel('Events', fontsize=10)
ax.set_title(f'Rebalancing Events (n={len(rebalance_events)})', fontsize=12, fontweight='bold')
ax.set_ylim(0, 1)
ax.set_yticks([])
ax.grid(True, alpha=0.3)

# Subplot 7: Rebalancing costs (USD)
ax = axes1[6]
if not donation_df.empty:
    cost_data = donation_df[donation_df['cost_usd'] > 0]
    if not cost_data.empty:
        # Plot individual costs as bars
        bar_width = timedelta(hours=12)
        ax.bar(cost_data['timestamp'], cost_data['cost_usd'], width=bar_width,
               color=ORANGE, label='Cost per Event', alpha=0.7, edgecolor=ORANGE)

    # Plot 7-day cumulative costs
    cost_7d_data = donation_df.dropna(subset=['cost_usd_7d'])
    if not cost_7d_data.empty:
        ax_twin = ax.twinx()
        ax_twin.plot(cost_7d_data['timestamp'], cost_7d_data['cost_usd_7d'], color=RED,
                     label='7D Cumulative', linestyle='-', linewidth=1.5)
        ax_twin.set_ylabel('7D Cumulative Cost (USD)', fontsize=10, color=RED)
        ax_twin.tick_params(axis='y', labelcolor=RED)
ax.set_ylabel('Cost per Event (USD)', fontsize=10)
ax.set_title('Rebalancing Costs', fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='upper left')
if not cost_7d_data.empty:
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax_twin.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper left')
ax.grid(True, alpha=0.3)

# Subplot 8: Cost as % of TVL
ax = axes1[7]
if not donation_df.empty:
    cost_pct_data = donation_df[donation_df['cost_pct_tvl'] > 0]
    if not cost_pct_data.empty:
        bar_width = timedelta(hours=12)
        ax.bar(cost_pct_data['timestamp'], cost_pct_data['cost_pct_tvl'], width=bar_width,
               color=PURPLE, label='Cost % TVL', alpha=0.7, edgecolor=PURPLE)

    # Plot 7-day cumulative
    cost_7d_pct_data = donation_df.dropna(subset=['cost_pct_tvl_7d'])
    if not cost_7d_pct_data.empty:
        ax_twin = ax.twinx()
        ax_twin.plot(cost_7d_pct_data['timestamp'], cost_7d_pct_data['cost_pct_tvl_7d'],
                     color='darkred', label='7D Cumulative', linestyle='-', linewidth=1.5)
        ax_twin.set_ylabel('7D Cumulative (%)', fontsize=10, color='darkred')
        ax_twin.tick_params(axis='y', labelcolor='darkred')
ax.set_ylabel('Cost % TVL', fontsize=10)
ax.set_title('Rebalancing Cost as % of TVL', fontsize=12, fontweight='bold')
ax.set_xlabel('Time', fontsize=10)
if not cost_7d_pct_data.empty:
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax_twin.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper left')
else:
    ax.legend(fontsize=8, loc='upper left')
ax.grid(True, alpha=0.3)

# Format x-axis for all subplots
for ax in axes1:
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax.tick_params(axis='x', rotation=45)

plt.tight_layout()
output_path1 = plot_dir / f'{safe_name}_volatility_timeseries.png'
plt.savefig(output_path1, dpi=_INTERNAL_DPI, bbox_inches='tight')
print(f"Chart 1 saved to: {output_path1}")
plt.close(fig1)

# ====================
# CHART 2: Correlation Scatter Plots
# ====================
print("\n=== Creating Chart 2: Correlation Scatter Plots ===")
if corr_matrix is not None and len(correlation_data) > 10:
    fig2, axes2 = plt.subplots(2, 3, figsize=(18, 12))

    # Scatter 1: Volatility (Std) vs Cost/TVL
    ax = axes2[0, 0]
    valid_data = correlation_data.dropna(subset=['volatility_std', 'cost_pct_tvl_7d'])
    if len(valid_data) > 5:
        ax.scatter(valid_data['volatility_std'] * 100, valid_data['cost_pct_tvl_7d'],
                   color=BLUE, alpha=0.5, s=20)
        # Add trend line
        z = np.polyfit(valid_data['volatility_std'] * 100, valid_data['cost_pct_tvl_7d'], 1)
        p = np.poly1d(z)
        x_trend = np.linspace(valid_data['volatility_std'].min() * 100,
                             valid_data['volatility_std'].max() * 100, 100)
        ax.plot(x_trend, p(x_trend), color=RED, linestyle='--', linewidth=2)

        # Calculate R²
        r_value = stats.pearsonr(valid_data['volatility_std'], valid_data['cost_pct_tvl_7d'])[0]
        ax.text(0.05, 0.95, f'R = {r_value:.3f}', transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.set_xlabel('Volatility Std Dev (%) - 7D', fontsize=10)
    ax.set_ylabel('Cost as % of TVL - 7D', fontsize=10)
    ax.set_title('Volatility vs Cost/TVL', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)

    # Scatter 2: Volatility vs Rebalance Frequency
    ax = axes2[0, 1]
    valid_data = correlation_data.dropna(subset=['volatility_std', 'rebalance_count_7d'])
    if len(valid_data) > 5:
        ax.scatter(valid_data['volatility_std'] * 100, valid_data['rebalance_count_7d'],
                   color=GREEN, alpha=0.5, s=20)
        z = np.polyfit(valid_data['volatility_std'] * 100, valid_data['rebalance_count_7d'], 1)
        p = np.poly1d(z)
        x_trend = np.linspace(valid_data['volatility_std'].min() * 100,
                             valid_data['volatility_std'].max() * 100, 100)
        ax.plot(x_trend, p(x_trend), color=RED, linestyle='--', linewidth=2)

        r_value = stats.pearsonr(valid_data['volatility_std'], valid_data['rebalance_count_7d'])[0]
        ax.text(0.05, 0.95, f'R = {r_value:.3f}', transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.set_xlabel('Volatility Std Dev (%) - 7D', fontsize=10)
    ax.set_ylabel('Rebalance Count - 7D', fontsize=10)
    ax.set_title('Volatility vs Rebalance Frequency', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)

    # Scatter 3: Range Volatility vs Cost
    ax = axes2[0, 2]
    valid_data = correlation_data.dropna(subset=['volatility_range', 'cost_pct_tvl_7d'])
    if len(valid_data) > 5:
        ax.scatter(valid_data['volatility_range'] * 100, valid_data['cost_pct_tvl_7d'],
                   color=ORANGE, alpha=0.5, s=20)
        z = np.polyfit(valid_data['volatility_range'] * 100, valid_data['cost_pct_tvl_7d'], 1)
        p = np.poly1d(z)
        x_trend = np.linspace(valid_data['volatility_range'].min() * 100,
                             valid_data['volatility_range'].max() * 100, 100)
        ax.plot(x_trend, p(x_trend), color=RED, linestyle='--', linewidth=2)

        r_value = stats.pearsonr(valid_data['volatility_range'], valid_data['cost_pct_tvl_7d'])[0]
        ax.text(0.05, 0.95, f'R = {r_value:.3f}', transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.set_xlabel('Range Volatility (%) - 7D', fontsize=10)
    ax.set_ylabel('Cost as % of TVL - 7D', fontsize=10)
    ax.set_title('Range Volatility vs Cost/TVL', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)

    # Scatter 4: Price Delta vs Cost
    ax = axes2[1, 0]
    valid_data = correlation_data.dropna(subset=['delta_abs_ma', 'cost_pct_tvl_7d'])
    if len(valid_data) > 5:
        ax.scatter(valid_data['delta_abs_ma'], valid_data['cost_pct_tvl_7d'],
                   color=PURPLE, alpha=0.5, s=20)
        z = np.polyfit(valid_data['delta_abs_ma'], valid_data['cost_pct_tvl_7d'], 1)
        p = np.poly1d(z)
        x_trend = np.linspace(valid_data['delta_abs_ma'].min(),
                             valid_data['delta_abs_ma'].max(), 100)
        ax.plot(x_trend, p(x_trend), color=RED, linestyle='--', linewidth=2)

        r_value = stats.pearsonr(valid_data['delta_abs_ma'], valid_data['cost_pct_tvl_7d'])[0]
        ax.text(0.05, 0.95, f'R = {r_value:.3f}', transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.set_xlabel('|Price Delta| MA (%) - 7D', fontsize=10)
    ax.set_ylabel('Cost as % of TVL - 7D', fontsize=10)
    ax.set_title('Price Delta vs Cost/TVL', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)

    # Scatter 5: Realized Vol vs Cost
    ax = axes2[1, 1]
    valid_data = correlation_data.dropna(subset=['volatility_realized', 'cost_pct_tvl_7d'])
    if len(valid_data) > 5:
        ax.scatter(valid_data['volatility_realized'] * 100, valid_data['cost_pct_tvl_7d'],
                   color='cyan', alpha=0.5, s=20)
        z = np.polyfit(valid_data['volatility_realized'] * 100, valid_data['cost_pct_tvl_7d'], 1)
        p = np.poly1d(z)
        x_trend = np.linspace(valid_data['volatility_realized'].min() * 100,
                             valid_data['volatility_realized'].max() * 100, 100)
        ax.plot(x_trend, p(x_trend), color=RED, linestyle='--', linewidth=2)

        r_value = stats.pearsonr(valid_data['volatility_realized'], valid_data['cost_pct_tvl_7d'])[0]
        ax.text(0.05, 0.95, f'R = {r_value:.3f}', transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.set_xlabel('Realized Volatility (%) - 7D', fontsize=10)
    ax.set_ylabel('Cost as % of TVL - 7D', fontsize=10)
    ax.set_title('Realized Volatility vs Cost/TVL', fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)

    # Heatmap: Correlation matrix
    ax = axes2[1, 2]
    sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='coolwarm', center=0,
                square=True, linewidths=1, cbar_kws={"shrink": 0.8}, ax=ax,
                xticklabels=['Vol Std', 'Vol Real', 'Vol Range', '|Δ| MA', 'Cost 7D', 'Cost%TVL 7D', 'Rebal Cnt'],
                yticklabels=['Vol Std', 'Vol Real', 'Vol Range', '|Δ| MA', 'Cost 7D', 'Cost%TVL 7D', 'Rebal Cnt'])
    ax.set_title('Correlation Heatmap', fontsize=12, fontweight='bold')
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right', fontsize=8)
    plt.setp(ax.yaxis.get_majorticklabels(), rotation=0, fontsize=8)

    plt.tight_layout()
    output_path2 = plot_dir / f'{safe_name}_volatility_correlations.png'
    plt.savefig(output_path2, dpi=_INTERNAL_DPI, bbox_inches='tight')
    print(f"Chart 2 saved to: {output_path2}")
    plt.close(fig2)
else:
    print("Skipping Chart 2: Not enough data for correlation analysis")

# ====================
# CHART 3: Distribution Analysis
# ====================
print("\n=== Creating Chart 3: Distribution Analysis ===")
fig3, axes3 = plt.subplots(2, 3, figsize=(18, 12))

# Histogram 1: Returns distribution
ax = axes3[0, 0]
if not price_df.empty:
    returns_clean = price_df['returns'].dropna()
    if len(returns_clean) > 0:
        ax.hist(returns_clean * 100, bins=50, color=BLUE, alpha=0.7, edgecolor='black')
        ax.axvline(x=0, color=RED, linestyle='--', linewidth=2)
        ax.set_xlabel('Returns (%)', fontsize=10)
        ax.set_ylabel('Frequency', fontsize=10)
        ax.set_title(f'Returns Distribution (μ={returns_clean.mean()*100:.3f}%, σ={returns_clean.std()*100:.3f}%)',
                     fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3)

# Histogram 2: Volatility distribution
ax = axes3[0, 1]
if not price_df.empty:
    vol_clean = price_df['volatility_std'].dropna()
    if len(vol_clean) > 0:
        ax.hist(vol_clean * 100, bins=30, color=GREEN, alpha=0.7, edgecolor='black')
        ax.set_xlabel('Volatility Std (%) - 7D', fontsize=10)
        ax.set_ylabel('Frequency', fontsize=10)
        ax.set_title(f'Volatility Distribution (μ={vol_clean.mean()*100:.2f}%)',
                     fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3)

# Histogram 3: Cost % TVL distribution
ax = axes3[0, 2]
if not donation_df.empty:
    cost_clean = donation_df[donation_df['cost_pct_tvl'] > 0]['cost_pct_tvl'].dropna()
    if len(cost_clean) > 0:
        ax.hist(cost_clean, bins=30, color=ORANGE, alpha=0.7, edgecolor='black')
        ax.set_xlabel('Cost as % of TVL', fontsize=10)
        ax.set_ylabel('Frequency', fontsize=10)
        ax.set_title(f'Rebalancing Cost Distribution (μ={cost_clean.mean():.4f}%)',
                     fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3)

# Box plot 1: Volatility by time period
ax = axes3[1, 0]
if not price_df.empty:
    price_df_copy = price_df.copy()
    price_df_copy['week'] = pd.to_datetime(price_df_copy['timestamp']).dt.isocalendar().week
    weekly_vol = price_df_copy.groupby('week')['volatility_std'].apply(list)
    if len(weekly_vol) > 0:
        ax.boxplot([v for v in weekly_vol.values if len(v) > 0], tick_labels=weekly_vol.index)
        ax.set_xlabel('Week Number', fontsize=10)
        ax.set_ylabel('Volatility Std - 7D', fontsize=10)
        ax.set_title('Volatility Distribution by Week', fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

# Time series: Daily aggregates
ax = axes3[1, 1]
if not merged_df.empty:
    daily_agg = merged_df.set_index('timestamp').resample('1D').agg({
        'volatility_std': 'mean',
        'cost_pct_tvl': 'sum'
    }).reset_index()

    ax.bar(daily_agg['timestamp'], daily_agg['cost_pct_tvl'],
           color=PURPLE, alpha=0.6, label='Daily Cost % TVL')
    ax.set_ylabel('Daily Cost % TVL', fontsize=10, color=PURPLE)
    ax.tick_params(axis='y', labelcolor=PURPLE)

    ax2 = ax.twinx()
    ax2.plot(daily_agg['timestamp'], daily_agg['volatility_std'] * 100,
             color=RED, linewidth=2, label='Daily Avg Volatility')
    ax2.set_ylabel('Avg Volatility (%)', fontsize=10, color=RED)
    ax2.tick_params(axis='y', labelcolor=RED)

    ax.set_xlabel('Date', fontsize=10)
    ax.set_title('Daily Aggregates: Cost and Volatility', fontsize=11, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper left')

# Summary statistics table
ax = axes3[1, 2]
ax.axis('off')
summary_text = f"""
VOLATILITY & COST SUMMARY
{'='*40}

Price Statistics:
  Mean: ${price_df['last_price'].mean():.4f}
  Std Dev: ${price_df['last_price'].std():.4f}
  Min/Max: ${price_df['last_price'].min():.4f} / ${price_df['last_price'].max():.4f}

Volatility (7-Day):
  Mean Std Dev: {price_df['volatility_std'].mean()*100:.2f}%
  Mean Realized: {price_df['volatility_realized'].mean()*100:.2f}%
  Mean Range: {price_df['volatility_range'].mean()*100:.2f}%

Rebalancing:
  Total Events: {int(donation_df['is_rebalance'].sum())}
  Total Cost: ${donation_df['cost_usd'].sum():.2f}
  Mean Cost/Event: ${donation_df[donation_df['cost_usd']>0]['cost_usd'].mean():.2f}
  Mean Cost % TVL: {donation_df[donation_df['cost_pct_tvl']>0]['cost_pct_tvl'].mean():.4f}%

TVL:
  Mean: ${supply_df['tvl_usd'].mean():.2f}
  Min/Max: ${supply_df['tvl_usd'].min():.2f} / ${supply_df['tvl_usd'].max():.2f}
"""

ax.text(0.1, 0.95, summary_text, transform=ax.transAxes,
        fontsize=9, verticalalignment='top', fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout()
output_path3 = plot_dir / f'{safe_name}_volatility_distributions.png'
plt.savefig(output_path3, dpi=_INTERNAL_DPI, bbox_inches='tight')
print(f"Chart 3 saved to: {output_path3}")
plt.close(fig3)

print(f"\n{'='*60}")
print(f"Analysis complete for {name}")
print(f"All charts saved to: {plot_dir}")
print(f"{'='*60}")
