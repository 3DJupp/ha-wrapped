#!/usr/bin/env python3
"""
HA Wrapped - a Spotify-Wrapped-style year review for your Home Assistant.

Pulls long-term statistics (WebSocket API) and state-change counts (REST API)
for a configurable list of entities, optionally generates witty German copy
via the Claude API, and renders a self-contained shareable HTML file.

Usage:
    export HA_TOKEN="<long-lived access token>"
    export ANTHROPIC_API_KEY="sk-ant-..."   # optional, for the witty copy
    python3 wrapped.py --config config.yaml

Requires: pip install websockets pyyaml requests
"""

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests
import websockets
import yaml

# ---------------------------------------------------------------- helpers


def iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S%z")


def find_template() -> Path:
    """Locate template.html next to the script or in an installed prefix."""
    candidates = [
        Path(__file__).resolve().parent / "template.html",
        Path(sys.prefix) / "share" / "ha-wrapped" / "template.html",
    ]
    for p in candidates:
        if p.exists():
            return p
    sys.exit("template.html not found (looked in: "
             + ", ".join(str(p) for p in candidates) + ")")


def check_api(ha_url: str, token: str) -> str:
    """Ping the HA REST API; returns the API message or exits with help."""
    try:
        r = requests.get(f"{ha_url.rstrip('/')}/api/",
                         headers={"Authorization": f"Bearer {token}"},
                         timeout=15)
    except requests.RequestException as e:
        sys.exit(f"  [FAIL] cannot reach {ha_url}: {e}")
    if r.status_code == 401:
        sys.exit("  [FAIL] HA rejected the token (401). Create a new "
                 "long-lived access token in your HA profile.")
    r.raise_for_status()
    return r.json().get("message", "API running.")


def year_bounds(year: int, tz_offset: str = "+01:00"):
    start = dt.datetime.fromisoformat(f"{year}-01-01T00:00:00{tz_offset}")
    end = dt.datetime.fromisoformat(f"{year + 1}-01-01T00:00:00{tz_offset}")
    now = dt.datetime.now(dt.timezone.utc)
    if end.astimezone(dt.timezone.utc) > now:
        end = now
    return start, end


# ------------------------------------------------- long-term statistics


async def fetch_statistics(ha_url, token, statistic_ids, start, end):
    """recorder/statistics_during_period over the WebSocket API, monthly."""
    ws_url = ha_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = ws_url.rstrip("/") + "/api/websocket"

    async with websockets.connect(ws_url, max_size=16 * 1024 * 1024) as ws:
        await ws.recv()  # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(await ws.recv())
        if auth.get("type") != "auth_ok":
            raise RuntimeError(f"WebSocket auth failed: {auth}")

        await ws.send(json.dumps({
            "id": 1,
            "type": "recorder/statistics_during_period",
            "start_time": iso(start),
            "end_time": iso(end),
            "statistic_ids": statistic_ids,
            "period": "month",
            "types": ["sum", "mean", "max", "min", "state"],
        }))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == 1 and msg.get("type") == "result":
                if not msg.get("success"):
                    raise RuntimeError(f"statistics query failed: {msg}")
                return msg["result"]


def reduce_stat(rows, aggregate):
    """Collapse monthly statistic rows into (total, monthly_series)."""
    if not rows:
        return None, []

    if aggregate == "sum":
        # 'sum' is cumulative; the yearly total is last - first, the
        # monthly series is the per-month delta.
        series, prev = [], None
        for r in rows:
            s = r.get("sum")
            if s is None:
                series.append(0.0)
                continue
            series.append(0.0 if prev is None else max(0.0, s - prev))
            prev = s
        sums = [r["sum"] for r in rows if r.get("sum") is not None]
        total = (sums[-1] - sums[0]) + series[0] if sums else 0.0
        # series[0] delta vs. before-window is unknown; fall back to the
        # plain difference if that looks degenerate
        if total <= 0 and sums:
            total = sums[-1] - sums[0]
        return total, series

    if aggregate == "mean":
        vals = [r["mean"] for r in rows if r.get("mean") is not None]
        series = [r.get("mean") or 0.0 for r in rows]
        return (sum(vals) / len(vals) if vals else None), series

    if aggregate == "max":
        vals = [r["max"] for r in rows if r.get("max") is not None]
        series = [r.get("max") or 0.0 for r in rows]
        return (max(vals) if vals else None), series

    raise ValueError(f"unknown aggregate: {aggregate}")


