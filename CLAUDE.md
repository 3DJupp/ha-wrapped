# CLAUDE.md

## Project

HA Wrapped: a Spotify-Wrapped-style year review for Home Assistant.
A single Python script (`wrapped.py`) pulls a year of stats from an HA
instance, optionally generates witty copy via the Anthropic API, and
renders a self-contained HTML story from `template.html`.

## File map

- `wrapped.py` — collector + renderer. No other Python files.
- `template.html` — HTML/CSS/JS template. The quoted token
  `"__WRAPPED_DATA__"` is replaced with a JSON payload at render time
  (quoted so the raw template stays valid JS and can self-diagnose).
  Keep it dependency-free and self-contained (Google Fonts is the only
  external resource).
- `pyproject.toml` — packaging for `uvx`/`pipx` one-liner runs; installs
  `template.html` to `<prefix>/share/ha-wrapped/` (see `find_template()`).
- `Dockerfile` — one-liner container run; `/data` is the work dir for
  `config.yaml` and the output file.
- `config.example.yaml` — documented example config. Real configs are
  `config.yaml` (gitignored).
- `docs/index.html` — pre-rendered demo with sample data, served via
  GitHub Pages (Settings: branch `main`, folder `/docs`).
- `docs/screenshot.png` — README hero, 480x860 @2x of the first stat card.

## Architecture notes

- Two data paths, both optional per config:
  - `statistics:` entries -> `recorder/statistics_during_period` over the
    HA WebSocket API, monthly period. `reduce_stat()` collapses rows;
    `sum` aggregates use cumulative-sum deltas.
  - `counts:` entries -> REST `/api/history/period` with
    `minimal_response&no_attributes`; counts transitions INTO `to_state`.
- Payload contract for the template: see `payload = {...}` in `main()`.
  Each stat: `id, label, unit, value, display_value, series[12],
  headline, quip, footnote`. UI strings live in `payload.i18n`;
  `payload.theme` (`auto|dark|light`) sets the default theme;
  `payload.meta` (generated_at, range, ai_copy, entities[]) feeds the
  on-page status panel. The template must degrade gracefully when
  `theme`/`meta` are missing.
- Claude copy: `claude_copy()` sends aggregated numbers only (never raw
  history) and expects strict JSON back; any failure falls back to plain
  labels. Model: `claude-sonnet-4-6`. `language` and `tone` come from
  config.
- Auth via env: `HA_TOKEN` (required), `ANTHROPIC_API_KEY` (optional).

## Conventions

- Repo language is English; generated output language is a config option.
- No personal data in the repo: no real entity IDs, hostnames, names, or
  real consumption numbers. Demo data is invented.
- Number formatting is manual (`fmt()`), not locale-dependent, so output
  is reproducible on any system.
- Keep `wrapped.py` stdlib + `websockets`/`pyyaml`/`requests` only.

## Verifying changes

- `python3 -m py_compile wrapped.py`
- Re-render the demo after template changes: replace the quoted token
  `"__WRAPPED_DATA__"` in `template.html` with the sample payload from
  `docs/index.html` (search for `let DATA =`) and write to
  `docs/index.html`.
- Regenerate `docs/screenshot.png` with Playwright after visual changes:
  480x860 viewport, deviceScaleFactor 2, scroll to `.card` index 1, wait
  ~2.5s for the odometer animation.

## Open ideas (not commitments)

- Chunked monthly history queries for `counts` on large recorder DBs.
- Optional PNG export of each card (Playwright) for direct sharing.
- `min`/`count_distinct_days` aggregates; "busiest day" stat.
