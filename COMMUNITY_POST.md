# Community post draft

For the Home Assistant Community forum, "Share your Projects" category
(or similar: Reddit r/homeassistant, etc.). Markdown renders fine on
Discourse.

---

## Title

HA Wrapped – a Spotify Wrapped-style year-in-review for your smart home

## Body

Ever wondered how many liters flowed through your water meter this year,
how many loads of laundry you ran, or how far your shutters traveled (in
elevator-trip equivalents)? **HA Wrapped** turns a year of your Home
Assistant statistics into a shareable, Spotify-Wrapped-style story:
scrolling cards, mechanical odometer digits that roll in as you scroll,
monthly bar charts, and a copper-toned look in dark *and* light (follows
your system, toggleable on the page).

> *"Your shutters traveled 4.2 km this year. If this were an elevator, it
> would deserve a tip."*

**[Live demo](https://3djupp.github.io/ha-wrapped/)** — sample data, real
scrolling odometers, no setup needed.

### How it works

It's a single Python script, no add-on or integration required:

- Pulls **yearly totals** from HA's long-term statistics (water, energy,
  anything cumulative — sums, averages, peaks).
- Counts **state changes** via the history API (laundry loads, coffees
  brewed, doorbell rings, shutter cycles, ...).
- Turns counts into fun numbers with a `scale` factor — shutter cycles ×
  window height = travel distance, brews × cup size = liters of coffee.
- Renders everything into **one self-contained HTML file**. Open it,
  scroll, screenshot, share. No server, no dependencies at view time.

Optional: add an Anthropic API key and Claude writes a dry, witty
one-liner for each stat, in your language and tone of choice. Only the
aggregated numbers are ever sent — never raw history — and the page works
just as well without it.

### Running it

One line via `uvx`, `pipx`, Docker, or a classic clone + venv — point it
at your instance with a long-lived access token and a short YAML config:

```bash
curl -fsSL https://raw.githubusercontent.com/3DJupp/ha-wrapped/main/config.example.yaml -o config.yaml
export HA_TOKEN="eyJ..."
uvx --from git+https://github.com/3DJupp/ha-wrapped ha-wrapped
```

🔗 Source & full setup: https://github.com/3DJupp/ha-wrapped

Would love feedback — especially which stats you find most fun to wrap
up, and any "fun unit" ideas for the `scale` factor (cycles → km, brews →
cups, liters → bathtubs, ...).
