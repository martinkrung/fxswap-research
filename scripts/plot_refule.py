import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # Headless mode for CI
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from data_loader import load_fxswap_data
from html_generator import generate_market_page, generate_overview_page

# Plotting constants
_INTERNAL_DPI = 100  # Used to convert pixels to cm for matplotlib figsize
PLOT_AREA_RATIO = 0.87  # Plot area takes up approx 87% of figure width with margins
FIGURE_HEIGHT_CM = 35  # Fixed height in cm
MARKER_SIZE = 1  # Size of markers for all data points
MAKER = "."  # Use this constant instead of the literal maker string
BLUE = "#3465A4"
GREEN = "#4E9A06"
ORANGE = "#F57900"

def slugify(text):
    return re.sub(r'[\W_]+', '_', text).strip('_')

def get_week_start(dt):
    """Get the Monday 00:00:00 UTC of the week for a given datetime."""
    return (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

def process_pool(pool_info, force=False):
    address = pool_info["address"]
    name = pool_info["name"]
    chain_name = pool_info["chain_name"]
    pool_slug = slugify(name)
    
    print(f"\nProcessing pool: {name} ({chain_name})")
    
    data_file_path = Path(f"data/{chain_name}/{address}")
    try:
        data = load_fxswap_data(data_file_path)
    except Exception as e:
        print(f"Error loading data for {name}: {e}")
        return []

    if not data:
        print(f"No data found for {name}")
        return []

    # Original complex data processing logic
    last_prices_data = []
    price_scale_data = []
    price_oracle_data = []
    donation_shares_data = []
    donation_releases = []
    donation_reset_timestamps = []
    virtual_price_data = []
    total_supply_data = []
    xcp_profit_data = []
    balance_data = []
    delta_price_data = []

    prev_release_ts = None

    for _block_number, block_data in sorted(data.items(), key=lambda x: int(x[0])):
        timestamp = None
        if "last_prices" in block_data:
            timestamp = datetime.fromtimestamp(block_data["last_prices"]["epoch"])
        elif "price_scale" in block_data:
            timestamp = datetime.fromtimestamp(block_data["price_scale"]["epoch"])
        else:
            continue

        if "last_prices" in block_data:
            last_prices_data.append({"timestamp": timestamp, "last_price": block_data["last_prices"]["value"]})
        if "price_scale" in block_data:
            price_scale_data.append({"timestamp": timestamp, "price_scale": block_data["price_scale"]["value"]})
        if "price_oracle" in block_data:
            price_oracle_data.append({"timestamp": timestamp, "price_oracle": block_data["price_oracle"]["value"]})
        if "donation_shares" in block_data:
            donation_shares_data.append({"timestamp": timestamp, "donation_shares": block_data["donation_shares"]["value"]})
        if "totalSupply" in block_data:
            total_supply_data.append({"timestamp": timestamp, "totalSupply": block_data["totalSupply"]["value"]})
        if "virtual_price" in block_data:
            virtual_price_data.append({"timestamp": timestamp, "virtual_price": (block_data["virtual_price"]["value"] - 1)})
        if "xcp_profit" in block_data:
            xcp_profit_data.append({"timestamp": timestamp, "xcp_profit": (block_data["xcp_profit"]["value"] - 1) / 2})
        
        balance_0 = block_data.get("balances(0)", {}).get("value")
        balance_1 = block_data.get("balances(1)", {}).get("value")
        if balance_0 is not None or balance_1 is not None:
            balance_data.append({"timestamp": timestamp, "balance_0": balance_0, "balance_1": balance_1})

        if "last_donation_release_ts" in block_data:
            release_ts = block_data["last_donation_release_ts"]["value"]
            if release_ts > 1000000000:
                release_time = datetime.fromtimestamp(release_ts)
                donation_releases.append({"timestamp": timestamp, "release_time": release_time})
                if prev_release_ts is not None and release_ts != prev_release_ts:
                    donation_reset_timestamps.append(timestamp)
                prev_release_ts = release_ts
            elif prev_release_ts is not None and release_ts <= 1000000000:
                donation_reset_timestamps.append(timestamp)
                prev_release_ts = None

        if "last_prices" in block_data and "price_scale" in block_data:
            lp = block_data["last_prices"]["value"]
            ps = block_data["price_scale"]["value"]
            delta_usd = lp - ps
            delta_percent = (delta_usd / ps) * 100 if ps != 0 else 0
            delta_price_data.append({"timestamp": timestamp, "delta_usd": delta_usd, "delta_percent": delta_percent})

    last_prices_df = pd.DataFrame(last_prices_data).drop_duplicates(subset=["timestamp"]).sort_values("timestamp") if last_prices_data else pd.DataFrame()
    price_scale_df = pd.DataFrame(price_scale_data).drop_duplicates(subset=["timestamp"]).sort_values("timestamp") if price_scale_data else pd.DataFrame()
    donation_shares_df = pd.DataFrame(donation_shares_data).drop_duplicates(subset=["timestamp"]).sort_values("timestamp") if donation_shares_data else pd.DataFrame()
    virtual_price_df = pd.DataFrame(virtual_price_data).drop_duplicates(subset=["timestamp"]).sort_values("timestamp") if virtual_price_data else pd.DataFrame()
    xcp_profit_df = pd.DataFrame(xcp_profit_data).drop_duplicates(subset=["timestamp"]).sort_values("timestamp") if xcp_profit_data else pd.DataFrame()
    total_supply_df = pd.DataFrame(total_supply_data).drop_duplicates(subset=["timestamp"]).sort_values("timestamp") if total_supply_data else pd.DataFrame()
    balance_df = pd.DataFrame(balance_data).drop_duplicates(subset=["timestamp"]).sort_values("timestamp") if balance_data else pd.DataFrame()
    delta_price_df = pd.DataFrame(delta_price_data).drop_duplicates(subset=["timestamp"]).sort_values("timestamp") if delta_price_data else pd.DataFrame()

    if not donation_shares_df.empty:
        donation_shares_df["delta"] = donation_shares_df["donation_shares"].diff().fillna(0)
        donation_shares_df["delta_filtered"] = donation_shares_df["delta"].apply(lambda x: x if x < 0 else 0)
        if not total_supply_df.empty:
            donation_shares_df = pd.merge(donation_shares_df, total_supply_df, on="timestamp", how="left")
        if not balance_df.empty:
            donation_shares_df = pd.merge(donation_shares_df, balance_df, on="timestamp", how="left")
        if not last_prices_df.empty:
            donation_shares_df = pd.merge(donation_shares_df, last_prices_df, on="timestamp", how="left")
        
        def calc_delta_usd(row):
            if row["delta_filtered"] != 0 and pd.notna(row.get("totalSupply")) and row.get("totalSupply", 0) > 0 and pd.notna(row.get("balance_0")) and pd.notna(row.get("balance_1")) and pd.notna(row.get("last_price")):
                ratio = abs(row["delta_filtered"]) / row["totalSupply"]
                return ratio * row["balance_0"] + ratio * row["balance_1"] * row["last_price"]
            return 0
        
        donation_shares_df["delta_usd"] = donation_shares_df.apply(calc_delta_usd, axis=1)
        donation_shares_df["delta_usd_ma"] = donation_shares_df.set_index("timestamp")["delta_usd"].rolling(window="2h", min_periods=1).mean().values

    all_ts = []
    for df in [last_prices_df, price_scale_df, donation_shares_df]:
        if not df.empty: all_ts.extend(df["timestamp"].tolist())
    
    if not all_ts: return []
    
    first_ts = min(all_ts)
    last_ts = max(all_ts)
    current_week_start = get_week_start(first_ts)
    
    output_dir = Path("plots") / chain_name / pool_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Stride determines the number of pixels per day roughly
    stride = 100 if pool_info["chain_id"] == 8453 else 20
    # On Base (stride 100, 2s blocks) -> ~432 points per day
    # On Ethereum (stride 20, 12s blocks) -> ~360 points per day
    # But user wants "one block = one pixel". So we use the maximum theoretical points per week.
    points_per_week = (7 * 24 * 3600) // (stride * (2 if pool_info["chain_id"] == 8453 else 12))
    # We'll use a fixed pixels_per_day based on the stride
    if pool_info["chain_id"] == 8453:
        pixels_per_day = 432 # 86400 / 200
    else:
        pixels_per_day = 360 # 86400 / 240

    plot_files = []
    while current_week_start <= last_ts:
        week_end = current_week_start + timedelta(days=7)
        iso_year, iso_week, _ = current_week_start.isocalendar()
        monday_str = current_week_start.strftime('%Y-%m-%d')
        filename = f"week_{iso_year}_W{iso_week:02d}_{monday_str}.png"
        filepath = output_dir / filename
        
        if not filepath.exists() or force:
            w_lp = last_prices_df[(last_prices_df["timestamp"] >= current_week_start) & (last_prices_df["timestamp"] < week_end)]
            w_ps = price_scale_df[(price_scale_df["timestamp"] >= current_week_start) & (price_scale_df["timestamp"] < week_end)]
            w_ds = donation_shares_df[(donation_shares_df["timestamp"] >= current_week_start) & (donation_shares_df["timestamp"] < week_end)] if not donation_shares_df.empty else pd.DataFrame()
            w_vp = virtual_price_df[(virtual_price_df["timestamp"] >= current_week_start) & (virtual_price_df["timestamp"] < week_end)]
            w_xp = xcp_profit_df[(xcp_profit_df["timestamp"] >= current_week_start) & (xcp_profit_df["timestamp"] < week_end)]
            w_dp = delta_price_df[(delta_price_df["timestamp"] >= current_week_start) & (delta_price_df["timestamp"] < week_end)]
            w_resets = [ts for ts in donation_reset_timestamps if current_week_start <= ts < week_end]
            
            if not any(not d.empty for d in [w_lp, w_ps, w_ds, w_vp, w_xp, w_dp]):
                current_week_start = week_end
                continue

            # Calculate width: 1 pixel per data point (theoretical)
            # Area width = 7 days * pixels_per_day
            area_width = 7 * pixels_per_day
            figure_width_pixels = area_width / PLOT_AREA_RATIO
            figure_width_cm = (figure_width_pixels / _INTERNAL_DPI) * 2.54

            create_refuel_chart(
                w_lp, w_ps, w_xp, w_vp, w_ds, w_dp, w_resets,
                figure_width_cm, name, filepath, current_week_start, week_end, pixels_per_day
            )
            
        plot_files.append(filepath)
        current_week_start = week_end

    generate_market_page(pool_info, [str(f.relative_to(output_dir)) for f in plot_files], output_dir)
    return plot_files

def create_refuel_chart(lp_df, ps_df, xp_df, vp_df, ds_df, dp_df, resets, width_cm, pool_name, output_path, start_time, end_time, pixels_per_day):
    fig, axes = plt.subplots(5, 1, figsize=(width_cm / 2.54, FIGURE_HEIGHT_CM / 2.54), sharex=True,
                             height_ratios=[18, 18, 2, 18, 18])
    ax0, ax1, ax2, ax3, ax4 = axes

    if not lp_df.empty:
        ax0.plot(lp_df["timestamp"], lp_df["last_price"], color=BLUE, label="spot price", linestyle="None", marker=MAKER, markersize=MARKER_SIZE)
    if not ps_df.empty:
        ax0.plot(ps_df["timestamp"], ps_df["price_scale"], color=GREEN, label="price scale", linestyle="None", marker=MAKER, markersize=MARKER_SIZE)
    
    ax1_twin = ax0.twinx()
    if not lp_df.empty:
        ax1_twin.set_ylabel("Price % of Max", color="black")
    
    ax0.set_ylabel("Price (USD)")
    ax0.set_title(f"{pool_name}: Spot and Scale Prices Over Time", fontweight="bold")
    ax0.grid(True, alpha=0.3)
    h0, l0 = ax0.get_legend_handles_labels()
    if h0: ax0.legend(h0, l0, bbox_to_anchor=(1, -0.02), loc="upper right", ncol=len(h0), frameon=False, markerscale=15)

    if not xp_df.empty:
        ax1.plot(xp_df["timestamp"], xp_df["xcp_profit"], color="green", label="xcp_profit", linestyle="None", marker=MAKER, markersize=MARKER_SIZE)
    if not vp_df.empty:
        ax1.plot(vp_df["timestamp"], vp_df["virtual_price"] / 2, color="red", label="virtual_price / 2", linestyle="None", marker=MAKER, markersize=MARKER_SIZE)
    ax1.set_ylabel("Value")
    ax1.grid(True, alpha=0.3)
    h1, l1 = ax1.get_legend_handles_labels()
    if h1: ax1.legend(h1, l1, bbox_to_anchor=(1, -0.02), loc="upper right", ncol=len(h1), frameon=False, markerscale=15)

    ax2.set_title("Refueling events (vertical lines)", fontweight="bold", fontsize=10)
    ax2.set_ylim(0, 1)
    ax2.set_yticks([])
    for ts in resets:
        ax2.axvline(x=ts, color="black", linestyle="-", linewidth=1, alpha=0.7)

    ax3_twin_norm = ax3.twinx()
    ax3_twin_delta = None
    if not ds_df.empty:
        usage = ds_df[ds_df["delta_filtered"] != 0]
        if not usage.empty:
            bar_w = timedelta(days=2/pixels_per_day)
            ax3.bar(usage["timestamp"], usage["delta_filtered"], width=bar_w, color="purple", label="refuel in USD")
            for _, row in usage.iterrows():
                if row["delta_filtered"] < -0.001 and row.get("delta_usd", 0) > 0:
                    ax3.text(row["timestamp"], row["delta_filtered"], f"${row['delta_usd']:.4f}", fontsize=6, ha="center", va="top", bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7, edgecolor="none"))
        
        ax3_twin_norm.plot(ds_df["timestamp"], ds_df["donation_shares"], color="black", label="refuel_shares", alpha=0.7)
        ax3_twin_norm.set_yticks([])
        
        if "delta_usd_ma" in ds_df.columns:
            ax3_twin_delta = ax3_twin_norm.twinx()
            ax3_twin_delta.plot(ds_df["timestamp"], ds_df["delta_usd_ma"], color="orange", label="2h MA USD Spend", linestyle="None", marker=MAKER, markersize=MARKER_SIZE)
            ax3_twin_delta.set_ylabel("2h MA USD Spend", color="orange")
            ax3_twin_delta.tick_params(axis='y', labelcolor='orange')

    ax3.set_ylabel("refuel in shares")
    ax3.grid(True, alpha=0.3)
    ax3.axhline(y=0, color="black", linestyle="--", linewidth=0.5, alpha=0.5)
    h3, l3 = ax3.get_legend_handles_labels()
    h3n, l3n = ax3_twin_norm.get_legend_handles_labels(); h3.extend(h3n); l3.extend(l3n)
    if ax3_twin_delta:
        h3d, l3d = ax3_twin_delta.get_legend_handles_labels(); h3.extend(h3d); l3.extend(l3d)
    if h3: ax3.legend(h3, l3, bbox_to_anchor=(1, -0.02), loc="upper right", ncol=len(h3), frameon=False, markerscale=15)

    ax4_twin = ax4.twinx()
    if not dp_df.empty:
        ax4.plot(dp_df["timestamp"], dp_df["delta_usd"], color="c", label="Delta (USD)", linestyle="None", marker=MAKER, markersize=MARKER_SIZE)
        ax4_twin.plot(dp_df["timestamp"], dp_df["delta_percent"], color="m", label="Delta (%)", linestyle="None", marker=MAKER, markersize=MARKER_SIZE)
        ax4_twin.axhspan(-2, 2, color="blue", alpha=0.2)
        ax4_twin.set_ylabel("Delta Price Last to Scale (%)", color="m")
        ax4_twin.tick_params(axis='y', labelcolor='m')
    ax4.set_ylabel("Delta Price (USD)", color="c")
    ax4.tick_params(axis='y', labelcolor='c')
    ax4.grid(True, alpha=0.3)
    h4, l4 = ax4.get_legend_handles_labels()
    h4t, l4t = ax4_twin.get_legend_handles_labels(); h4.extend(h4t); l4.extend(l4t)
    if h4: ax4.legend(h4, l4, bbox_to_anchor=(0.5, -0.15), loc="upper center", ncol=len(h4), frameon=False, markerscale=15)

    ax4.set_xlim(start_time, end_time)
    ax4.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, ha="right")
    for ax in [ax0, ax1, ax3, ax4]:
        ax.grid(True, alpha=0.3, which="major")
        ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0]))
        ax.grid(True, alpha=0.6, which="minor", linewidth=1.5, linestyle="-")

    plt.suptitle(f"Data from {start_time.strftime('%Y-%m-%d')} (Values from Parquet cache)", fontsize=10, y=0.98)
    plt.subplots_adjust(left=0.08, bottom=0.15, right=0.95, top=0.92, hspace=0.3)
    plt.savefig(output_path, dpi=_INTERNAL_DPI)
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, default=None, help="Index of the pool in fxswaps.json")
    parser.add_argument("--all", action="store_true", help="Process all pools in fxswaps.json")
    parser.add_argument("--force", action="store_true", help="Force recreate all plots")
    args = parser.parse_args()

    fxswaps_path = Path(__file__).parent.parent / "config" / "fxswaps.json"
    with open(fxswaps_path) as f:
        fxswap_addresses = {int(k): v for k, v in json.load(f).items()}

    pools_to_process = sorted(fxswap_addresses.keys()) if args.all else ([args.index] if args.index is not None else [0])

    for idx in pools_to_process:
        pool_info = fxswap_addresses[idx]
        process_pool(pool_info, force=args.force)
        
        # After each pool, regenerate overview based on ALL existing folders in plots/
        update_global_overview(fxswap_addresses)

