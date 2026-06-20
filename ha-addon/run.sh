#!/usr/bin/env bash
# HA Wrapped add-on entrypoint.
# Reads /data/options.json (written by the Supervisor from the add-on UI),
# converts it to a wrapped.py config, and runs the generator.
set -e

OPTIONS=/data/options.json
TMP_CONFIG=/tmp/ha_wrapped_config.yaml
OUTPUT_DIR=/share/ha-wrapped

mkdir -p "$OUTPUT_DIR"

# Convert Supervisor options.json -> wrapped.py YAML config.
# The Supervisor API is always at http://supervisor/core/api inside an add-on;
# SUPERVISOR_TOKEN is injected automatically — no manual token needed.
python3 - <<'PYEOF'
import json, os, sys

try:
    import yaml
except ImportError:
    sys.exit("pyyaml not installed inside the add-on image")

opts = json.load(open("/data/options.json"))

# Supervisor core API endpoint
opts["ha_url"] = "http://supervisor/core/api"

# Move the Anthropic key to env so it never lands in a plain-text file
api_key = opts.pop("anthropic_api_key", None)
if api_key:
    # Write to a file that run.sh will source; avoids shell-escaping issues
    with open("/tmp/ha_wrapped_env", "w") as f:
        f.write(f"export ANTHROPIC_API_KEY={api_key!r}\n")

with open("/tmp/ha_wrapped_config.yaml", "w") as f:
    yaml.dump(opts, f, allow_unicode=True, default_flow_style=False)
PYEOF

# Source the Anthropic key if the user set one
if [ -f /tmp/ha_wrapped_env ]; then
    # shellcheck disable=SC1091
    source /tmp/ha_wrapped_env
    rm -f /tmp/ha_wrapped_env
fi

# SUPERVISOR_TOKEN gives access to the HA core API; wrapped.py picks it up
export HA_TOKEN="${SUPERVISOR_TOKEN}"

cd "$OUTPUT_DIR"
exec python3 /app/wrapped.py --config "$TMP_CONFIG"
