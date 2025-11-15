import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import json
import argparse
from pathlib import Path
import csv

def calculate_impermanent_loss(initial_price_ratio, future_price_ratio):
    """
    Calculate impermanent loss given initial and future price ratios.

    Args:
        initial_price_ratio: Initial price of token1/token0
        future_price_ratio: Future price of token1/token0

    Returns:
        tuple: (price_change_ratio, il_ratio)
    """
    if initial_price_ratio == 0:
        return 0, 0

    price_change_ratio = future_price_ratio / initial_price_ratio

    # IL formula: 2 * sqrt(price_ratio) / (1 + price_ratio) - 1
    il_ratio = 2 * np.sqrt(price_change_ratio) / (1 + price_change_ratio) - 1

    return price_change_ratio, il_ratio


def generate_financial_statement(pool_data, name, chain_name, start_time=None, end_time=None,
                                 token0_decimals=6, token1_decimals=18):
    """
    Generate a financial statement for a pool.

    Args:
        pool_data: Dictionary of pool data from JSON
        name: Pool name
        chain_name: Chain name
        start_time: Optional start datetime for filtering
        end_time: Optional end datetime for filtering
        token0_decimals: Decimals for token 0
        token1_decimals: Decimals for token 1

    Returns:
        dict: Financial statement data
    """
    # Parse pool data into lists
    timestamps = []
    balances_0 = []
    balances_1 = []
    last_prices = []
    donation_shares = []
    total_supplies = []

    for block_number, block_data in sorted(pool_data.items(), key=lambda x: int(x[0])):
        timestamp = None
        if 'last_prices' in block_data:
            timestamp = datetime.fromtimestamp(block_data['last_prices']['epoch'])
        elif 'price_scale' in block_data:
            timestamp = datetime.fromtimestamp(block_data['price_scale']['epoch'])
        else:
            continue

        # Apply time filters if provided
        if start_time and timestamp < start_time:
            continue
        if end_time and timestamp > end_time:
            continue

        timestamps.append(timestamp)

        if 'balances(0)' in block_data:
            balances_0.append(block_data['balances(0)']['value'])
        else:
            balances_0.append(None)

        if 'balances(1)' in block_data:
            balances_1.append(block_data['balances(1)']['value'])
        else:
            balances_1.append(None)

        if 'last_prices' in block_data:
            last_prices.append(block_data['last_prices']['value'])
        else:
            last_prices.append(None)

        if 'donation_shares' in block_data:
            donation_shares.append(block_data['donation_shares']['value'])
        else:
            donation_shares.append(None)

        if 'totalSupply' in block_data:
            total_supplies.append(block_data['totalSupply']['value'])
        else:
            total_supplies.append(None)

    if len(timestamps) == 0:
        return None

    # Get start and end values
    start_idx = 0
    end_idx = -1

    start_balance_0 = balances_0[start_idx]
    start_balance_1 = balances_1[start_idx]
    start_price = last_prices[start_idx]

    end_balance_0 = balances_0[end_idx]
    end_balance_1 = balances_1[end_idx]
    end_price = last_prices[end_idx]

    # Skip if essential data is missing
    if None in [start_balance_0, start_balance_1, start_price, end_balance_0, end_balance_1, end_price]:
        return None

    # Calculate refuel events (increases in donation_shares)
    refuel_events = []
    prev_donation_shares = None
    for i, timestamp in enumerate(timestamps):
        if donation_shares[i] is not None and total_supplies[i] is not None:
            if prev_donation_shares is not None and donation_shares[i] > prev_donation_shares:
                shares_added = donation_shares[i] - prev_donation_shares
                # Calculate USD value
                if balances_0[i] is not None and balances_1[i] is not None and last_prices[i] is not None and total_supplies[i] > 0:
                    added_ratio = shares_added / total_supplies[i]
                    token0_usd = added_ratio * balances_0[i]
                    token1_usd = added_ratio * balances_1[i] * last_prices[i]
                    total_usd = token0_usd + token1_usd

                    refuel_events.append({
                        'date': timestamp,
                        'token_amount': shares_added,
                        'usd_value': total_usd
                    })
            prev_donation_shares = donation_shares[i]

    # === ON START ===
    token0_name = name.split('/')[0] if '/' in name else "Token0"
    token1_name = name.split('/')[1].split()[0] if '/' in name else "Token1"

    on_start_token0_amount = start_balance_0
    on_start_token0_price = 1.0
    on_start_token0_usd = on_start_token0_amount * on_start_token0_price

    on_start_token1_amount = start_balance_1
    on_start_token1_price = start_price
    on_start_token1_usd = on_start_token1_amount * on_start_token1_price

    on_start_total_usd = on_start_token0_usd + on_start_token1_usd

    # === HODL ===
    hodl_token0_amount = on_start_token0_amount
    hodl_token0_price = 1.0
    hodl_token0_usd = hodl_token0_amount * hodl_token0_price

    hodl_token1_amount = on_start_token1_amount
    hodl_token1_price = end_price
    hodl_token1_usd = hodl_token1_amount * hodl_token1_price

    hodl_total_usd = hodl_token0_usd + hodl_token1_usd

    # === IMPERMANENT LOSS ===
    # Calculate using constant product formula
    initial_price_ratio = 1.0 / start_price  # token0/token1
    future_price_ratio = 1.0 / end_price

    price_change_ratio, il_ratio = calculate_impermanent_loss(initial_price_ratio, future_price_ratio)

    # Calculate new balances after IL
    # Using constant product: x * y = k
    # x = sqrt(k * current_price)
    # y = sqrt(k / current_price)
    k = on_start_token0_amount * on_start_token1_amount

    new_token0_amount = np.sqrt(k * end_price)
    new_token1_amount = np.sqrt(k / end_price)

    new_token0_usd = new_token0_amount * 1.0
    new_token1_usd = new_token1_amount * end_price
    new_total_usd = new_token0_usd + new_token1_usd

    il_usd = new_total_usd - hodl_total_usd
    il_pct = (il_usd / hodl_total_usd * 100) if hodl_total_usd > 0 else 0

    # === REAL POOL ===
    real_token0_amount = end_balance_0
    real_token0_usd = real_token0_amount * 1.0

    real_token1_amount = end_balance_1
    real_token1_usd = real_token1_amount * end_price

    real_total_usd = real_token0_usd + real_token1_usd

    # Calculate fees earned
    fee_usd = real_total_usd - new_total_usd

    # Calculate total refuel cost
    total_refuel_usd = sum(event['usd_value'] for event in refuel_events)

    # Calculate net earned (fees - refuel costs)
    earned_usd = fee_usd - total_refuel_usd

    # Calculate APR if we have enough time data
    time_span_days = (timestamps[end_idx] - timestamps[start_idx]).total_seconds() / (24 * 3600)
    apr_pct = 0
    fee_per_year_usd = 0
    balance_in_one_year_usd = real_total_usd

    if time_span_days > 0:
        apr_pct = (earned_usd / on_start_total_usd) * (365 / time_span_days) * 100 if on_start_total_usd > 0 else 0
        fee_per_year_usd = earned_usd * (365 / time_span_days)
        balance_in_one_year_usd = on_start_total_usd + fee_per_year_usd

    return {
        'pool_name': name,
        'start_date': timestamps[start_idx],
        'end_date': timestamps[end_idx],
        'time_span_days': time_span_days,

        # On Start
        'on_start': {
            'token0_name': token0_name,
            'token0_amount': on_start_token0_amount,
            'token0_price': on_start_token0_price,
            'token0_usd': on_start_token0_usd,
            'token1_name': token1_name,
            'token1_amount': on_start_token1_amount,
            'token1_price': on_start_token1_price,
            'token1_usd': on_start_token1_usd,
            'total_usd': on_start_total_usd,
        },

        # Hodl
        'hodl': {
            'token0_amount': hodl_token0_amount,
            'token0_price': hodl_token0_price,
            'token0_usd': hodl_token0_usd,
            'token1_amount': hodl_token1_amount,
            'token1_price': hodl_token1_price,
            'token1_usd': hodl_token1_usd,
            'total_usd': hodl_total_usd,
        },

        # Impermanent Loss
        'il': {
            'initial_price_ratio': initial_price_ratio,
            'future_price_ratio': future_price_ratio,
            'price_change_ratio': price_change_ratio,
            'new_token0_amount': new_token0_amount,
            'new_token0_usd': new_token0_usd,
            'new_token1_amount': new_token1_amount,
            'new_token1_usd': new_token1_usd,
            'total_usd': new_total_usd,
            'il_usd': il_usd,
            'il_pct': il_pct,
        },

        # Real Pool
        'real': {
            'token0_amount': real_token0_amount,
            'token0_usd': real_token0_usd,
            'token1_amount': real_token1_amount,
            'token1_usd': real_token1_usd,
            'total_usd': real_total_usd,
            'fee_usd': fee_usd,
            'earned_usd': earned_usd,
            'apr_pct': apr_pct,
            'fee_per_year_usd': fee_per_year_usd,
            'balance_in_one_year_usd': balance_in_one_year_usd,
        },

        # Current prices
        'current_prices': {
            'token0_price': 1.0,
            'token1_price': end_price,
        },

        # Refuel events
        'refuel_events': refuel_events,
        'total_refuel_usd': total_refuel_usd,
    }