# ------------------------------------------------- state-change counts


def fetch_count(ha_url, token, entity_id, to_state, start, end):
    """Count transitions into `to_state` using the REST history API."""
    url = (
        f"{ha_url.rstrip('/')}/api/history/period/{iso(start)}"
        f"?filter_entity_id={entity_id}&end_time={iso(end)}"
        f"&minimal_response&no_attributes"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                     timeout=300)
    r.raise_for_status()
    data = r.json()
    if not data or not data[0]:
        return 0, [0] * 12

    count = 0
    monthly = [0] * 12
    prev = None
    for st in data[0]:
        state = st.get("state")
        when = st.get("last_changed") or st.get("last_updated")
        if state == to_state and prev != to_state:
            count += 1
            if when:
                monthly[dt.datetime.fromisoformat(when).month - 1] += 1
        prev = state
    return count, monthly


# ------------------------------------------------------- Claude copy


def claude_copy(stats, year, language="en", tone="dry, witty, deadpan"):
    """Ask Claude for witty one-liners. Returns {} on any failure."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("  (no ANTHROPIC_API_KEY set, skipping witty copy)")
        return {}

    facts = [
        {"id": s["id"], "label": s["label"],
         "value": s["display_value"], "unit": s.get("unit", "")}
        for s in stats
    ]
    prompt = (
        f"You write the copy for a 'Home Assistant Wrapped {year}', a "
        "Spotify-Wrapped-style year review for a smart home.\n"
        f"Language: {language}. Tone: {tone}. Short and punchy, "
        "no cringe, no emojis, no exclamation mark spam.\n\n"
        f"Here are the yearly stats as JSON:\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n\n"
        "Respond ONLY with a JSON object, no markdown fences:\n"
        "{\n"
        '  "intro_title": "...", "intro_sub": "...",\n'
        '  "outro_title": "...", "outro_sub": "...",\n'
        '  "cards": { "<id>": {"headline": "...", "quip": "..."} }\n'
        "}\n"
        "headline = short title (max 6 words, without the number), "
        "quip = one deadpan line putting the number into perspective."
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json()["content"])
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:  # noqa: BLE001
        print(f"  (Claude copy failed, using plain labels: {e})")
        return {}


# ------------------------------------------------------------- main


def fmt(value, decimals, number_format="en"):
    if value is None:
        return "?"
    s = f"{value:,.{decimals}f}"
    if number_format == "de":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    ha_url = cfg["ha_url"]
    token = os.environ.get("HA_TOKEN") or cfg.get("token")
    if not token:
        sys.exit("Set HA_TOKEN or put 'token:' in the config.")

    year = cfg.get("year", dt.date.today().year)
    lang = cfg.get("language", "en")
    nfmt = cfg.get("number_format", "de" if lang == "de" else "en")
    start, end = year_bounds(year, cfg.get("tz_offset", "+01:00"))

    # --- preflight: report what is configured before touching the network
    n_stats = len(cfg.get("statistics", []))
    n_counts = len(cfg.get("counts", []))
    print(f"HA Wrapped {year}: {iso(start)} .. {iso(end)}")
    print("Preflight:")
    print(f"  [ OK ] config: {args.config} "
          f"({n_stats} statistics, {n_counts} counts)")
    src = "env HA_TOKEN" if os.environ.get("HA_TOKEN") else "config 'token:'"
    print(f"  [ OK ] HA token: set via {src}")
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("  [ OK ] ANTHROPIC_API_KEY: set, witty copy enabled")
    else:
        print("  [WARN] ANTHROPIC_API_KEY: not set, plain labels only")
    if n_stats + n_counts == 0:
        sys.exit("  [FAIL] no 'statistics:' or 'counts:' entries configured.")
    print(f"  [ OK ] {ha_url}: {check_api(ha_url, token)}")

    stats_out = []
    entity_status = []

    # --- numeric long-term statistics
    stat_cfgs = cfg.get("statistics", [])
    if stat_cfgs:
        ids = [s["entity_id"] for s in stat_cfgs]
        print(f"Fetching long-term statistics for {len(ids)} entities ...")
        result = asyncio.run(fetch_statistics(ha_url, token, ids, start, end))
        for s in stat_cfgs:
            rows = result.get(s["entity_id"], [])
            total, series = reduce_stat(rows, s.get("aggregate", "sum"))
            if total is None:
                print(f"  ! no data for {s['entity_id']}")
                entity_status.append({"id": s["entity_id"],
                                      "kind": "statistics",
                                      "status": "no data"})
                continue
            entity_status.append({"id": s["entity_id"], "kind": "statistics",
                                  "status": f"ok ({len(rows)} months)"})
            scale = s.get("scale", 1.0)
            total *= scale
            series = [v * scale for v in series]
            stats_out.append({
                "id": s["entity_id"],
                "label": s["label"],
                "unit": s.get("unit", ""),
                "value": total,
                "display_value": fmt(total, s.get("decimals", 0), nfmt),
                "series": series,
                "footnote": s.get("footnote", ""),
            })
            print(f"  {s['label']}: {total:.1f} {s.get('unit','')}")

    # --- state-change counts
    for c in cfg.get("counts", []):
        print(f"Counting {c['entity_id']} -> '{c['to_state']}' ...")
        try:
            n, monthly = fetch_count(ha_url, token, c["entity_id"],
                                     c["to_state"], start, end)
        except Exception as e:  # noqa: BLE001
            print(f"  ! failed: {e}")
            entity_status.append({"id": c["entity_id"], "kind": "counts",
                                  "status": f"error: {e}"})
            continue
        entity_status.append({"id": c["entity_id"], "kind": "counts",
                              "status": f"ok ({n} events)" if n
                              else "no events"})
        scale = c.get("scale", 1.0)
        value = n * scale
        stats_out.append({
            "id": c["entity_id"],
            "label": c["label"],
            "unit": c.get("unit", "x"),
            "value": value,
            "display_value": fmt(value, c.get("decimals", 0), nfmt),
            "series": [m * scale for m in monthly],
            "footnote": c.get("footnote", ""),
        })
        print(f"  {c['label']}: {n} events")

    if not stats_out:
        sys.exit("No stats collected, nothing to render.")

    # --- copywriting
    print("Generating copy ...")
    copy = claude_copy(stats_out, year, lang,
                       cfg.get("tone", "dry, witty, deadpan"))
    cards_copy = copy.get("cards", {})
    for s in stats_out:
        cc = cards_copy.get(s["id"], {})
        s["headline"] = cc.get("headline", s["label"])
        s["quip"] = cc.get("quip", "")

    i18n = {
        "de": {"scroll": "scrollen", "trend": "Verlauf",
               "jan": "Jan", "dec": "Dez", "theme": "Hell / Dunkel",
               "intro_sub": "Was dein Zuhause dieses Jahr so getrieben hat.",
               "outro_title": "Bis naechstes Jahr."},
        "en": {"scroll": "scroll", "trend": "over the year",
               "jan": "Jan", "dec": "Dec", "theme": "light / dark",
               "intro_sub": "What your home has been up to this year.",
               "outro_title": "See you next year."},
    }.get(lang, None) or {
        "scroll": "scroll", "trend": "trend", "jan": "Jan", "dec": "Dec",
        "theme": "light / dark",
        "intro_sub": "", "outro_title": f"Wrapped {year}"}

    payload = {
        "year": year,
        "lang": lang,
        "house": cfg.get("house_name", "My Home"),
        "theme": cfg.get("theme", "auto"),
        "i18n": i18n,
        "intro_title": copy.get("intro_title", f"Wrapped {year}"),
        "intro_sub": copy.get("intro_sub", i18n["intro_sub"]),
        "outro_title": copy.get("outro_title", i18n["outro_title"]),
        "outro_sub": copy.get("outro_sub", ""),
        "stats": stats_out,
        # self-debug info, shown in the page's status panel
        "meta": {
            "generated_at": dt.datetime.now().astimezone()
                              .isoformat(timespec="seconds"),
            "range": [iso(start), iso(end)],
            "ai_copy": bool(copy),
            "entities": entity_status,
        },
    }

    # --- render
    template = find_template().read_text()
    token_str = '"__WRAPPED_DATA__"'
    if token_str not in template:
        token_str = "__WRAPPED_DATA__"
    html = template.replace(token_str,
                            json.dumps(payload, ensure_ascii=False))
    out = Path(args.output or f"ha_wrapped_{year}.html")
    out.write_text(html)

    ok = sum(1 for e in entity_status if e["status"].startswith("ok"))
    print(f"Status: {ok}/{len(entity_status)} entities delivered data, "
          f"AI copy: {'generated' if copy else 'fallback labels'}")
    print(f"Done -> {out.resolve()}")


if __name__ == "__main__":
    main()
