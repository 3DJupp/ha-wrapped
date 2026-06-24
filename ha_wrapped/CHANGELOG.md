# Changelog

## 1.1.0

- Config UI restyled to match Home Assistant (HA blue accent, light/dark
  surfaces). Dropdowns now follow the theme instead of staying white.
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
