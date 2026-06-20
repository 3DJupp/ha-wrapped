# HA Wrapped

A Spotify-Wrapped-style year review for your Home Assistant. One Python
script pulls a full year of statistics from your instance, optionally lets
an LLM write deadpan one-liners about them, and renders a shareable,
self-contained HTML story — vibrant per-card accent colors, mechanical
odometer digits that roll in as you scroll, monthly bar charts, dark/light
theme, and a layout that works on phones and desktops alike.

[![GitHub Release](https://img.shields.io/github/release/3DJupp/ha-wrapped.svg?style=flat-square)](https://github.com/3DJupp/ha-wrapped/releases)
[![License](https://img.shields.io/github/license/3DJupp/ha-wrapped.svg?style=flat-square)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square&logo=HomeAssistantCommunityStore)](https://github.com/hacs/integration)

<img width="740" height="1260" alt="demo" src="https://github.com/user-attachments/assets/2d62b6bd-3a10-4efa-8ab7-4fc70fd2c561" />

**[Live demo](https://3djupp.github.io/ha-wrapped/)** — sample data, real scrolling odometers.

> *"Your shutters traveled 4.2 km this year. If this were an elevator,
> it would deserve a tip."*

---

## Installation

Three ways to run HA Wrapped — pick the one that fits your setup.

### Option A — Home Assistant Add-on

The easiest way if you run HA OS or Supervised. The add-on runs entirely
inside your Home Assistant instance, reads your stats directly, and saves
the HTML to `/share/ha-wrapped/`.

**Step 1 — Add this repository to your add-on store:**

[![Add Repository to HA](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F3DJupp%2Fha-wrapped)

Or manually: **Settings → Add-ons → Add-on Store → ⋮ → Repositories** →
paste `https://github.com/3DJupp/ha-wrapped`

**Step 2 — Install and configure:**

Find *HA Wrapped* in the store, click **Install**, then open the
**Configuration** tab. Add your entities under `statistics` and/or `counts`
(see [Configuration](#configuration) below).

**Step 3 — Run:**

Click **Start**. The add-on runs once, saves the HTML, and stops. Open the
output with the **File editor** or **Samba** add-on from
`/share/ha-wrapped/ha_wrapped_<year>.html`.

**Or add via HACS:**

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=3DJupp&repository=ha-wrapped&category=addon)

In HACS: **⋮ → Custom repositories** → paste the URL, category **Add-on**
→ then install from the HACS add-on list.

---

### Option B — Command line / uvx / Docker

Grab the config, fill in your entities, create a
[long-lived access token](https://my.home-assistant.io/redirect/profile/)
in your Home Assistant profile, export it as `HA_TOKEN` — then any **one**
of these runs the whole thing:

```bash
# 0) the config (edit it once, the rest is one-liners)
curl -fsSL https://raw.githubusercontent.com/3DJupp/ha-wrapped/main/config.example.yaml -o config.yaml
export HA_TOKEN="eyJ..."                # secrets stay env-only
export ANTHROPIC_API_KEY="sk-ant-..."   # optional, for the witty copy

# uv (Linux / macOS / Windows)
uvx --from git+https://github.com/3DJupp/ha-wrapped ha-wrapped

# pipx
pipx run --spec git+https://github.com/3DJupp/ha-wrapped ha-wrapped

# Docker (builds straight from the repo, writes into the current dir)
docker build -t ha-wrapped https://github.com/3DJupp/ha-wrapped.git
docker run --rm -e HA_TOKEN -e ANTHROPIC_API_KEY -v "$PWD:/data" ha-wrapped

# classic clone (venv)
git clone https://github.com/3DJupp/ha-wrapped.git && cd ha-wrapped
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml
.venv/bin/python wrapped.py
```

Output: `ha_wrapped_<year>.html` in the current directory.

---

## What it does

- Pulls **yearly totals** from Home Assistant's long-term statistics over
  the WebSocket API (water, energy, anything cumulative — also averages,
  peaks, and minimums).
- Counts **state changes** via the REST history API (laundry loads,
  coffees brewed, doorbell rings, shutter cycles, ...).
- Turns counts into fun numbers with a `scale` factor (shutter cycles ×
  window height = travel distance).
- Optionally sends the numbers to the **Claude API** to generate witty
  copy in your language and tone of choice. Without an API key it falls
  back to your plain labels — the page works either way.
- Renders everything into a **single HTML file**. No server, no
  dependencies at view time. Open it, scroll, screenshot, share.
- **Keyboard navigation**: arrow keys / space / Home / End scroll between cards.
- **Share button**: native Web Share on mobile, clipboard fallback on desktop.

Only aggregated numbers ever leave your network, and only if you opt into
the LLM copy. No entity history is uploaded anywhere.

### Self-debug

The script prints a preflight status before it fetches anything — config
found, token source, API reachable, AI copy on/off — and a per-entity
summary at the end. The same diagnostics are embedded into the page:
click the **ⓘ** button (bottom right) for the status panel. It shows when
the page was generated, the covered range, which entities delivered data
and which were skipped, and it opens automatically if something is wrong.

### Hosting & social export

The output is a single static HTML file, so any static host works: copy
it into Home Assistant's `www/` folder (served at `/local/...` with zero
extra setup), drop it on GitHub Pages / Netlify / Cloudflare Pages, or
`rsync`/`scp` it to a webserver you already run.

The page also includes a **recap card** — a compact grid of every stat,
made for sharing. Add `--export-summary` to also render it as a
ready-to-post PNG (1080×1080 by default). This needs
[Playwright](https://playwright.dev/), which is *not* part of the default
install:

```bash
pip install playwright && playwright install chromium
python3 wrapped.py --export-summary
# -> ha_wrapped_2025.html
# -> ha_wrapped_2025_summary.png   (1080×1080, ready for Instagram & co.)

python3 wrapped.py --export-summary --summary-size 1080x1920   # 9:16 story
```

---

## Configuration

Two kinds of stats, both optional, mix freely:

```yaml
statistics:                      # long-term statistics (needs state_class)
  - entity_id: sensor.water_meter_total
    label: "Water through the pipes"
    aggregate: sum               # sum | mean | max | min | delta
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

All top-level options (see [`config.example.yaml`](config.example.yaml)
for the fully commented reference):

| key | default | description |
|---|---|---|
| `ha_url` | — | base URL of your Home Assistant instance |
| `token` | — | HA access token; prefer the `HA_TOKEN` env var |
| `period` | `yearly` | `yearly` or `monthly` — see [Monthly Wrapped](#monthly-wrapped) |
| `year` | current year | the year to wrap (or the year of `month`, for `period: monthly`) |
| `month` | previous month | `period: monthly` only, `1`–`12` |
| `tz_offset` | `+01:00` | timezone offset for the period boundaries |
| `language` | `en` | language for UI strings and AI copy (`en`, `de`, `fr`, `es`, `nl`, `it`) |
| `number_format` | follows language | `en` → 1,234.5 · `de` → 1.234,5 |
| `house_name` | `My Home` | shown on the intro and outro card |
| `theme` | `auto` | `auto` (follow system) · `dark` · `light` |
| `tone` | `dry, witty, deadpan` | personality of the AI copy |

Per-entry options for both lists: `label`, `unit`, `scale`, `decimals`,
`footnote` — plus `aggregate` for `statistics:` and `to_state` for `counts:`.

### Aggregates

| aggregate | use for |
|-----------|---------|
| `sum` | Cumulative sensors (energy, water, gas) |
| `mean` | Period average (temperature, humidity) |
| `max` | Period peak (power spike, hottest day) |
| `min` | Period minimum (coldest night, lowest humidity) |
| `delta` | Absolute/lifetime counters (`state_class: total_increasing`, e.g. a coffee machine's total brew count) — period total = *last − first reading* |

In `counts:`, `entity_id` can also be a list — their counts and series
are summed into one stat (e.g. several shutters as one "shutter travel"
number).

---

## Monthly Wrapped

By default HA Wrapped covers a full calendar year. Set `period: monthly` to
get a per-month recap instead — same page, same stats, just a shorter
window with a daily (instead of monthly) breakdown in the charts.

```yaml
period: monthly
# year: 2025    # optional, defaults to the year of `month`
# month: 5      # optional, defaults to the month that just ended
```

Without `year`/`month`, a run on (or shortly after) the 1st of a month
wraps the month that just ended — perfect for a monthly cronjob:

```bash
# crontab: run at 00:05 on the 1st of every month
5 0 1 * * cd /path/to/ha-wrapped && .venv/bin/python wrapped.py
```

The output filename also changes to `ha_wrapped_<year>-<month>.html`
(e.g. `ha_wrapped_2025-05.html`), so monthly runs don't overwrite each
other or the yearly file.

---

## Tips

- Good `counts` candidates: anything with a power-plug-derived
  `binary_sensor` (washing machine, dishwasher, coffee machine, 3D
  printer), covers, doorbells, scene/`input_boolean` activations.
- `scale` is where the fun lives: cycles × meters, brews × cups,
  liters → bathtubs.
- A full year of history for a `counts` entity can take a moment on
  large recorder databases. Long-term `statistics` queries are fast.
- Multiple shutters/covers: list all their entity IDs under one `counts:`
  entry (see `config.example.yaml`), or add a template sensor that sums
  the travel and pull it with `aggregate: sum`.
- Use `--output-json result.json` to also write the full payload as JSON
  (handy for dashboards, automations, or debugging).

---

## Requirements

- Home Assistant with the recorder (default) and long-term statistics
- Python 3.10+ · `websockets` · `pyyaml` · `requests`
- Optional: an Anthropic API key for the generated copy
- Add-on: Home Assistant OS or Supervised (add-on store access required)

## License

MIT