def save_as_csv(statement, output_path):
    """Save financial statement as CSV."""
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([statement['pool_name']])
        writer.writerow([])

        # On Start
        writer.writerow(['On Start', 'Amount', 'Price', 'USD'])
        writer.writerow([
            statement['on_start']['token0_name'],
            f"{statement['on_start']['token0_amount']:.3f}",
            f"{statement['on_start']['token0_price']:.3f}",
            f"${statement['on_start']['token0_usd']:.2f}"
        ])
        writer.writerow([
            statement['on_start']['token1_name'],
            f"{statement['on_start']['token1_amount']:.3f}",
            f"{statement['on_start']['token1_price']:.3f}",
            f"${statement['on_start']['token1_usd']:.2f}"
        ])
        writer.writerow(['', '', '', f"${statement['on_start']['total_usd']:.2f}"])
        writer.writerow([])

        # Hodl
        writer.writerow(['Hodl', '', '', ''])
        writer.writerow([
            statement['on_start']['token0_name'],
            f"{statement['hodl']['token0_amount']:.3f}",
            f"{statement['hodl']['token0_price']:.3f}",
            f"${statement['hodl']['token0_usd']:.2f}"
        ])
        writer.writerow([
            statement['on_start']['token1_name'],
            f"{statement['hodl']['token1_amount']:.3f}",
            f"{statement['hodl']['token1_price']:.3f}",
            f"${statement['hodl']['token1_usd']:.2f}"
        ])
        writer.writerow(['', '', '', f"${statement['hodl']['total_usd']:.2f}"])
        writer.writerow([])

        # Impermanent Loss
        writer.writerow(['Impermanent Loss', '', '', ''])
        writer.writerow(['Initial Price Ratio', f"{statement['il']['initial_price_ratio']:.5f}", '', ''])
        writer.writerow(['Future Price Ratio', f"{statement['il']['future_price_ratio']:.5f}", '', ''])
        writer.writerow(['Price Change Ratio', f"{statement['il']['price_change_ratio']:.5f}", '', ''])
        writer.writerow([])
        writer.writerow([
            f"New {statement['on_start']['token0_name']}",
            f"{statement['il']['new_token0_amount']:.4f}",
            f"{statement['on_start']['token0_price']:.4f}",
            f"${statement['il']['new_token0_usd']:.2f}"
        ])
        writer.writerow([
            f"New {statement['on_start']['token1_name']}",
            f"{statement['il']['new_token1_amount']:.4f}",
            f"{statement['current_prices']['token1_price']:.4f}",
            f"${statement['il']['new_token1_usd']:.2f}"
        ])
        writer.writerow(['Value in ($)', f"{statement['il']['total_usd']:.4f}", '', f"${statement['il']['total_usd']:.2f}"])
        writer.writerow(['IL ($)', f"{statement['il']['il_usd']:.3f}", '', ''])
        writer.writerow(['IL (%)', f"{statement['il']['il_pct']:.2f}%", '', ''])
        writer.writerow([])

        # Real Pool
        writer.writerow(['Real Pool', '', '', ''])
        writer.writerow([
            statement['on_start']['token0_name'],
            f"{statement['real']['token0_amount']:.2f}",
            '1',
            f"${statement['real']['token0_usd']:.2f}"
        ])
        writer.writerow([
            statement['on_start']['token1_name'],
            f"{statement['real']['token1_amount']:.2f}",
            f"{statement['current_prices']['token1_price']:.2f}",
            f"${statement['real']['token1_usd']:.2f}"
        ])
        writer.writerow(['Value', '', '', f"${statement['real']['total_usd']:.2f}"])
        writer.writerow(['Fee', '', '', f"${statement['real']['fee_usd']:.2f}"])
        writer.writerow(['Refuel used to date', '', '', f"-${statement['total_refuel_usd']:.2f}"])
        writer.writerow(['Earned', '', '', f"${statement['real']['earned_usd']:.2f}"])
        writer.writerow(['APR timespan', f"{statement['time_span_days']:.2f}", '', f"{statement['real']['apr_pct']:.2f}%"])
        writer.writerow(['APR year', '', '', f"{statement['real']['apr_pct']:.2f}%"])
        writer.writerow(['Fee per year', '', '', f"${statement['real']['fee_per_year_usd']:.2f}"])
        writer.writerow(['Balance in one year', '', '', f"${statement['real']['balance_in_one_year_usd']:.2f}"])
        writer.writerow([])

        # Prices
        writer.writerow([f"Price Token 0", statement['on_start']['token0_name'], f"{statement['current_prices']['token0_price']:.2f}", ''])
        writer.writerow([f"Price Token 1", statement['on_start']['token1_name'], f"{statement['current_prices']['token1_price']:.2f}", ''])
        writer.writerow([])

        # Refuel events
        writer.writerow(['Refuel', '', '', ''])
        for event in statement['refuel_events']:
            writer.writerow([
                event['date'].strftime('%Y-%m-%d %H:%M:%S'),
                f"{event['token_amount']:.6f}",
                '',
                f"${event['usd_value']:.2f}"
            ])
        writer.writerow([])
        writer.writerow(['Total', '', '', f"${statement['total_refuel_usd']:.2f}"])


