# CLAUDE.md

## Project

HA Wrapped: a Spotify-Wrapped-style year review for Home Assistant.
`wrapped.py` pulls a year of stats from an HA instance, optionally generates
witty copy via the Anthropic API, and renders a self-contained HTML story
from `template.html`. It ships two ways: a CLI/Docker one-liner, and a
dedicated Home Assistant **add-on** (`ha_wrapped/`) with an Ingress UI.

## File map

- `wrapped.py` — collector + renderer engine. `collect_and_render(cfg, ...)`
  is the shared core behind both entry points (CLI `main()` and the add-on
  `server.py`); `resolve_connection(cfg)` returns `(ha_url, token, ws_url)`
  — the Supervisor proxy when `SUPERVISOR_TOKEN` is set (add-on), else
  `ha_url`+`HA_TOKEN` (CLI). `fetch_statistics`/`list_statistic_ids` take a
  full `ws_url`.
- `ha_wrapped/` — the Home Assistant add-on. `config.yaml` is the add-on
  manifest (`ingress: true`, `homeassistant_api: true`, minimal options
  schema), `server.py` is the aiohttp Ingress server (config UI with live
  entity pickers, `/api/generate` runs the engine in a worker thread since
  it spins up its own asyncio loop, `/view`+`/download` serve the result),
  `Dockerfile`/`build.yaml`/`run.sh` build it (engine installed from git via
  the `HA_WRAPPED_REF` build arg), `DOCS.md`/`CHANGELOG.md` are add-on docs.
  `repository.yaml` (repo root) marks the repo as an add-on repository.
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

- `compute_period(cfg, tz)` resolves the time window: `period: yearly`
  (default, `year:`) or `period: monthly` (`year:`/`month:`, defaults to
  the month that just ended). Returns start/end/full_end, the mode, and
  `n_periods` (12 for yearly, days-in-month for monthly) — this drives
  both data paths below plus the partial-period trimming and the output
  filename (`ha_wrapped_<year>.html` vs `ha_wrapped_<year>-<month>.html`).
- Two data paths, both optional per config:
  - `statistics:` entries -> `recorder/statistics_during_period` over the
    HA WebSocket API, `"month"` period for yearly / `"day"` period for
    monthly. `reduce_stat()` collapses rows; `sum` aggregates use
    cumulative-sum deltas, `delta` uses `last_state - first_state` for
    absolute/lifetime counters (e.g. a coffee machine's total brew count
    — don't use `sum` for those, it adds the raw readings together).
  - `counts:` entries -> REST `/api/history/period` with
    `minimal_response&no_attributes`; counts transitions INTO `to_state`.
    `entity_id` may be a list — counts and the per-period series are
    summed across all of them (e.g. several shutters as one stat).
    `fetch_count()` buckets by day-of-month (monthly) or month (yearly).
- Payload contract for the template: see `payload = {...}` in `main()`.
  Each stat: `id, label, unit, value, display_value, series[n_periods],
  headline, quip, footnote`. UI strings live in `payload.i18n`;
  `payload.theme` (`auto|dark|light`) sets the default theme;
  `payload.period_label` is the human-readable range (`"2025"`,
  `"Jan – Jun 2025"`, `"May 2025"`, `"1.–13. May 2025"`);
  `payload.period` is `{mode: "yearly"|"monthly", labels: [...]}` with one
  chart-axis label per series entry (month names or day numbers), used by
  `chart()` in `template.html`; `payload.meta` (generated_at, range,
  ai_copy, entities[]) feeds the on-page status panel. The template must
  degrade gracefully when `theme`/`meta`/`period` are missing.
- Claude copy: `claude_copy()` sends aggregated numbers only (never raw
  history) and expects strict JSON back; any failure falls back to plain
  labels. Model: `claude-sonnet-4-6`. `language`, `tone` and
  `period_label` come from config/`compute_period()`.
- Auth via env: `HA_TOKEN` (required), `ANTHROPIC_API_KEY` (optional).
- Recap card: the last `.summary` section in `template.html` renders a
  compact grid of every stat (`display_value` + `unit` + `headline`),
  built for screenshots/social sharing. `--export-summary` (in `main()`)
  uses `export_summary_png()` to screenshot just that card via Playwright;
  `--summary-size WIDTHxHEIGHT` controls the output (default `1080x1080`,
  use `1080x1920` for a 9:16 story). Uses the same payload as the rest of
  the page — no new fields.

## Conventions

- Repo language is English; generated output language is a config option.
- No personal data in the repo: no real entity IDs, hostnames, names, or
  real consumption numbers. Demo data is invented.
- Number formatting is manual (`fmt()`), not locale-dependent, so output
  is reproducible on any system.
- Keep `wrapped.py` stdlib + `websockets`/`pyyaml`/`requests` only.
  Playwright is an optional extra (`pyproject.toml` `[export]`), lazily
  imported only inside `export_summary_png()` for `--export-summary`.

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
- `min`/`count_distinct_days` aggregates; "busiest day" stat.