def update_global_overview(all_pool_configs):
    overview_data = []
    plots_root = Path("plots")
    if not plots_root.exists(): return

    # Map pool names to their info
    name_to_info = {v["name"]: v for v in all_pool_configs.values()}
    
    # Iterate over chains and slugs
    for chain_dir in plots_root.iterdir():
        if not chain_dir.is_dir(): continue
        for slug_dir in chain_dir.iterdir():
            if not slug_dir.is_dir(): continue
            
            # Find index.html and latest plot
            market_index = slug_dir / "index.html"
            if not market_index.exists(): continue
            
            # Find latest PNG
            pngs = sorted(list(slug_dir.glob("*.png")))
            if not pngs: continue
            latest_plot = pngs[-1]
            
            # Try to find matching pool info by slug
            matched_info = None
            for p_info in all_pool_configs.values():
                if slugify(p_info["name"]) == slug_dir.name and p_info["chain_name"] == chain_dir.name:
                    matched_info = p_info
                    break
            
            if matched_info:
                rel_img_path = latest_plot.relative_to(plots_root)
                rel_link_path = market_index.relative_to(plots_root)
                overview_data.append({
                    "info": matched_info,
                    "latest_plot": str(rel_img_path),
                    "link": str(rel_link_path)
                })
    
    if overview_data:
        generate_overview_page(overview_data, "plots/index.html")
        print(f"Updated global overview with {len(overview_data)} markets.")

if __name__ == "__main__":
    main()
