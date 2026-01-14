import json
from pathlib import Path
from datetime import datetime

def generate_market_page(pool_info, plot_files, output_dir):
    """
    Generates an HTML page for a specific pool/market showing all weekly plots.
    
    Args:
        pool_info: dict with pool metadata (name, address, chain_name, etc.)
        plot_files: list of paths to plot images, sorted by week (latest first)
        output_dir: directory to save the HTML file
    """
    name = pool_info.get("name", "Unknown Pool")
    address = pool_info.get("address", "")
    chain = pool_info.get("chain_name", "")
    explorer = pool_info.get("explorer", "")
    curve_url = pool_info.get("curve", "")
    
    # Sort plot_files to have the latest first
    plot_files = sorted(plot_files, reverse=True)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Refuel Analysis - {name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 20px; background: #f5f5f5; }}
        .header {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; max-width: 1200px; }}
        .header h1 {{ margin-top: 0; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; font-size: 0.95em; }}
        .info-item {{ margin-bottom: 5px; }}
        .info-label {{ font-weight: bold; color: #666; margin-right: 5px; }}
        .plot-container {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; width: fit-content; }}
        .plot-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
        .plot-title {{ font-weight: bold; font-size: 1.1em; }}
        .plot-image-wrapper {{ width: fit-content; }}
        img {{ display: block; height: auto; width: 1150px; max-width: 100%; border: 1px solid #ddd; transition: opacity 0.2s; }}
        img:hover {{ opacity: 0.9; }}
        .back-link {{ display: inline-block; margin-bottom: 20px; text-decoration: none; color: #3465A4; font-weight: bold; }}
        .back-link:hover {{ text-decoration: underline; }}
        a {{ color: #3465A4; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <a href="../../../index.html" class="back-link">← Back to Overview</a>
    
    <div class="header">
        <h1>{name}</h1>
        <div class="info-grid">
            <div class="info-item"><span class="info-label">Chain:</span> {chain.capitalize()}</div>
            <div class="info-item"><span class="info-label">Address:</span> <a href="{explorer}" target="_blank">{address}</a></div>
            {f'<div class="info-item"><span class="info-label">Curve:</span> <a href="{curve_url}" target="_blank">View on Curve</a></div>' if curve_url else ''}
        </div>
    </div>

    <div class="plots-list">
"""

    for plot_path in plot_files:
        plot_name = Path(plot_path).name
        # Show filename as label to see the date
        label = plot_name.replace('.png', '').replace('_', ' ')
        
        html_content += f"""
        <div class="plot-container">
            <div class="plot-header">
                <div class="plot-title">{label}</div>
            </div>
            <div class="plot-image-wrapper">
                <a href="{plot_name}" target="_blank">
                    <img src="{plot_name}" alt="Weekly Plot {label}" loading="lazy">
                </a>
            </div>
        </div>
"""

    html_content += """
    </div>
</body>
</html>
"""
    
    output_path = Path(output_dir) / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html_content)

def generate_overview_page(pools_data, output_file):
    """
    Generates an overview HTML page with all markets and their first plot thumbnails.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Refuel Analysis Overview</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1400px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        h1 { text-align: center; margin-bottom: 40px; }
        .market-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 25px; }
        .market-card { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.2s; text-decoration: none; color: inherit; display: flex; flex-direction: column; height: 100%; }
        .market-card:hover { transform: translateY(-5px); box-shadow: 0 8px 12px rgba(0,0,0,0.15); }
        .thumbnail-container { width: 100%; height: 200px; overflow: hidden; background: #eee; border-bottom: 1px solid #eee; }
        .thumbnail-container img { width: 100%; height: 100%; object-fit: cover; object-position: top; }
        .market-info { padding: 15px; flex-grow: 1; }
        .market-name { font-weight: bold; font-size: 1.2em; margin-bottom: 5px; color: #3465A4; }
        .market-meta { font-size: 0.85em; color: #666; }
        .filter-container { margin-bottom: 30px; display: flex; gap: 10px; justify-content: center; }
        input[type="text"] { padding: 10px 20px; border-radius: 25px; border: 1px solid #ccc; width: 100%; max-width: 400px; font-size: 1em; }
    </style>
</head>
<body>
    <h1>FxSwap Refuel Analysis</h1>
    
    <div class="filter-container">
        <input type="text" id="marketSearch" placeholder="Search markets (name or chain)..." onkeyup="filterMarkets()">
    </div>

    <div class="market-grid" id="marketGrid">
"""

    for pool in pools_data:
        info = pool['info']
        name = info.get("name", "Unknown Pool")
        chain = info.get("chain_name", "unknown")
        link = pool['link']
        thumbnail = pool['latest_plot']
        
        html_content += f"""
        <div class="market-item" data-name="{name.lower()}" data-chain="{chain.lower()}">
            <a href="{link}" class="market-card">
                <div class="thumbnail-container">
                    <img src="{thumbnail}" alt="{name}" loading="lazy">
                </div>
                <div class="market-info">
                    <div class="market-name">{name}</div>
                    <div class="market-meta">Chain: {chain.capitalize()}</div>
                </div>
            </a>
        </div>
"""

    html_content += """
    </div>

    <script>
        function filterMarkets() {
            const input = document.getElementById('marketSearch');
            const filter = input.value.toLowerCase();
            const grid = document.getElementById('marketGrid');
            const items = grid.getElementsByClassName('market-item');

            for (let i = 0; i < items.length; i++) {
                const name = items[i].getAttribute('data-name');
                const chain = items[i].getAttribute('data-chain');
                if (name.includes(filter) || chain.includes(filter)) {
                    items[i].style.display = "";
                } else {
                    items[i].style.display = "none";
                }
            }
        }
    </script>
</body>
</html>
"""
    
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        f.write(html_content)
