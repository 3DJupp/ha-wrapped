# HA Wrapped — Add-on Documentation

A Spotify-Wrapped-style yearly or monthly review of your Home Assistant data.
Generates a self-contained, shareable HTML page from your long-term statistics
and state-change history, saved to `/share/ha-wrapped/`.

## Setup

1. Open the **Configuration** tab and add your entities under `statistics`
   and/or `counts` (examples below). No HA token needed — the add-on has
   direct access to your Home Assistant instance automatically.
2. Click **Start**. The add-on runs once and stops — it is not a daemon.
3. Open the result with the **File editor** or **Samba** add-on:
   `/share/ha-wrapped/ha_wrapped_<year>.html`

You can also put the HTML file in `www/` to serve it at
`http://homeassistant.local:8123/local/ha_wrapped_<year>.html` without
any extra add-on.

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
| `anthropic_api_key` | *(unset)* | Anthropic API key for AI-generated copy — stored encrypted |

## statistics entries

Long-term statistics (entity needs `state_class` set in HA):

```yaml
statistics:
  - entity_id: sensor.energy_total
    label: Electricity used
    aggregate: sum      # sum | mean | max | min | delta
    unit: kWh
    decimals: 0

  - entity_id: sensor.living_room_temperature
    label: Average temperature
    aggregate: mean
    unit: "°C"
    decimals: 1

  - entity_id: sensor.outdoor_temperature
    label: Coldest night
    aggregate: min
    unit: "°C"
    decimals: 1
```

| Aggregate | Use for |
|-----------|---------|
| `sum` | Cumulative sensors (energy, water, gas) |
| `mean` | Period average (temperature, humidity) |
| `max` | Period peak (hottest day, power spike) |
| `min` | Period minimum (coldest night, lowest humidity) |
| `delta` | Absolute/lifetime counters (`state_class: total_increasing`, e.g. coffee machine brew count) |

## counts entries

State-change counts via the history API — counts transitions *into* `to_state`:

```yaml
counts:
  - entity_id: binary_sensor.washing_machine_running
    to_state: "on"
    label: Laundry loads
    unit: loads

  - entity_id: binary_sensor.doorbell
    to_state: "on"
    label: Doorbell rings
    unit: times

  # Sum multiple entities into one stat
  - entity_id:
      - cover.living_room_shutter
      - cover.bedroom_shutter
    to_state: closing
    label: Shutter travel
    unit: meters
    scale: 2.4    # meters per cycle — tune to your window height
    decimals: 0
    footnote: "If this were an elevator, it would deserve a tip."
```

## Output

The rendered HTML is saved to:

- Yearly: `/share/ha-wrapped/ha_wrapped_<year>.html`
- Monthly: `/share/ha-wrapped/ha_wrapped_<year>-<month>.html`

The file is fully self-contained — no internet connection, no server, no
dependencies required to view it. Open it in any browser, share the file,
or host it with a static file server add-on.
