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
    "number_format": "en",
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
    except Exception as e:  # noqa: BLE001
        return web.json_response(
            {"ok": False, "error": str(e), "log": logs}, status=400)

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
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 1.5rem; max-width: 920px; margin-inline: auto;
         line-height: 1.45; }
  h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
  h2 { font-size: 1.1rem; margin: 1.75rem 0 .5rem; }
  p.sub { opacity: .7; margin: 0 0 1rem; }
  fieldset { border: 1px solid color-mix(in srgb, currentColor 20%, transparent);
             border-radius: 12px; padding: 1rem; margin: 0 0 1rem; }
  label { display: block; font-size: .8rem; opacity: .8; margin-bottom: .15rem; }
  input, select, textarea { width: 100%; padding: .5rem .6rem; border-radius: 8px;
    border: 1px solid color-mix(in srgb, currentColor 25%, transparent);
    background: color-mix(in srgb, currentColor 4%, transparent);
    color: inherit; font: inherit; }
  .grid { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
  .row { display: grid; gap: .5rem; align-items: end;
         grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)) 2.5rem;
         padding: .6rem; border-radius: 10px;
         background: color-mix(in srgb, currentColor 5%, transparent);
         margin-bottom: .5rem; }
  .row .del { height: 2.3rem; align-self: end; border: none; cursor: pointer;
    border-radius: 8px; background: #d9534f22; color: #d9534f; font-size: 1.1rem; }
  button { cursor: pointer; font: inherit; }
  .btn { padding: .6rem 1.1rem; border-radius: 10px; border: none;
         background: #6c5ce7; color: #fff; font-weight: 600; }
  .btn.secondary { background: color-mix(in srgb, currentColor 12%, transparent);
    color: inherit; }
  .add { margin-top: .25rem; padding: .4rem .8rem; border-radius: 8px; border: none;
    background: color-mix(in srgb, currentColor 12%, transparent); color: inherit; }
  .bar { display: flex; gap: .75rem; flex-wrap: wrap; align-items: center;
         position: sticky; bottom: 0; padding: 1rem 0;
         background: linear-gradient(transparent, Canvas 40%); }
  #log { white-space: pre-wrap; font-family: ui-monospace, monospace;
    font-size: .8rem; background: color-mix(in srgb, currentColor 6%, transparent);
    border-radius: 10px; padding: .75rem; margin-top: .75rem; display: none;
    max-height: 320px; overflow: auto; }
  .links { margin-top: .75rem; display: none; gap: .75rem; flex-wrap: wrap; }
  .muted { opacity: .6; font-size: .8rem; }
</style>
</head>
<body>
  <h1>HA Wrapped 🎁</h1>
  <p class="sub">Your home's year (or month) in review — configured right here,
     served right in Home Assistant.</p>

  <fieldset>
    <h2 style="margin-top:0">General</h2>
    <div class="grid">
      <div><label>House name</label><input id="house_name"></div>
      <div><label>Period</label>
        <select id="period"><option value="yearly">yearly</option>
          <option value="monthly">monthly</option></select></div>
      <div><label>Year (optional)</label><input id="year" type="number" placeholder="auto"></div>
      <div><label>Month (monthly only)</label><input id="month" type="number" min="1" max="12" placeholder="auto"></div>
      <div><label>Language</label>
        <select id="language"><option value="en">en</option><option value="de">de</option></select></div>
      <div><label>Number format</label>
        <select id="number_format"><option value="en">en (1,234.5)</option><option value="de">de (1.234,5)</option></select></div>
      <div><label>Theme</label>
        <select id="theme"><option value="auto">auto</option><option value="dark">dark</option><option value="light">light</option></select></div>
      <div><label>Timezone offset</label><input id="tz_offset" placeholder="+01:00"></div>
    </div>
    <div style="margin-top:.75rem"><label>Tone (AI copy personality)</label><input id="tone"></div>
    <div style="margin-top:.75rem"><label>Anthropic API key (optional — enables witty copy)</label>
      <input id="anthropic_api_key" type="password" placeholder="sk-ant-… (leave blank for plain labels)"></div>
  </fieldset>

  <fieldset>
    <h2 style="margin-top:0">Statistics</h2>
    <p class="muted">Long-term statistics (energy, water, temperatures…). The
       picker lists entities that actually have statistics.</p>
    <div id="statistics"></div>
    <button class="add" onclick="addStat()">+ Add statistic</button>
  </fieldset>

  <fieldset>
    <h2 style="margin-top:0">Counts</h2>
    <p class="muted">State-change counts via the history API (laundry loads,
       doorbell rings…). Comma-separate several entities to sum them as one.</p>
    <div id="counts"></div>
    <button class="add" onclick="addCount()">+ Add count</button>
  </fieldset>

  <datalist id="dl_stats"></datalist>
  <datalist id="dl_entities"></datalist>

  <div class="bar">
    <button class="btn secondary" onclick="saveConfig()">Save</button>
    <button class="btn" onclick="generate()" id="genbtn">Save &amp; Generate</button>
    <span id="status" class="muted"></span>
  </div>
  <div class="links" id="links">
    <a class="btn secondary" href="view" target="_blank">Open wrapped ↗</a>
    <a class="btn secondary" href="download">Download HTML</a>
  </div>
  <pre id="log"></pre>

<script>
const $ = id => document.getElementById(id);
const GEN = ["sum","mean","max","delta"];

function el(tag, attrs={}, ...kids){
  const e=document.createElement(tag);
  for(const k in attrs){ if(k==="value") e.value=attrs[k]; else e.setAttribute(k,attrs[k]); }
  kids.forEach(c=>e.append(c)); return e;
}

function statRow(s={}){
  const wrap=el("div",{class:"row"});
  wrap.append(
    field("entity_id","entity", s.entity_id||"", "dl_stats"),
    field("label","label", s.label||""),
    selectField("aggregate", GEN, s.aggregate||"sum"),
    field("unit","unit", s.unit||""),
    field("scale","scale", s.scale??""),
    field("decimals","decimals", s.decimals??""),
    field("footnote","footnote", s.footnote||""),
  );
  wrap.append(delBtn(wrap));
  return wrap;
}
function countRow(c={}){
  const wrap=el("div",{class:"row"});
  const eid = Array.isArray(c.entity_id) ? c.entity_id.join(", ") : (c.entity_id||"");
  wrap.append(
    field("entity_id","entity(ies)", eid, "dl_entities"),
    field("to_state","to_state", c.to_state||"on"),
    field("label","label", c.label||""),
    field("unit","unit", c.unit||""),
    field("scale","scale", c.scale??""),
    field("decimals","decimals", c.decimals??""),
    field("footnote","footnote", c.footnote||""),
  );
  wrap.append(delBtn(wrap));
  return wrap;
}
function field(key,label,val,list){
  const d=el("div");
  d.append(el("label",{},label));
  const attrs={class:"f",["data-k"]:key,value:val};
  if(list) attrs.list=list;
  d.append(el("input",attrs));
  return d;
}
function selectField(key,opts,val){
  const d=el("div"); d.append(el("label",{},key));
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
  $("status").textContent = r.ok ? "Saved ✓" : "Save failed";
}

async function generate(){
  await saveConfig();
  const btn=$("genbtn"); btn.disabled=true; btn.textContent="Generating…";
  $("status").textContent="Working…"; $("log").style.display="block"; $("log").textContent="";
  try{
    const r=await fetch("api/generate",{method:"POST"});
    const j=await r.json();
    $("log").textContent=(j.log||[]).join("\n")+(j.error?("\n[FAIL] "+j.error):"");
    if(j.ok){ $("status").textContent="Done ✓"; $("links").style.display="flex"; }
    else $("status").textContent="Failed";
  }catch(e){ $("status").textContent="Error"; $("log").textContent=String(e); }
  btn.disabled=false; btn.textContent="Save & Generate";
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
  ["house_name","period","language","number_format","theme","tz_offset","tone","anthropic_api_key"]
    .forEach(k=>{ if(cfg[k]!=null) $(k).value=cfg[k]; });
  if(cfg.year) $("year").value=cfg.year;
  if(cfg.month) $("month").value=cfg.month;
  (cfg.statistics||[]).forEach(addStat);
  (cfg.counts||[]).forEach(addCount);
  if(!(cfg.statistics||[]).length) addStat();
  if(!(cfg.counts||[]).length) addCount();
  loadEntities();
}
init();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=PORT)
