#!/usr/bin/env python3
"""HA Wrapped add-on -- Ingress web UI.

A thin aiohttp server that runs inside Home Assistant as an add-on. It:

  * serves a config UI with entity pickers (fed by the Core API through the
    Supervisor proxy) so entities *and* the other options are set in the UI,
  * stores that config in /data/config.yaml (persistent),
  * runs wrapped.collect_and_render on demand (in a worker thread, since the
    engine spins up its own asyncio loop for the WebSocket query), and
  * serves the rendered page straight into the HA sidebar -- and copies it to
    /share/ha-wrapped/ for Samba/SSH access.

No long-lived token: Core is reached via http(ws)://supervisor/core using the
add-on's own SUPERVISOR_TOKEN.
"""
import asyncio
import os
from pathlib import Path

import yaml
from aiohttp import ClientSession, ClientTimeout, web

import wrapped

DATA = Path("/data")
CONFIG_PATH = DATA / "config.yaml"
OUTPUT_DIR = DATA / "output"
OUTPUT_HTML = OUTPUT_DIR / "ha_wrapped.html"
SHARE_DIR = Path("/share/ha-wrapped")
PORT = int(os.environ.get("INGRESS_PORT", "8099"))

SUPERVISOR_CORE = "http://supervisor/core"
SUPERVISOR_WS = "ws://supervisor/core/websocket"

DEFAULT_CONFIG = {
    "period": "yearly",
    "year": None,
    "month": None,
    "language": "en",
    "number_format": "comma_dot",
    "house_name": "My Home",
    "theme": "auto",
    "tone": "dry, witty, deadpan",
    "tz_offset": "+01:00",
    "anthropic_api_key": "",
    "statistics": [],
    "counts": [],
}


def token() -> str:
    return os.environ.get("SUPERVISOR_TOKEN", "")


def load_config() -> dict:
    cfg = {}
    if CONFIG_PATH.exists():
        cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    return {**DEFAULT_CONFIG, **cfg}


def save_config(cfg: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    # don't persist empty year/month -- let compute_period() pick its defaults
    clean = {k: v for k, v in cfg.items() if v not in (None, "")}
    CONFIG_PATH.write_text(
        yaml.safe_dump(clean, sort_keys=False, allow_unicode=True))


# --------------------------------------------------------------- handlers


async def handle_index(request: web.Request) -> web.Response:
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def handle_get_config(request: web.Request) -> web.Response:
    return web.json_response(load_config())


async def handle_save_config(request: web.Request) -> web.Response:
    body = await request.json()
    cfg = {**DEFAULT_CONFIG, **body}
    save_config(cfg)
    return web.json_response({"ok": True})


async def handle_entities(request: web.Request) -> web.Response:
    """Entity list for the counts picker -- id, name, domain, unit, classes."""
    session: ClientSession = request.app["http"]
    try:
        async with session.get(
                f"{SUPERVISOR_CORE}/api/states",
                headers={"Authorization": f"Bearer {token()}"}) as r:
            r.raise_for_status()
            states = await r.json()
    except Exception as e:  # noqa: BLE001
        return web.json_response({"error": str(e)}, status=502)
    out = []
    for s in states:
        attrs = s.get("attributes", {})
        eid = s.get("entity_id", "")
        out.append({
            "entity_id": eid,
            "name": attrs.get("friendly_name", eid),
            "domain": eid.split(".", 1)[0] if "." in eid else "",
            "unit": attrs.get("unit_of_measurement", ""),
            "device_class": attrs.get("device_class", ""),
            "state_class": attrs.get("state_class", ""),
        })
    out.sort(key=lambda e: e["entity_id"])
    return web.json_response(out)


async def handle_statistics(request: web.Request) -> web.Response:
    """Entities that have long-term statistics -- for the statistics picker."""
    try:
        rows = await wrapped.list_statistic_ids(SUPERVISOR_WS, token())
    except Exception as e:  # noqa: BLE001
        return web.json_response({"error": str(e)}, status=502)
    out = [{
        "entity_id": r.get("statistic_id", ""),
        "name": r.get("name") or r.get("statistic_id", ""),
        "unit": r.get("unit_of_measurement") or r.get("display_unit_of_measurement", ""),
        "has_sum": bool(r.get("has_sum")),
        "has_mean": bool(r.get("has_mean")),
    } for r in rows]
    out.sort(key=lambda e: e["entity_id"])
    return web.json_response(out)


async def handle_generate(request: web.Request) -> web.Response:
    cfg = load_config()
    logs: list[str] = []

    def log(msg):
        logs.append(str(msg))
        print(msg, flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, lambda: wrapped.collect_and_render(
            cfg, ha_url=SUPERVISOR_CORE, token=token(), ws_url=SUPERVISOR_WS,
            output=str(OUTPUT_HTML), log=log))
    except (Exception, SystemExit) as e:  # noqa: BLE001
        # SystemExit too: find_template() exits if the template is missing,
        # and that surfaces here through the worker thread.
        return web.json_response(
            {"ok": False, "error": str(e) or repr(e), "log": logs}, status=400)

    # mirror to /share for Samba/SSH access (best-effort)
    try:
        SHARE_DIR.mkdir(parents=True, exist_ok=True)
        (SHARE_DIR / "ha_wrapped.html").write_text(OUTPUT_HTML.read_text())
    except Exception as e:  # noqa: BLE001
        log(f"  (could not copy to /share: {e})")

    return web.json_response({"ok": True, "result": result, "log": logs})


async def handle_view(request: web.Request) -> web.Response:
    if not OUTPUT_HTML.exists():
        return web.Response(
            text="No wrapped generated yet. Go back and hit Generate.",
            status=404)
    return web.Response(text=OUTPUT_HTML.read_text(), content_type="text/html")


async def handle_download(request: web.Request) -> web.Response:
    if not OUTPUT_HTML.exists():
        return web.Response(text="Nothing to download yet.", status=404)
    return web.Response(
        body=OUTPUT_HTML.read_bytes(), content_type="text/html",
        headers={"Content-Disposition":
                 'attachment; filename="ha_wrapped.html"'})


# ----------------------------------------------------------------- app


async def on_startup(app: web.Application):
    app["http"] = ClientSession(timeout=ClientTimeout(total=60))


async def on_cleanup(app: web.Application):
    await app["http"].close()


def make_app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get("/", handle_index),
        web.get("/api/config", handle_get_config),
        web.post("/api/config", handle_save_config),
        web.get("/api/entities", handle_entities),
        web.get("/api/statistics", handle_statistics),
        web.post("/api/generate", handle_generate),
        web.get("/view", handle_view),
        web.get("/download", handle_download),
    ])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