def save_as_markdown(statement, output_path):
    """Save financial statement as markdown."""
    with open(output_path, 'w') as f:
        # Header
        f.write(f"# {statement['pool_name']}\n\n")
        f.write(f"Period: {statement['start_date'].strftime('%Y-%m-%d %H:%M:%S')} to {statement['end_date'].strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Duration: {statement['time_span_days']:.2f} days\n\n")

        # On Start
        f.write("## On Start\n\n")
        f.write("| Asset | Amount | Price | USD |\n")
        f.write("|-------|--------|-------|-----|\n")
        f.write(f"| {statement['on_start']['token0_name']} | {statement['on_start']['token0_amount']:.3f} | {statement['on_start']['token0_price']:.3f} | ${statement['on_start']['token0_usd']:,.2f} |\n")
        f.write(f"| {statement['on_start']['token1_name']} | {statement['on_start']['token1_amount']:.3f} | {statement['on_start']['token1_price']:.3f} | ${statement['on_start']['token1_usd']:,.2f} |\n")
        f.write(f"| **Total** | | | **${statement['on_start']['total_usd']:,.2f}** |\n\n")

        # Hodl
        f.write("## Hodl\n\n")
        f.write("| Asset | Amount | Price | USD |\n")
        f.write("|-------|--------|-------|-----|\n")
        f.write(f"| {statement['on_start']['token0_name']} | {statement['hodl']['token0_amount']:.3f} | {statement['hodl']['token0_price']:.3f} | ${statement['hodl']['token0_usd']:,.2f} |\n")
        f.write(f"| {statement['on_start']['token1_name']} | {statement['hodl']['token1_amount']:.3f} | {statement['hodl']['token1_price']:.3f} | ${statement['hodl']['token1_usd']:,.2f} |\n")
        f.write(f"| **Total** | | | **${statement['hodl']['total_usd']:,.2f}** |\n\n")

        # Impermanent Loss
        f.write("## Impermanent Loss\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Initial Price Ratio | {statement['il']['initial_price_ratio']:.5f} |\n")
        f.write(f"| Future Price Ratio | {statement['il']['future_price_ratio']:.5f} |\n")
        f.write(f"| Price Change Ratio | {statement['il']['price_change_ratio']:.5f} |\n\n")

        f.write("| Asset | Amount | Price | USD |\n")
        f.write("|-------|--------|-------|-----|\n")
        f.write(f"| New {statement['on_start']['token0_name']} | {statement['il']['new_token0_amount']:.4f} | {statement['on_start']['token0_price']:.4f} | ${statement['il']['new_token0_usd']:,.2f} |\n")
        f.write(f"| New {statement['on_start']['token1_name']} | {statement['il']['new_token1_amount']:.4f} | {statement['current_prices']['token1_price']:.4f} | ${statement['il']['new_token1_usd']:,.2f} |\n")
        f.write(f"| **Value** | | | **${statement['il']['total_usd']:,.2f}** |\n")
        f.write(f"| IL ($) | {statement['il']['il_usd']:.3f} | | |\n")
        f.write(f"| IL (%) | {statement['il']['il_pct']:.2f}% | | |\n\n")

        # Real Pool
        f.write("## Real Pool\n\n")
        f.write("| Asset | Amount | Price | USD |\n")
        f.write("|-------|--------|-------|-----|\n")
        f.write(f"| {statement['on_start']['token0_name']} | {statement['real']['token0_amount']:.2f} | 1 | ${statement['real']['token0_usd']:,.2f} |\n")
        f.write(f"| {statement['on_start']['token1_name']} | {statement['real']['token1_amount']:.2f} | {statement['current_prices']['token1_price']:.2f} | ${statement['real']['token1_usd']:,.2f} |\n")
        f.write(f"| **Value** | | | **${statement['real']['total_usd']:,.2f}** |\n")
        f.write(f"| Fee | | | ${statement['real']['fee_usd']:.2f} |\n")
        f.write(f"| Refuel used to date | | | -${statement['total_refuel_usd']:.2f} |\n")
        f.write(f"| **Earned** | | | **${statement['real']['earned_usd']:.2f}** |\n\n")

        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| APR timespan | {statement['time_span_days']:.2f} days - {statement['real']['apr_pct']:.2f}% |\n")
        f.write(f"| APR year | {statement['real']['apr_pct']:.2f}% |\n")
        f.write(f"| Fee per year | ${statement['real']['fee_per_year_usd']:,.2f} |\n")
        f.write(f"| Balance in one year | ${statement['real']['balance_in_one_year_usd']:,.2f} |\n\n")

        # Prices
        f.write("## Current Prices\n\n")
        f.write(f"- {statement['on_start']['token0_name']}: ${statement['current_prices']['token0_price']:.2f}\n")
        f.write(f"- {statement['on_start']['token1_name']}: ${statement['current_prices']['token1_price']:.2f}\n\n")

        # Refuel events
        if statement['refuel_events']:
            f.write("## Refuel\n\n")
            f.write("| Date | Token Amount | USD Value |\n")
            f.write("|------|--------------|----------|\n")
            for event in statement['refuel_events']:
                f.write(f"| {event['date'].strftime('%Y-%m-%d %H:%M:%S')} | {event['token_amount']:.6f} | ${event['usd_value']:.2f} |\n")
            f.write(f"| **Total** | | **${statement['total_refuel_usd']:.2f}** |\n\n")


