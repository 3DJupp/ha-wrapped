# HA Wrapped

A Spotify-Wrapped-style year review for your Home Assistant. One Python
script pulls a full year of statistics from your instance, optionally lets
an LLM write deadpan one-liners about them, and renders a shareable,
self-contained HTML story — dark copper look, mechanical odometer digits
that roll in as you scroll, and a monthly sparkline per stat.

![HA Wrapped demo](docs/screenshot.png)

**[Live demo](https://3djupp.github.io/ha-wrapped/)** — sample data, real scrolling odometers.

> *"Your shutters traveled 4.2 km this year. If this were an elevator,
> it would deserve a tip."*

## What it does

- Pulls **yearly totals** from Home Assistant's long-term statistics over
  the WebSocket API (water, energy, anything cumulative — also averages
  and peaks).
- Counts **state changes** via the REST history API (laundry loads,
  coffees brewed, doorbell rings, shutter cycles, ...).
- Turns counts into fun numbers with a `scale` factor (shutter cycles ×
  window height = travel distance).
- Optionally sends the numbers to the **Claude API** to generate witty
  copy in your language and tone of choice. Without an API key it falls
  back to your plain labels — the page works either way.
- Renders everything into a **single HTML file**. No server, no
  dependencies at view time. Open it, scroll, screenshot, share.

Only aggregated numbers ever leave your network, and only if you opt into
the LLM copy. No entity history is uploaded anywhere.

## Setup

```bash
git clone <this repo> && cd ha-wrapped
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml: your HA URL and entities
```

Create a [long-lived access token](https://my.home-assistant.io/redirect/profile/)
in your Home Assistant profile, then:

```bash
export HA_TOKEN="eyJ..."
export ANTHROPIC_API_KEY="sk-ant-..."   # optional, for the witty copy
python3 wrapped.py
```

Output: `ha_wrapped_<year>.html` in the current directory.
Open `docs/index.html` locally or check the [live demo](https://3djupp.github.io/ha-wrapped/) for a preview with sample data.

## Configuration

Two kinds of stats, both optional, mix freely:

```yaml
statistics:                      # long-term statistics (needs state_class)
  - entity_id: sensor.water_meter_total
    label: "Water through the pipes"
    aggregate: sum               # sum | mean | max
    unit: "liters"
    scale: 1000                  # m3 -> liters
    decimals: 0

counts:                          # state-change counts via history API
  - entity_id: binary_sensor.washing_machine_running
    to_state: "on"
    label: "Laundry loads"
    unit: "loads"
    footnote: "Optional fine print under the number."
```

| key | description |
|---|---|
| `year` | defaults to the current year |
| `language` | language for the generated copy (`en`, `de`, ...) |
| `number_format` | `en` → 1,234.5 · `de` → 1.234,5 |
| `tone` | personality of the AI copy, e.g. `"dry, witty, deadpan"` |
| `house_name` | shown on the intro and outro card |

## Tips

- Good `counts` candidates: anything with a power-plug-derived
  `binary_sensor` (washing machine, dishwasher, coffee machine, 3D
  printer), covers, doorbells, scene/`input_boolean` activations.
- `scale` is where the fun lives: cycles × meters, brews × cups,
  liters → bathtubs.
- A full year of history for a `counts` entity can take a moment on
  large recorder databases. Long-term `statistics` queries are fast.

## Requirements

- Home Assistant with the recorder (default) and long-term statistics
- Python 3.10+, `websockets`, `pyyaml`, `requests`
- Optional: an Anthropic API key for the generated copy

## License

MIT