# The whole UI is one self-contained page (vanilla JS, relative URLs so it
# works under the Ingress path prefix). Kept dependency-free on purpose.
INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HA Wrapped</title>
<style>
  /* Home Assistant-flavoured palette: HA blue primary, HA's light/dark
     surfaces, so the add-on UI sits naturally inside the sidebar. */
  :root {
    color-scheme: light dark;
    --primary: #03a9f4;
    --bg: #f5f7fa;
    --card: #ffffff;
    --field: #ffffff;
    --text: #212121;
    --muted: #5b6470;
    --border: #d4d9e0;
    --row: #eef1f5;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #111417;
      --card: #1c1f24;
      --field: #22262d;
      --text: #e1e3e6;
      --muted: #9aa3ad;
      --border: #3a3f47;
      --row: #262a31;
    }
  }
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 1.5rem; max-width: 920px; margin-inline: auto;
         line-height: 1.45; background: var(--bg); color: var(--text); }
  h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
  h2 { font-size: 1.1rem; margin: 1.75rem 0 .5rem; }
  p.sub { color: var(--muted); margin: 0 0 1rem; }
  fieldset { border: 1px solid var(--border); background: var(--card);
             border-radius: 12px; padding: 1rem; margin: 0 0 1rem; }
  label { display: block; font-size: .8rem; color: var(--muted); margin-bottom: .15rem; }
  input, select, textarea { width: 100%; padding: .5rem .6rem; border-radius: 8px;
    border: 1px solid var(--border); background: var(--field);
    color: var(--text); font: inherit; }
  select option { background: var(--field); color: var(--text); }
  input:focus, select:focus, textarea:focus {
    outline: none; border-color: var(--primary);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 30%, transparent); }
  .grid { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
  .row { display: grid; gap: .5rem; align-items: end;
         grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)) 2.5rem;
         padding: .6rem; border-radius: 10px;
         background: var(--row); margin-bottom: .5rem; }
  .row .del { height: 2.3rem; align-self: end; border: none; cursor: pointer;
    border-radius: 8px; background: #d9534f22; color: #d9534f; font-size: 1.1rem; }
  button { cursor: pointer; font: inherit; }
  .btn { padding: .6rem 1.1rem; border-radius: 10px; border: none;
         background: var(--primary); color: #fff; font-weight: 600; }
  .btn.secondary { background: transparent; color: var(--text);
    border: 1px solid var(--border); }
  .add { margin-top: .25rem; padding: .4rem .8rem; border-radius: 8px;
    border: 1px solid var(--border); background: transparent; color: var(--text); }
  .bar { display: flex; gap: .75rem; flex-wrap: wrap; align-items: center;
         position: sticky; bottom: 0; padding: 1rem 0;
         background: linear-gradient(transparent, var(--bg) 40%); }
  #log { white-space: pre-wrap; font-family: ui-monospace, monospace;
    font-size: .8rem; background: var(--row);
    border-radius: 10px; padding: .75rem; margin-top: .75rem; display: none;
    max-height: 320px; overflow: auto; }
  .links { margin-top: .75rem; display: none; gap: .75rem; flex-wrap: wrap; }
  .muted { color: var(--muted); font-size: .8rem; }
</style>
</head>
<body>
  <h1 data-i18n="title">HA Wrapped</h1>
  <p class="sub" data-i18n="subtitle">Your home's year (or month) in review,
     configured right here and served inside Home Assistant.</p>

  <fieldset>
    <h2 style="margin-top:0" data-i18n="sec_general">General</h2>
    <div class="grid">
      <div><label data-i18n="l_house">House name</label><input id="house_name"></div>
      <div><label data-i18n="l_period">Period</label>
        <select id="period"><option value="yearly" data-i18n="opt_yearly">yearly</option>
          <option value="monthly" data-i18n="opt_monthly">monthly</option></select></div>
      <div><label data-i18n="l_year">Year (optional)</label><input id="year" type="number" data-i18n-ph="ph_auto" placeholder="auto"></div>
      <div><label data-i18n="l_month">Month (monthly only)</label><input id="month" type="number" min="1" max="12" data-i18n-ph="ph_auto" placeholder="auto"></div>
      <div><label data-i18n="l_language">Language</label>
        <select id="language">
          <option value="en">English</option>
          <option value="de">Deutsch</option>
          <option value="fr">Français</option>
          <option value="es">Español</option>
          <option value="it">Italiano</option>
          <option value="nl">Nederlands</option>
          <option value="pt">Português</option>
        </select></div>
      <div><label data-i18n="l_numfmt">Number format</label>
        <select id="number_format">
          <option value="comma_dot">1,234.5</option>
          <option value="dot_comma">1.234,5</option>
          <option value="space_comma">1 234,5</option>
          <option value="plain_dot">1234.5</option>
        </select></div>
      <div><label data-i18n="l_theme">Theme</label>
        <select id="theme"><option value="auto" data-i18n="opt_auto">auto</option>
          <option value="dark" data-i18n="opt_dark">dark</option>
          <option value="light" data-i18n="opt_light">light</option></select></div>
      <div><label data-i18n="l_tz">Timezone offset</label><input id="tz_offset" placeholder="+01:00"></div>
    </div>
    <div style="margin-top:.75rem"><label data-i18n="l_tone">Tone (AI copy personality)</label><input id="tone"></div>
    <div style="margin-top:.75rem"><label data-i18n="l_apikey">Anthropic API key (optional, enables witty copy)</label>
      <input id="anthropic_api_key" type="password" data-i18n-ph="ph_apikey" placeholder="sk-ant-... (leave blank for plain labels)"></div>
  </fieldset>

  <fieldset>
    <h2 style="margin-top:0" data-i18n="sec_statistics">Statistics</h2>
    <p class="muted" data-i18n="help_stats">Long-term statistics (energy, water,
       temperatures). The picker lists entities that actually have statistics.</p>
    <div id="statistics"></div>
    <button class="add" onclick="addStat()" data-i18n="btn_addstat">+ Add statistic</button>
  </fieldset>

  <fieldset>
    <h2 style="margin-top:0" data-i18n="sec_counts">Counts</h2>
    <p class="muted" data-i18n="help_counts">State-change counts via the history
       API (laundry loads, doorbell rings). Comma-separate several entities to
       sum them as one.</p>
    <div id="counts"></div>
    <button class="add" onclick="addCount()" data-i18n="btn_addcount">+ Add count</button>
  </fieldset>

  <datalist id="dl_stats"></datalist>
  <datalist id="dl_entities"></datalist>

  <div class="bar">
    <button class="btn secondary" onclick="saveConfig()" data-i18n="btn_save">Save</button>
    <button class="btn" onclick="generate()" id="genbtn" data-i18n="btn_generate">Save &amp; Generate</button>
    <span id="status" class="muted"></span>
  </div>
  <div class="links" id="links">
    <a class="btn secondary" href="view" target="_blank" data-i18n="link_open">Open wrapped</a>
    <a class="btn secondary" href="download" data-i18n="link_download">Download HTML</a>
  </div>
  <pre id="log"></pre>

<script>
const $ = id => document.getElementById(id);
const GEN = ["sum","mean","max","delta"];

// UI strings per language. The wrapped *output* language is a separate thing
// (it can be any language Claude handles); this only translates this config
// page so it switches the moment you pick a language above.
const I18N = {
  en: {
    title:"HA Wrapped",
    subtitle:"Your home's year (or month) in review, configured right here and served inside Home Assistant.",
    sec_general:"General", sec_statistics:"Statistics", sec_counts:"Counts",
    l_house:"House name", l_period:"Period", l_year:"Year (optional)",
    l_month:"Month (monthly only)", l_language:"Language",
    l_numfmt:"Number format", l_theme:"Theme", l_tz:"Timezone offset",
    l_tone:"Tone (AI copy personality)",
    l_apikey:"Anthropic API key (optional, enables witty copy)",
    opt_yearly:"yearly", opt_monthly:"monthly",
    opt_auto:"auto", opt_dark:"dark", opt_light:"light",
    ph_auto:"auto", ph_apikey:"sk-ant-... (leave blank for plain labels)",
    help_stats:"Long-term statistics (energy, water, temperatures). The picker lists entities that actually have statistics.",
    help_counts:"State-change counts via the history API (laundry loads, doorbell rings). Comma-separate several entities to sum them as one.",
    btn_addstat:"+ Add statistic", btn_addcount:"+ Add count",
    btn_save:"Save", btn_generate:"Save & Generate",
    link_open:"Open wrapped", link_download:"Download HTML",
    col_entity:"entity", col_entities:"entity(ies)", col_label:"label",
    col_aggregate:"aggregate", col_unit:"unit", col_scale:"scale",
    col_decimals:"decimals", col_footnote:"footnote", col_tostate:"to_state",
    st_saved:"Saved ✓", st_savefail:"Save failed", st_working:"Working...",
    st_generating:"Generating...", st_done:"Done ✓",
    st_failed:"Failed", st_error:"Error",
  },
  de: {
    title:"HA Wrapped",
    subtitle:"Das Jahr (oder der Monat) deines Zuhauses im Rückblick, direkt hier eingerichtet und in Home Assistant angezeigt.",
    sec_general:"Allgemein", sec_statistics:"Statistiken", sec_counts:"Zählungen",
    l_house:"Name des Zuhauses", l_period:"Zeitraum", l_year:"Jahr (optional)",
    l_month:"Monat (nur monatlich)", l_language:"Sprache",
    l_numfmt:"Zahlenformat", l_theme:"Design", l_tz:"Zeitzonen-Offset",
    l_tone:"Tonfall (Stil der KI-Texte)",
    l_apikey:"Anthropic API-Key (optional, aktiviert witzige Texte)",
    opt_yearly:"jährlich", opt_monthly:"monatlich",
    opt_auto:"automatisch", opt_dark:"dunkel", opt_light:"hell",
    ph_auto:"automatisch", ph_apikey:"sk-ant-... (leer lassen für schlichte Beschriftungen)",
    help_stats:"Langzeitstatistiken (Energie, Wasser, Temperaturen). Die Auswahl listet Entitäten, die tatsächlich Statistiken haben.",
    help_counts:"Zustandswechsel über die Verlaufs-API (Waschgänge, Türklingeln). Mehrere Entitäten mit Komma trennen, um sie zusammenzuzählen.",
    btn_addstat:"+ Statistik hinzufügen", btn_addcount:"+ Zählung hinzufügen",
    btn_save:"Speichern", btn_generate:"Speichern & Erstellen",
    link_open:"Wrapped öffnen", link_download:"HTML herunterladen",
    col_entity:"Entität", col_entities:"Entität(en)", col_label:"Bezeichnung",
    col_aggregate:"Aggregat", col_unit:"Einheit", col_scale:"Faktor",
    col_decimals:"Dezimalstellen", col_footnote:"Fußnote", col_tostate:"Zielzustand",
    st_saved:"Gespeichert ✓", st_savefail:"Speichern fehlgeschlagen",
    st_working:"Arbeite...", st_generating:"Erstelle...", st_done:"Fertig ✓",
    st_failed:"Fehlgeschlagen", st_error:"Fehler",
  },
  fr: {
    title:"HA Wrapped",
    subtitle:"L'année (ou le mois) de votre maison en rétrospective, configurée ici et affichée dans Home Assistant.",
    sec_general:"Général", sec_statistics:"Statistiques", sec_counts:"Comptages",
    l_house:"Nom de la maison", l_period:"Période", l_year:"Année (facultatif)",
    l_month:"Mois (mensuel uniquement)", l_language:"Langue",
    l_numfmt:"Format des nombres", l_theme:"Thème", l_tz:"Décalage horaire",
    l_tone:"Ton (style des textes IA)",
    l_apikey:"Clé API Anthropic (facultatif, active les textes spirituels)",
    opt_yearly:"annuel", opt_monthly:"mensuel",
    opt_auto:"auto", opt_dark:"sombre", opt_light:"clair",
    ph_auto:"auto", ph_apikey:"sk-ant-... (laisser vide pour des libellés simples)",
    help_stats:"Statistiques de long terme (énergie, eau, températures). Le sélecteur liste les entités qui ont réellement des statistiques.",
    help_counts:"Comptages de changements d'état via l'API d'historique (machines à laver, sonnettes). Séparez plusieurs entités par une virgule pour les additionner.",
    btn_addstat:"+ Ajouter une statistique", btn_addcount:"+ Ajouter un comptage",
    btn_save:"Enregistrer", btn_generate:"Enregistrer et générer",
    link_open:"Ouvrir le wrapped", link_download:"Télécharger le HTML",
    col_entity:"entité", col_entities:"entité(s)", col_label:"libellé",
    col_aggregate:"agrégat", col_unit:"unité", col_scale:"facteur",
    col_decimals:"décimales", col_footnote:"note", col_tostate:"état cible",
    st_saved:"Enregistré ✓", st_savefail:"Échec de l'enregistrement",
    st_working:"En cours...", st_generating:"Génération...", st_done:"Terminé ✓",
    st_failed:"Échec", st_error:"Erreur",
  },
  es: {
    title:"HA Wrapped",
    subtitle:"El año (o el mes) de tu casa en resumen, configurado aquí mismo y mostrado dentro de Home Assistant.",
    sec_general:"General", sec_statistics:"Estadísticas", sec_counts:"Recuentos",
    l_house:"Nombre de la casa", l_period:"Periodo", l_year:"Año (opcional)",
    l_month:"Mes (solo mensual)", l_language:"Idioma",
    l_numfmt:"Formato numérico", l_theme:"Tema", l_tz:"Desfase horario",
    l_tone:"Tono (estilo de los textos de IA)",
    l_apikey:"Clave API de Anthropic (opcional, activa textos ingeniosos)",
    opt_yearly:"anual", opt_monthly:"mensual",
    opt_auto:"automático", opt_dark:"oscuro", opt_light:"claro",
    ph_auto:"automático", ph_apikey:"sk-ant-... (déjalo vacío para etiquetas simples)",
    help_stats:"Estadísticas de largo plazo (energía, agua, temperaturas). El selector muestra las entidades que realmente tienen estadísticas.",
    help_counts:"Recuentos de cambios de estado mediante la API de historial (lavados, timbres). Separa varias entidades con comas para sumarlas como una.",
    btn_addstat:"+ Añadir estadística", btn_addcount:"+ Añadir recuento",
    btn_save:"Guardar", btn_generate:"Guardar y generar",
    link_open:"Abrir el wrapped", link_download:"Descargar HTML",
    col_entity:"entidad", col_entities:"entidad(es)", col_label:"etiqueta",
    col_aggregate:"agregado", col_unit:"unidad", col_scale:"factor",
    col_decimals:"decimales", col_footnote:"nota", col_tostate:"estado destino",
    st_saved:"Guardado ✓", st_savefail:"Error al guardar",
    st_working:"Trabajando...", st_generating:"Generando...", st_done:"Listo ✓",
    st_failed:"Falló", st_error:"Error",
  },
  it: {
    title:"HA Wrapped",
    subtitle:"L'anno (o il mese) della tua casa in sintesi, configurato qui e mostrato dentro Home Assistant.",
    sec_general:"Generale", sec_statistics:"Statistiche", sec_counts:"Conteggi",
    l_house:"Nome della casa", l_period:"Periodo", l_year:"Anno (opzionale)",
    l_month:"Mese (solo mensile)", l_language:"Lingua",
    l_numfmt:"Formato numeri", l_theme:"Tema", l_tz:"Fuso orario",
    l_tone:"Tono (stile dei testi IA)",
    l_apikey:"Chiave API Anthropic (opzionale, attiva testi arguti)",
    opt_yearly:"annuale", opt_monthly:"mensile",
    opt_auto:"auto", opt_dark:"scuro", opt_light:"chiaro",
    ph_auto:"auto", ph_apikey:"sk-ant-... (lascia vuoto per etichette semplici)",
    help_stats:"Statistiche a lungo termine (energia, acqua, temperature). Il selettore elenca le entità che hanno davvero statistiche.",
    help_counts:"Conteggi dei cambi di stato tramite l'API della cronologia (lavaggi, campanelli). Separa più entità con la virgola per sommarle come una.",
    btn_addstat:"+ Aggiungi statistica", btn_addcount:"+ Aggiungi conteggio",
    btn_save:"Salva", btn_generate:"Salva e genera",
    link_open:"Apri il wrapped", link_download:"Scarica HTML",
    col_entity:"entità", col_entities:"entità", col_label:"etichetta",
    col_aggregate:"aggregato", col_unit:"unità", col_scale:"fattore",
    col_decimals:"decimali", col_footnote:"nota", col_tostate:"stato finale",
    st_saved:"Salvato ✓", st_savefail:"Salvataggio non riuscito",
    st_working:"In corso...", st_generating:"Generazione...", st_done:"Fatto ✓",
    st_failed:"Non riuscito", st_error:"Errore",
  },
  nl: {
    title:"HA Wrapped",
    subtitle:"Het jaar (of de maand) van je huis in het kort, hier ingesteld en getoond in Home Assistant.",
    sec_general:"Algemeen", sec_statistics:"Statistieken", sec_counts:"Tellingen",
    l_house:"Naam van het huis", l_period:"Periode", l_year:"Jaar (optioneel)",
    l_month:"Maand (alleen maandelijks)", l_language:"Taal",
    l_numfmt:"Getalnotatie", l_theme:"Thema", l_tz:"Tijdzone-offset",
    l_tone:"Toon (stijl van AI-teksten)",
    l_apikey:"Anthropic API-sleutel (optioneel, schakelt geestige teksten in)",
    opt_yearly:"jaarlijks", opt_monthly:"maandelijks",
    opt_auto:"auto", opt_dark:"donker", opt_light:"licht",
    ph_auto:"auto", ph_apikey:"sk-ant-... (leeg laten voor gewone labels)",
    help_stats:"Langetermijnstatistieken (energie, water, temperaturen). De keuzelijst toont entiteiten die echt statistieken hebben.",
    help_counts:"Tellingen van statuswijzigingen via de geschiedenis-API (wasbeurten, deurbellen). Scheid meerdere entiteiten met komma's om ze als één op te tellen.",
    btn_addstat:"+ Statistiek toevoegen", btn_addcount:"+ Telling toevoegen",
    btn_save:"Opslaan", btn_generate:"Opslaan en genereren",
    link_open:"Wrapped openen", link_download:"HTML downloaden",
    col_entity:"entiteit", col_entities:"entiteit(en)", col_label:"label",
    col_aggregate:"aggregaat", col_unit:"eenheid", col_scale:"factor",
    col_decimals:"decimalen", col_footnote:"voetnoot", col_tostate:"doelstatus",
    st_saved:"Opgeslagen ✓", st_savefail:"Opslaan mislukt",
    st_working:"Bezig...", st_generating:"Genereren...", st_done:"Klaar ✓",
    st_failed:"Mislukt", st_error:"Fout",
  },
  pt: {
    title:"HA Wrapped",
    subtitle:"O ano (ou o mês) da sua casa em resumo, configurado aqui e apresentado dentro do Home Assistant.",
    sec_general:"Geral", sec_statistics:"Estatísticas", sec_counts:"Contagens",
    l_house:"Nome da casa", l_period:"Período", l_year:"Ano (opcional)",
    l_month:"Mês (apenas mensal)", l_language:"Idioma",
    l_numfmt:"Formato dos números", l_theme:"Tema", l_tz:"Diferença de fuso horário",
    l_tone:"Tom (estilo dos textos de IA)",
    l_apikey:"Chave de API da Anthropic (opcional, ativa textos espirituosos)",
    opt_yearly:"anual", opt_monthly:"mensal",
    opt_auto:"auto", opt_dark:"escuro", opt_light:"claro",
    ph_auto:"auto", ph_apikey:"sk-ant-... (deixe vazio para rótulos simples)",
    help_stats:"Estatísticas de longo prazo (energia, água, temperaturas). O seletor lista as entidades que realmente têm estatísticas.",
    help_counts:"Contagens de mudanças de estado via API de histórico (lavagens, campainhas). Separe várias entidades por vírgula para somá-las como uma.",
    btn_addstat:"+ Adicionar estatística", btn_addcount:"+ Adicionar contagem",
    btn_save:"Guardar", btn_generate:"Guardar e gerar",
    link_open:"Abrir o wrapped", link_download:"Transferir HTML",
    col_entity:"entidade", col_entities:"entidade(s)", col_label:"rótulo",
    col_aggregate:"agregado", col_unit:"unidade", col_scale:"fator",
    col_decimals:"casas decimais", col_footnote:"nota de rodapé", col_tostate:"estado alvo",
    st_saved:"Guardado ✓", st_savefail:"Falha ao guardar",
    st_working:"A trabalhar...", st_generating:"A gerar...", st_done:"Concluído ✓",
    st_failed:"Falhou", st_error:"Erro",
  },
};
let LANG = "en";
const t = key => (I18N[LANG] && I18N[LANG][key]) || I18N.en[key] || key;

// Walk every tagged node and (re)apply the current language. Works on the
// static markup and on dynamically added stat/count rows alike.
function applyLang(lang){
  LANG = (I18N[lang] ? lang : "en");
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach(n => {
    n.textContent = t(n.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(n => {
    n.setAttribute("placeholder", t(n.getAttribute("data-i18n-ph")));
  });
}

function el(tag, attrs={}, ...kids){
  const e=document.createElement(tag);
  for(const k in attrs){ if(k==="value") e.value=attrs[k]; else e.setAttribute(k,attrs[k]); }
  kids.forEach(c=>e.append(c)); return e;
}

function statRow(s={}){
  const wrap=el("div",{class:"row"});
  wrap.append(
    field("entity_id","col_entity", s.entity_id||"", "dl_stats"),
    field("label","col_label", s.label||""),
    selectField("aggregate", GEN, s.aggregate||"sum"),
    field("unit","col_unit", s.unit||""),
    field("scale","col_scale", s.scale??""),
    field("decimals","col_decimals", s.decimals??""),
    field("footnote","col_footnote", s.footnote||""),
  );
  wrap.append(delBtn(wrap));
  return wrap;
}
function countRow(c={}){
  const wrap=el("div",{class:"row"});
  const eid = Array.isArray(c.entity_id) ? c.entity_id.join(", ") : (c.entity_id||"");
  wrap.append(
    field("entity_id","col_entities", eid, "dl_entities"),
    field("to_state","col_tostate", c.to_state||"on"),
    field("label","col_label", c.label||""),
    field("unit","col_unit", c.unit||""),
    field("scale","col_scale", c.scale??""),
    field("decimals","col_decimals", c.decimals??""),
    field("footnote","col_footnote", c.footnote||""),
  );
  wrap.append(delBtn(wrap));
  return wrap;
}
function field(key,i18nKey,val,list){
  const d=el("div");
  d.append(el("label",{["data-i18n"]:i18nKey}, t(i18nKey)));
  const attrs={class:"f",["data-k"]:key,value:val};
  if(list) attrs.list=list;
  d.append(el("input",attrs));
  return d;
}
function selectField(key,opts,val){
  // aggregate options (sum/mean/max/delta) are technical, left untranslated
  const d=el("div"); d.append(el("label",{["data-i18n"]:"col_"+key}, t("col_"+key)));
  const s=el("select",{class:"f",["data-k"]:key});
  opts.forEach(o=>{const op=el("option",{value:o},o); if(o===val)op.selected=true; s.append(op);});
  d.append(s); return d;
}
function delBtn(wrap){ const b=el("button",{class:"del",title:"remove"},"×");
  b.onclick=()=>wrap.remove(); return b; }
function addStat(s){ $("statistics").append(statRow(s)); }
function addCount(c){ $("counts").append(countRow(c)); }

function readRows(containerId){
  return [...$(containerId).children].map(row=>{
    const o={};
    row.querySelectorAll(".f").forEach(f=>{
      let v=f.value.trim(); const k=f.dataset.k;
      if(v==="") return;
      if(k==="scale") v=parseFloat(v);
      else if(k==="decimals") v=parseInt(v,10);
      o[k]=v;
    });
    return o;
  }).filter(o=>o.entity_id);
}

function collect(){
  const cfg={
    house_name:$("house_name").value, period:$("period").value,
    language:$("language").value, number_format:$("number_format").value,
    theme:$("theme").value, tz_offset:$("tz_offset").value,
    tone:$("tone").value, anthropic_api_key:$("anthropic_api_key").value,
    statistics:readRows("statistics"), counts:readRows("counts"),
  };
  const y=$("year").value.trim(), m=$("month").value.trim();
  if(y) cfg.year=parseInt(y,10);
  if(m) cfg.month=parseInt(m,10);
  // counts: comma-separated -> list
  cfg.counts.forEach(c=>{
    if(typeof c.entity_id==="string" && c.entity_id.includes(",")){
      c.entity_id=c.entity_id.split(",").map(x=>x.trim()).filter(Boolean);
    }
  });
  return cfg;
}

async function saveConfig(){
  const r=await fetch("api/config",{method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify(collect())});
  $("status").textContent = r.ok ? t("st_saved") : t("st_savefail");
}

async function generate(){
  await saveConfig();
  const btn=$("genbtn"); btn.disabled=true; btn.textContent=t("st_generating");
  $("status").textContent=t("st_working"); $("log").style.display="block"; $("log").textContent="";
  try{
    const r=await fetch("api/generate",{method:"POST"});
    const j=await r.json();
    $("log").textContent=(j.log||[]).join("\n")+(j.error?("\n[FAIL] "+j.error):"");
    if(j.ok){ $("status").textContent=t("st_done"); $("links").style.display="flex"; }
    else $("status").textContent=t("st_failed");
  }catch(e){ $("status").textContent=t("st_error"); $("log").textContent=String(e); }
  btn.disabled=false; btn.textContent=t("btn_generate");
}

async function loadEntities(){
  try{
    const [stats,ents]=await Promise.all([
      fetch("api/statistics").then(r=>r.json()),
      fetch("api/entities").then(r=>r.json()),
    ]);
    if(Array.isArray(stats)) fill("dl_stats", stats);
    if(Array.isArray(ents)) fill("dl_entities", ents);
  }catch(e){ /* pickers are a nicety; typing still works */ }
}
function fill(listId, items){
  const dl=$(listId); dl.innerHTML="";
  items.forEach(i=>{ const o=el("option",{value:i.entity_id}); o.label=i.name||""; dl.append(o); });
}

async function init(){
  const cfg=await fetch("api/config").then(r=>r.json());
  // migrate legacy country-named number formats to the neutral keys
  const NF_LEGACY={en:"comma_dot",de:"dot_comma"};
  if(cfg.number_format in NF_LEGACY) cfg.number_format=NF_LEGACY[cfg.number_format];
  ["house_name","period","language","number_format","theme","tz_offset","tone","anthropic_api_key"]
    .forEach(k=>{ if(cfg[k]!=null) $(k).value=cfg[k]; });
  if(cfg.year) $("year").value=cfg.year;
  if(cfg.month) $("month").value=cfg.month;
  // switch the whole UI to the saved language, and again whenever it changes
  applyLang($("language").value || "en");
  $("language").addEventListener("change", e => applyLang(e.target.value));
  (cfg.statistics||[]).forEach(addStat);
  (cfg.counts||[]).forEach(addCount);
  if(!(cfg.statistics||[]).length) addStat();
  if(!(cfg.counts||[]).length) addCount();
  applyLang($("language").value || "en");  // re-apply for the freshly added rows
  loadEntities();
}
init();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=PORT)
