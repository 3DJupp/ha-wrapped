# Changelog

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
