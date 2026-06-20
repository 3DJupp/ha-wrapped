# HA Wrapped — Add-on Documentation

A Spotify-Wrapped-style yearly or monthly review of your Home Assistant data.
Generates a self-contained, shareable HTML page from your long-term statistics
and state-change history, saved to `/share/ha-wrapped/`.

## Setup

1. Install the add-on from the repository.
2. Open the **Configuration** tab and set your entities under `statistics`
   and/or `counts` (see examples below).
3. Click **Start**. The add-on runs once and stops — it is not a daemon.
4. Open `/share/ha-wrapped/ha_wrapped_<year>.html` via the
   **Samba** or **File editor** add-on, or serve it from the
   `/share` folder using a web server add-on.

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `house_name` | `My Home` | Shown on the intro and outro card |
| `language` | `en` | Language for UI strings and AI copy: `en`, `de`, `fr`, `es`, `nl`, `it` |
| `number_format` | `en` | `en` → 1,234.5 · `de` → 1.234,5 |
| `theme` | `auto` | `auto` (follow system), `dark`, or `light` |
| `tone` | `dry, witty, deadpan` | AI copy personality (only with `anthropic_api_key`) |
| `period` | `yearly` | `yearly` or `monthly` |
| `year` | current year | Which year to cover |
| `month` | previous month | Monthly mode only: 1–12 |
| `tz_offset` | `+01:00` | Timezone offset for period boundaries |
| `anthropic_api_key` | *(unset)* | Anthropic API key for AI-generated copy (optional) |

## statistics entries

Long-term statistics (entities need `state_class` set in HA):

```yaml
statistics:
  - entity_id: sensor.energy_total
    label: Electricity used
    aggregate: sum    # sum | mean | max | min | delta
    unit: kWh
    decimals: 0

  - entity_id: sensor.living_room_temperature
    label: Average temperature
    aggregate: mean
    unit: "°C"
    decimals: 1
```

| Aggregate | Use for |
|-----------|---------|
| `sum` | Cumulative sensors (energy, water, gas) |
| `mean` | Averages (temperature, humidity) |
| `max` | Peak values (power spikes) |
| `min` | Lowest values (coldest night) |
| `delta` | Absolute/lifetime counters (`state_class: total_increasing`) |

## counts entries

State-change counts via the history API. Counts transitions *into* `to_state`:

```yaml
counts:
  - entity_id: binary_sensor.washing_machine_running
    to_state: "on"
    label: Laundry loads
    unit: loads

  # Sum multiple entities into one stat
  - entity_id:
      - cover.living_room_shutter
      - cover.bedroom_shutter
    to_state: closing
    label: Shutter travel
    unit: meters
    scale: 2.4   # meters per cycle
```

## Output

The rendered HTML file is saved to:

- Yearly: `/share/ha-wrapped/ha_wrapped_<year>.html`
- Monthly: `/share/ha-wrapped/ha_wrapped_<year>-<month>.html`

The file is self-contained — no server required. Open it in any browser,
share it directly, or host it from `/share` using a static file server add-on.

## Setting up a separate add-on repository

The `ha-addon/` directory in the main repository contains everything needed
to publish this as a standalone HA add-on repository:

```
your-addon-repo/
├── config.yaml       ← from ha-addon/config.yaml
├── Dockerfile        ← from ha-addon/Dockerfile (adapt paths for repo root)
├── run.sh            ← from ha-addon/run.sh
├── wrapped.py        ← from repo root
├── template.html     ← from repo root
├── requirements.txt  ← from repo root
└── DOCS.md           ← this file
```

Update the `Dockerfile` `COPY` paths to match the flat repo structure (remove
the `ha-addon/` prefix from `run.sh`).