def main():
    # Load fxswap_addresses from fxswaps.json
    fxswaps_path = Path(__file__).parent.parent / "config" / "fxswaps.json"
    with open(fxswaps_path, 'r') as f:
        fxswap_addresses_raw = json.load(f)
        fxswap_addresses = {int(k): v for k, v in fxswap_addresses_raw.items()}

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate financial statements for fxswap pools')
    parser.add_argument('--index', type=int, default=0, help='Index of the pool to query (default: 0)')
    args = parser.parse_args()

    index = args.index
    fxswap_address = fxswap_addresses[index]["address"]
    name = fxswap_addresses[index]["name"]
    chain_name = fxswap_addresses[index]["chain_name"]

    # Check if pool has USDC to determine decimals
    if "USDC" in name:
        token0_decimals = 6
        token1_decimals = 18
    else:
        token0_decimals = 18
        token1_decimals = 18

    # Load pool data
    json_file_path = Path(__file__).parent.parent / f'data/{chain_name}/{fxswap_address}.json'
    with open(json_file_path, 'r') as f:
        pool_data = json.load(f)

    print(f"\nGenerating financial statements for: {name}")
    print(f"Chain: {chain_name}")
    print(f"Address: {fxswap_address}")

    # Create output directory
    statements_dir = Path(__file__).parent.parent / "financial_statements" / chain_name
    statements_dir.mkdir(parents=True, exist_ok=True)

    # Generate statement from start of data
    print("\n=== Financial Statement: From Start ===")
    statement_all = generate_financial_statement(
        pool_data, name, chain_name,
        token0_decimals=token0_decimals,
        token1_decimals=token1_decimals
    )

    if statement_all:
        # Save as CSV
        csv_path = statements_dir / f'{name.replace("/", "_").replace(" ", "")}_all.csv'
        save_as_csv(statement_all, csv_path)
        print(f"Saved CSV: {csv_path}")

        # Save as markdown
        md_path = statements_dir / f'{name.replace("/", "_").replace(" ", "")}_all.md'
        save_as_markdown(statement_all, md_path)
        print(f"Saved Markdown: {md_path}")

        print(f"\nPeriod: {statement_all['start_date']} to {statement_all['end_date']}")
        print(f"Duration: {statement_all['time_span_days']:.2f} days")
        print(f"APR: {statement_all['real']['apr_pct']:.2f}%")
        print(f"Earned: ${statement_all['real']['earned_usd']:.2f}")
    else:
        print("Could not generate statement from start (missing data)")

    # Generate statement for last 7 days
    print("\n=== Financial Statement: Last 7 Days ===")

    # Find the latest timestamp in the data
    latest_timestamp = None
    for block_number, block_data in pool_data.items():
        if 'last_prices' in block_data:
            ts = datetime.fromtimestamp(block_data['last_prices']['epoch'])
            if latest_timestamp is None or ts > latest_timestamp:
                latest_timestamp = ts

    if latest_timestamp:
        start_time_7d = latest_timestamp - timedelta(days=7)

        statement_7d = generate_financial_statement(
            pool_data, name, chain_name,
            start_time=start_time_7d,
            token0_decimals=token0_decimals,
            token1_decimals=token1_decimals
        )

        if statement_7d:
            # Save as CSV
            csv_path_7d = statements_dir / f'{name.replace("/", "_").replace(" ", "")}_7d.csv'
            save_as_csv(statement_7d, csv_path_7d)
            print(f"Saved CSV: {csv_path_7d}")

            # Save as markdown
            md_path_7d = statements_dir / f'{name.replace("/", "_").replace(" ", "")}_7d.md'
            save_as_markdown(statement_7d, md_path_7d)
            print(f"Saved Markdown: {md_path_7d}")

            print(f"\nPeriod: {statement_7d['start_date']} to {statement_7d['end_date']}")
            print(f"Duration: {statement_7d['time_span_days']:.2f} days")
            print(f"APR: {statement_7d['real']['apr_pct']:.2f}%")
            print(f"Earned: ${statement_7d['real']['earned_usd']:.2f}")
        else:
            print("Could not generate 7-day statement (missing data)")

    print("\nFinancial statement generation complete!")


if __name__ == "__main__":
    main()
