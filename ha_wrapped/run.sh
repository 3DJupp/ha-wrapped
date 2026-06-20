#!/usr/bin/env bash
# HA Wrapped add-on entrypoint.
# Reads /data/options.json (written by the Supervisor from the add-on UI),
# converts it to a wrapped.py config, and runs the generator via the
# installed 'ha-wrapped' CLI command.
set -e

TMP_CONFIG=/tmp/ha_wrapped_config.yaml
OUTPUT_DIR=/share/ha-wrapped

mkdir -p "$OUTPUT_DIR"

# Convert Supervisor options.json -> wrapped.py YAML config.
# ha_url is always http://supervisor/core/api inside an add-on;
# SUPERVISOR_TOKEN is injected automatically by the Supervisor.
python3 - <<'PYEOF'
import json, os, sys
try:
    import yaml
except ImportError:
    sys.exit("pyyaml not found — the add-on image may be broken")

opts = json.load(open("/data/options.json"))
opts["ha_url"] = "http://supervisor/core/api"

# Move Anthropic key to env so it never lands in a plain-text file
api_key = opts.pop("anthropic_api_key", None)
if api_key:
    with open("/tmp/ha_wrapped_env", "w") as f:
        f.write(f"export ANTHROPIC_API_KEY={api_key!r}\n")

with open("/tmp/ha_wrapped_config.yaml", "w") as f:
    yaml.dump(opts, f, allow_unicode=True, default_flow_style=False)
PYEOF

if [ -f /tmp/ha_wrapped_env ]; then
    # shellcheck disable=SC1091
    source /tmp/ha_wrapped_env
    rm -f /tmp/ha_wrapped_env
fi

# SUPERVISOR_TOKEN grants access to the HA core API
export HA_TOKEN="${SUPERVISOR_TOKEN}"

cd "$OUTPUT_DIR"
exec ha-wrapped --config "$TMP_CONFIG"
