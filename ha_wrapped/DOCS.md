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

- `/local/ha-wrapped/latest.html` — **use this in dashboards** (always shows
  the newest run, cache-proof — see the note below)
- `/local/ha-wrapped/ha_wrapped.html` — the latest generation (manual or auto)
- `/local/ha-wrapped/monthly.html` — the latest auto-generated month
- `/local/ha-wrapped/yearly.html` — the latest auto-generated year

To show it on a dashboard, add a **Webpage card** pointing at `latest.html`:

```yaml
type: iframe
url: /local/ha-wrapped/latest.html
aspect_ratio: 150%
```

> **Why `latest.html`?** Home Assistant serves files under `/local` with a
> long browser cache. An iframe pointed straight at `ha_wrapped.html` keeps
> showing the previously cached run after you re-generate (you'd have to hard
> refresh). `latest.html` is a tiny wrapper that reloads the real file with a
> fresh timestamp on every page load, so your dashboard always shows the most
> recent wrapped without any manual refresh.

(The files are also mirrored to `/share/ha-wrapped/` for Samba/SSH.)

## Automatic generation

Set **Auto-generate** (General section) and hit **Save** to have the add-on
render the page on its own, no need to open it each time:

- **monthly**: shortly after midnight on the 1st (30 minutes grace, so the
  last hour of the month is in the statistics), renders the month that just
  ended.
- **yearly**: on 1 January, renders the year that just ended.
- **monthly + yearly**: both.
- **off** (default): only generate when you press Generate.

When you switch it on, the most recently completed month (or year) is
rendered right away; after that it runs once per period. The scheduler uses
your saved config (entities, language, tone, API key…) and the **Timezone
offset** to decide when a month/year has ended. The **Period**, **Year** and
**Month** fields only apply to the Generate button; automatic runs pick the
period themselves.

Below the buttons the config page shows when the next automatic run is due
and how the last one went. If a run fails (for example because Home
Assistant was restarting), the error is shown there and the run is retried
every hour (every 6 hours after six failures). The add-on log (tab **Log**)
has the details, prefixed `[auto]`.

Combined with a Webpage card pointing at `/local/ha-wrapped/monthly.html` or
`yearly.html`, your dashboard updates itself. The add-on has to be running
for any of this, so leave **Start on boot** on.

### Your own schedule (automations)

For anything the built-in schedule doesn't cover (weekly, a daily refresh of
the current month, right after a holiday…), trigger a run from a Home
Assistant automation with the `hassio.addon_stdin` action. The add-on's slug
is shown on the config page (it's also in the add-on's URL, for example
`a1b2c3d4_ha_wrapped`).

```yaml
automation:
  - alias: "HA Wrapped: refresh the current month every night"
    triggers:
      - trigger: time
        at: "03:00:00"
    actions:
      - action: hassio.addon_stdin
        data:
          addon: a1b2c3d4_ha_wrapped   # your slug
          input: this_month
```

Supported `input` values:

| input | renders |
|---|---|
| `generate` | same as the Generate button (saved config) |
| `monthly` | the month that just ended |
| `yearly` | the year that just ended |
| `this_month` | the current month so far |
| `this_year` | the current year so far |
| `auto` | whatever the Auto-generate schedule still owes |
| `{"period": "monthly", "year": 2025, "month": 8}` | the saved config with these keys overridden |

`monthly`/`yearly`/`this_*` also publish `monthly.html` / `yearly.html` and a
period-named copy (`ha_wrapped_2025-08.html`), like the automatic runs.
Output of triggered runs lands in the add-on log prefixed `[stdin]`.

### Last-run sensor

Every generate (manual, automatic or triggered) updates
`sensor.ha_wrapped_last_run` with the timestamp of that run, plus `ok`,
`period`, `mode`, `auto_generate`, `next_run` and (on failure) `error`
attributes. Use it on a dashboard or as an automation trigger, for example to
get a notification when a fresh wrapped is ready. The add-on re-publishes it
after a Home Assistant restart.

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
