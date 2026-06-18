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
- **HA serves the page.** The rendered wrapped opens right in the sidebar
  (Ingress). It is also written to `/share/ha-wrapped/ha_wrapped.html` so you
  can grab it over Samba/SSH.

## Install

1. Settings → Add-ons → Add-on store → ⋮ → **Repositories**, add:
   `https://github.com/3DJupp/ha-wrapped`
2. Install **HA Wrapped**, start it, then open the UI (sidebar **Wrapped**,
   or the add-on's **Open Web UI**).

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
4. **Save & Generate.** When it finishes, **Open wrapped ↗** shows the page;
   **Download HTML** saves the self-contained file.

Only aggregated numbers ever leave your network, and only if you set an
Anthropic API key. No entity history is uploaded anywhere.

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
