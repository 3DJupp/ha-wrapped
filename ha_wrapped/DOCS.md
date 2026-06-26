# HA Wrapped — Home Assistant add-on

A Spotify-Wrapped-style year (or month) review for your Home Assistant —
configured and served entirely inside HA. No long-lived token, no separate
VM, no copying HTML files around.

## Why the add-on

- **No token.** The add-on talks to Core through the Supervisor proxy using
  its own credentials. You never create a long-lived access token.
- **Config in the UI.** Entities *and* every other option (period, language,
  theme, tone, API key…) are set in the add-on's own web UI, which appears
  in the Home Assistant sidebar. The entity fields have pickers fed live
  from your instance (the statistics picker only lists entities that
  actually have long-term statistics).
- **Speaks your language.** The UI itself is available in English, German,
  French, Spanish, Italian, Dutch and Portuguese, and switches the moment
  you change the language dropdown. That dropdown also sets the language of
  the generated wrapped.
- **HA serves the page.** The rendered wrapped opens right in the sidebar
  (Ingress). It is also written to `/share/ha-wrapped/ha_wrapped.html` so you
  can grab it over Samba/SSH.

## Install

This is a Home Assistant **add-on** (installed via the Add-on Store /
Supervisor), *not* a HACS integration — HACS does not manage add-ons.

One click to add the repository:

[![Add repository to your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F3DJupp%2Fha-wrapped)

Or manually: Settings → Add-ons → Add-on store → ⋮ → **Repositories**, add
`https://github.com/3DJupp/ha-wrapped`. Then install **HA Wrapped**, start it,
and open the UI (sidebar **Wrapped**, or the add-on's **Open Web UI**).

## Use

1. Fill in **General** (house name, period, language, theme, tone). To enable
   the witty AI copy, paste an **Anthropic API key** — leave it blank for
   plain labels.
2. Add **Statistics** rows (energy, water, temperatures — anything with
   long-term statistics). Pick `sum` for cumulative meters, `mean`/`max` for
   sensors, `delta` for lifetime counters that never reset.
3. Add **Counts** rows (state-change counts via the history API — laundry
   loads, doorbell rings…). Comma-separate several entities to sum them into
   one stat. `to_state` is the state whose arrivals are counted (`on`,
   `closing`, …).
4. **Save & Generate.** When it finishes, **Open wrapped** shows the page
   full-screen right inside the add-on panel (use **← Back** to return);
   **Download HTML** saves the self-contained file.

Only aggregated numbers ever leave your network, and only if you set an
Anthropic API key. No entity history is uploaded anywhere.

## Embed it in a dashboard

Every generated wrapped is also written to your HA config's `www/` folder, so
it is served by Home Assistant at:

- `/local/ha-wrapped/ha_wrapped.html` — the latest generation (manual or auto)
- `/local/ha-wrapped/monthly.html` — the latest auto-generated month
- `/local/ha-wrapped/yearly.html` — the latest auto-generated year

To show it on a dashboard, add a **Webpage card** pointing at one of those
URLs, for example:

```yaml
type: iframe
url: /local/ha-wrapped/ha_wrapped.html
aspect_ratio: 150%
```

(The file is also mirrored to `/share/ha-wrapped/` for Samba/SSH.)

## Automatic generation

Set **Auto-generate** (General section) to have the add-on render the page on
its own — no need to open it each time:

- **monthly** — at the start of each month, renders the month that just ended.
- **yearly** — on 1 January, renders the year that just ended.
- **monthly + yearly** — both.
- **off** (default) — only generate when you press Generate.

The scheduler uses your saved config (entities, language, tone, API key…) and
the **Timezone offset** to decide when a month/year has ended. Combined with a
Webpage card pointing at `/local/ha-wrapped/monthly.html` or `yearly.html`,
your dashboard updates itself.

## Configuration tab

The native add-on **Configuration** tab only holds `log_level`. Everything
else lives in the add-on's own UI and is stored in `/data/config.yaml`
(persistent across restarts and updates).

## Notes

- The add-on image installs the engine (`wrapped.py` + `template.html`) from
  the git ref pinned by `HA_WRAPPED_REF` in `build.yaml` (default `main`).
- The on-page status panel (ⓘ button) reports which entities delivered data,
  which were skipped, and whether the AI copy was used.
- The PNG social-export (Playwright) is a CLI-only extra for now; the Ingress
  page itself is already shareable.
