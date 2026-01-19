import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

def load_env():
    """Load consolidated .env file into os.environ."""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value

def get_env_for_chain(chain_name, var_name, default=None):
    """
    Get environment variable for a specific chain.
    Tries {CHAIN}_{VAR} first, then {VAR}.
    """
    load_env()
    chain_upper = chain_name.upper()
    
    # Try prefixed first
    val = os.getenv(f"{chain_upper}_{var_name}")
    if val is not None:
        return val
        
    # Try original
    return os.getenv(var_name, default)

def setup_env_for_chain(chain_name):
    """
    Populate generic environment variables from chain-prefixed ones.
    Example: BASE_RPC -> RPC
    """
    load_env()
    chain_upper = chain_name.upper()
    vars_to_map = [
        "RPC", "RPC_URL", "XSCAN_API_KEY", "XSCAN_CHAIN_ID", 
        "XSCAN_URL", "XSCAN_API_URI_ONLY", "TWOCRYPTO_FACTORY",
        "IMPLEMENTATION_ID"
    ]
    for var in vars_to_map:
        val = os.getenv(f"{chain_upper}_{var}")
        if val:
            os.environ[var] = val
