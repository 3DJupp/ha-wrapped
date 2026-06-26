# Changelog

## 1.0.6

- **Open wrapped now opens full-screen inside the add-on panel** (with a
  ← Back button) instead of a new browser tab. New tabs hit Home Assistant's
  Ingress 401 and showed an ugly `blob:` URL; this works everywhere, the HA
  app included.
- **Embed the result in a dashboard.** The wrapped is now also written to the
  HA config's `www/` folder, so it's reachable at
  `/local/ha-wrapped/ha_wrapped.html` and can be dropped into a dashboard with
  a **Webpage card**. Auto-generated runs also publish stable
  `/local/ha-wrapped/monthly.html` and `/local/ha-wrapped/yearly.html`.
- **Automatic generation.** New **Auto-generate** option (off / monthly /
  yearly / both). A built-in scheduler renders the most recently completed
  month at the start of each month, and the previous year on 1 January, using
  your saved config. Off by default.

## 1.0.5

- Fixed: **Open wrapped gave `401: Unauthorized`.** It opened the Ingress
  `view` URL in a new browser tab, but Home Assistant only accepts Ingress
  paths as requests from inside its own iframe -- a top-level new tab is
  rejected. Both Open and Download now fetch the file the way the rest of the
  UI talks to the add-on (carrying the Ingress session) and hand the browser
  a local blob, so opening in a new tab works.
- Fixed: **Open / Download didn't reappear after reopening the add-on.** They
  only showed right after generating; the page now detects an existing result
  on load and shows them straight away.
- The view/download responses send `Cache-Control: no-store` so re-opening
  after a regenerate never serves a stale cached copy.

## 1.0.4

- Entity picker now works in the HA companion app on Android and iOS. The
  native browser datalist (unreliable inside the app's WebView) is replaced
  by a custom searchable dropdown: tap the field to see all entities, type to
  filter by ID or friendly name, tap an entry to select it. Keyboard
  navigation (arrows, Enter, Escape) works on desktop too.
- Fixed a crash when a statistics or counts entry was saved without a label
  (the engine now falls back to the entity ID instead of raising KeyError).

## 1.0.3

- Fixed a crash when saving the config (`module 'wrapped' has no attribute
  '_opt_int'`). The year/month normaliser is now defined inside the add-on
  itself instead of reaching into the engine, so saving no longer depends on
  the exact engine version the image was built against.

## 1.0.2

- Fixed another Generate crash (`Invalid isoformat string:
  'None-01-01...'`) that could happen if a stray "None"/"auto" year or month
  ever got saved. Year and month are now coerced to a real number (or
  dropped) both when saved and when read.
- New number format `1234,5` (no thousands separator, comma decimal).
- The Theme dropdown now re-themes the config UI itself the moment you pick
  dark/light/auto, so you see what you'll get.
- Mobile layout: fields get two columns with more breathing room instead of
  being crammed, and the remove button drops to its own line. Long labels
  (e.g. French) no longer push their input out of line.
- Set `log_level` to `debug` or `trace` (Configuration tab) to dump the raw
  statistic rows into the log when you Generate, for chasing down empty or
  odd stats.

## 1.0.1

- Fixed a crash on Generate (`unsupported format string passed to
  NoneType.__format__`) when year/month were left on auto.
- New add-on icon and sidebar icon (a blue bar-chart mark, matching Home
  Assistant) instead of the violet gift.
- Config UI restyled to match Home Assistant (HA blue accent, light/dark
  surfaces) and made wider so the entity rows are easier to fill in.
  Dropdowns now follow the theme instead of staying white.
- The config UI is fully translated and switches language the moment you
  pick one. Languages: English, Deutsch, Français, Español, Italiano,
  Nederlands, Português.
- Number format is now named by how the number looks (1,234.5 / 1.234,5 /
  1 234,5 / 1234.5) instead of by country.
- Toned down the AI copy so it reads less like an AI and drops em dashes.

## 1.0.0

- First release of the HA Wrapped add-on.
- Ingress web UI: configure entities (with live pickers) and all options,
  generate on demand, and view/download the result inside Home Assistant.
- Reaches Core via the Supervisor proxy — no long-lived access token needed.
- Output mirrored to `/share/ha-wrapped/` for Samba/SSH access.
