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
import calendar
import datetime as dt
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests
import websockets
import yaml

# ---------------------------------------------------------------- helpers


def iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S%z")


# month abbreviations for the chart axis and the partial-year range label
MONTHS = {
    "de": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
           "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


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


def _tzinfo(tz_offset: str) -> dt.tzinfo:
    return dt.datetime.fromisoformat(f"2000-01-01T00:00:00{tz_offset}").tzinfo


def compute_period(cfg: dict, tz_offset: str = "+01:00") -> dict:
    """Work out the time window for the configured period.

    ``period: yearly`` (default) wraps a full calendar year (``year:``,
    default the current year). ``period: monthly`` wraps a single month
    (``year:``/``month:``, default the month that just ended -- so a run
    on the 1st of a month covers the previous one).
    """
    mode = cfg.get("period", "yearly")
    now_utc = dt.datetime.now(dt.timezone.utc)

    if mode == "monthly":
        today = dt.datetime.now(_tzinfo(tz_offset))
        last_month_end = today.replace(day=1) - dt.timedelta(days=1)
        year = cfg.get("year", last_month_end.year)
        month = cfg.get("month", last_month_end.month)
        start = dt.datetime.fromisoformat(
            f"{year}-{month:02d}-01T00:00:00{tz_offset}")
        n_periods = calendar.monthrange(year, month)[1]
        full_end = start + dt.timedelta(days=n_periods)
    else:
        year = cfg.get("year", dt.date.today().year)
        month = None
        start = dt.datetime.fromisoformat(f"{year}-01-01T00:00:00{tz_offset}")
        full_end = dt.datetime.fromisoformat(f"{year + 1}-01-01T00:00:00{tz_offset}")
        n_periods = 12

    end = full_end
    if end.astimezone(dt.timezone.utc) > now_utc:
        end = now_utc

    return {"mode": mode, "year": year, "month": month, "start": start,
            "end": end, "full_end": full_end, "n_periods": n_periods}


# ------------------------------------------------- long-term statistics


async def fetch_statistics(ha_url, token, statistic_ids, start, end, period="month"):
    """recorder/statistics_during_period over the WebSocket API.

    `period` is "month" for a yearly wrapped (12 rows) or "day" for a
    monthly wrapped (one row per day of that month)."""
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
            "period": period,
            "types": ["sum", "mean", "max", "min", "state", "change"],
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
        # 'change' is the exact per-period delta; sum it for the total.
        if any(r.get("change") is not None for r in rows):
            series = [r.get("change") or 0.0 for r in rows]
            return sum(series), series
        # fallback for older HA without 'change': 'sum' is cumulative, the
        # yearly total is last - first (misses the first month's delta).
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

    if aggregate == "delta":
        # for sensors that report an absolute/lifetime counter (e.g. a
        # coffee machine's total brew count, state_class: total_increasing)
        # rather than a recorder-tracked 'sum': the period total is the
        # last reading minus the first, not the sum of the readings.
        series, prev = [], None
        for r in rows:
            s = r.get("state")
            if s is None:
                series.append(0.0)
                continue
            series.append(0.0 if prev is None else max(0.0, s - prev))
            prev = s
        states = [r["state"] for r in rows if r.get("state") is not None]
        total = (states[-1] - states[0]) if len(states) >= 2 else 0.0
        return total, series

    raise ValueError(f"unknown aggregate: {aggregate}")


# ------------------------------------------------- state-change counts


def fetch_count(ha_url, token, entity_ids, to_state, start, end,
                n_periods=12, period_unit="month"):
    """Count transitions into `to_state` using the REST history API.

    `entity_ids` may be a single entity id or a list -- counts and the
    per-period series are summed across all of them (e.g. several covers
    that should read as one "shutter travel" stat). `period_unit` is
    "month" for a yearly wrapped or "day" for a monthly wrapped."""
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    # timestamps must be URL-encoded: a raw '+' in the query string is
    # decoded as a space and HA answers 400 Bad Request
    url = (f"{ha_url.rstrip('/')}/api/history/period/"
           + quote(iso(start), safe=""))
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                     params={"filter_entity_id": ",".join(entity_ids),
                             "end_time": iso(end),
                             "minimal_response": "",
                             "no_attributes": ""},
                     timeout=300)
    r.raise_for_status()
    data = r.json()

    count = 0
    series = [0] * n_periods
    for history in data:
        prev = None
        for st in history:
            state = st.get("state")
            when = st.get("last_changed") or st.get("last_updated")
            if state == to_state and prev != to_state:
                count += 1
                if when:
                    ts = dt.datetime.fromisoformat(when)
                    idx = (ts.day if period_unit == "day" else ts.month) - 1
                    if 0 <= idx < n_periods:
                        series[idx] += 1
            prev = state
    return count, series


# ------------------------------------------------------- Claude copy


def claude_copy(stats, period_label, language="en", tone="dry, witty, deadpan"):
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
        f"You write the copy for a 'Home Assistant Wrapped' page covering "
        f"'{period_label}', a Spotify-Wrapped-style review for a smart "
        "home.\n"
        f"Language: {language}. Tone: {tone}. Short and punchy, "
        "no cringe, no emojis, no exclamation mark spam.\n\n"
        f"Here are the stats for this period as JSON:\n"
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


# --------------------------------------------------------- social export


def export_summary_png(html_path: Path, out_path: Path, width: int, height: int):
    """Screenshot the .summary recap card as a ready-to-post PNG."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("--export-summary needs Playwright: "
                 "pip install 'ha-wrapped[export]' && playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"file://{html_path.resolve()}")
        page.locator(".summary").scroll_into_view_if_needed()
        page.wait_for_timeout(2500)  # let the fade-up animation settle
        page.screenshot(path=str(out_path))
        browser.close()


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
    ap.add_argument("--export-summary", action="store_true",
                     help="also export the recap card as a PNG, ready for "
                          "social media (needs Playwright; "
                          "pip install 'ha-wrapped[export]')")
    ap.add_argument("--summary-size", default="1080x1080",
                     help="WIDTHxHEIGHT for --export-summary "
                          "(default 1080x1080; use 1080x1920 for a 9:16 "
                          "story format)")
    ap.add_argument("--debug", action="store_true",
                     help="dump the raw statistics rows (start/state/sum/"
                          "change) and the computed series per entity, to "
                          "sanity-check the numbers")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    ha_url = cfg["ha_url"]
    token = os.environ.get("HA_TOKEN") or cfg.get("token")
    if not token:
        sys.exit("Set HA_TOKEN or put 'token:' in the config.")

    lang = cfg.get("language", "en")
    nfmt = cfg.get("number_format", "de" if lang == "de" else "en")
    tz = cfg.get("tz_offset", "+01:00")

    period = compute_period(cfg, tz)
    mode, year, month = period["mode"], period["year"], period["month"]
    start, end, full_end = period["start"], period["end"], period["full_end"]
    n_periods = period["n_periods"]
    stat_period = "day" if mode == "monthly" else "month"

    # a period still in progress only has data up to "now"; flag it so the
    # page can say "Jan – Jun" / "1.–13." instead of pretending the empty
    # trailing periods are zeros
    partial = end.astimezone(dt.timezone.utc) < full_end.astimezone(dt.timezone.utc)
    periods_covered = ((end.day if mode == "monthly" else end.month)
                       if partial else n_periods)

    # --- preflight: report what is configured before touching the network
    n_stats = len(cfg.get("statistics", []))
    n_counts = len(cfg.get("counts", []))
    period_id = f"{year}-{month:02d}" if mode == "monthly" else str(year)
    print(f"HA Wrapped {period_id}: {iso(start)} .. {iso(end)}")
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
        result = asyncio.run(fetch_statistics(ha_url, token, ids, start, end, stat_period))
        for s in stat_cfgs:
            rows = result.get(s["entity_id"], [])
            total, series = reduce_stat(rows, s.get("aggregate", "sum"))
            if args.debug:
                agg = s.get("aggregate", "sum")
                print(f"  [debug] {s['entity_id']} (aggregate={agg}, "
                      f"{len(rows)} rows):")
                for r in rows:
                    ts = r.get("start")
                    if isinstance(ts, (int, float)):  # HA sends epoch ms
                        ts = dt.datetime.fromtimestamp(
                            ts / 1000, _tzinfo(tz)).date().isoformat()
                    print(f"    start={ts} state={r.get('state')} "
                          f"sum={r.get('sum')} change={r.get('change')}")
                print(f"    -> raw total={total} series={series}")
            if total is None:
                print(f"  ! no data for {s['entity_id']}")
                entity_status.append({"id": s["entity_id"],
                                      "kind": "statistics",
                                      "status": "no data"})
                continue
            unit_word = "days" if mode == "monthly" else "months"
            entity_status.append({"id": s["entity_id"], "kind": "statistics",
                                  "status": f"ok ({len(rows)} {unit_word})"})
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
        entity_ids = c["entity_id"]
        ids_list = entity_ids if isinstance(entity_ids, list) else [entity_ids]
        ids_label = ", ".join(ids_list)
        print(f"Counting {ids_label} -> '{c['to_state']}' ...")
        try:
            n, series = fetch_count(ha_url, token, ids_list, c["to_state"],
                                    start, end, n_periods,
                                    "day" if mode == "monthly" else "month")
        except Exception as e:  # noqa: BLE001
            print(f"  ! failed: {e}")
            entity_status.append({"id": ids_label, "kind": "counts",
                                  "status": f"error: {e}"})
            continue
        entity_status.append({"id": ids_label, "kind": "counts",
                              "status": f"ok ({n} events)" if n
                              else "no events"})
        scale = c.get("scale", 1.0)
        value = n * scale
        stats_out.append({
            "id": ids_label,
            "label": c["label"],
            "unit": c.get("unit", "x"),
            "value": value,
            "display_value": fmt(value, c.get("decimals", 0), nfmt),
            "series": [v * scale for v in series],
            "footnote": c.get("footnote", ""),
        })
        print(f"  {c['label']}: {n} events")

    if not stats_out:
        sys.exit("No stats collected, nothing to render.")

    # --- partial period: drop the not-yet-happened trailing months/days so
    # their zeros don't read as a real cliff in the charts
    if partial:
        for s in stats_out:
            if s["series"]:
                s["series"] = s["series"][:periods_covered]

    # range label + chart axis labels: bare year / month name for a
    # complete period, "Jan – Jun 2025" / "1.–13. May 2025" while in progress
    month_names = MONTHS.get(lang, MONTHS["en"])
    if mode == "monthly":
        period_labels_full = [str(d) for d in range(1, n_periods + 1)]
        if partial:
            period_label = f"1.–{periods_covered}. {month_names[month - 1]} {year}"
        else:
            period_label = f"{month_names[month - 1]} {year}"
    else:
        period_labels_full = month_names
        period_label = (f"{month_names[0]} – {month_names[periods_covered - 1]} "
                        f"{year}") if partial else str(year)
    period_labels = period_labels_full[:periods_covered]

    # --- copywriting
    print("Generating copy ...")
    copy = claude_copy(stats_out, period_label, lang,
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
               "outro_title": "Bis naechstes Jahr.",
               "summary_title": "Die Bilanz",
               "generated_by": "Erstellt mit Home Assistant"},
        "en": {"scroll": "scroll", "trend": "trend",
               "jan": "Jan", "dec": "Dec", "theme": "light / dark",
               "intro_sub": "What your home has been up to this year.",
               "outro_title": "See you next year.",
               "summary_title": "The Recap",
               "generated_by": "Generated by Home Assistant"},
    }.get(lang, None) or {
        "scroll": "scroll", "trend": "trend", "jan": "Jan", "dec": "Dec",
        "theme": "light / dark",
        "intro_sub": "", "outro_title": f"Wrapped {period_label}",
        "summary_title": "Recap",
        "generated_by": "Generated by Home Assistant"}
    i18n["months"] = month_names

    payload = {
        "year": year,
        "lang": lang,
        "house": cfg.get("house_name", "My Home"),
        "theme": cfg.get("theme", "auto"),
        "period_label": period_label,
        "period": {"mode": mode, "labels": period_labels},
        "i18n": i18n,
        "intro_title": copy.get("intro_title", f"Wrapped {period_label}"),
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
    default_name = (f"ha_wrapped_{year}-{month:02d}.html" if mode == "monthly"
                    else f"ha_wrapped_{year}.html")
    out = Path(args.output or default_name)
    out.write_text(html)

    ok = sum(1 for e in entity_status if e["status"].startswith("ok"))
    print(f"Status: {ok}/{len(entity_status)} entities delivered data, "
          f"AI copy: {'generated' if copy else 'fallback labels'}")
    print(f"Done -> {out.resolve()}")

    if args.export_summary:
        try:
            w, h = (int(x) for x in args.summary_size.lower().split("x", 1))
        except ValueError:
            sys.exit(f"--summary-size must be WIDTHxHEIGHT, "
                     f"got {args.summary_size!r}")
        png_out = out.with_name(out.stem + "_summary.png")
        print(f"Exporting recap card ({w}x{h}) ...")
        export_summary_png(out, png_out, w, h)
        print(f"Done -> {png_out.resolve()}")


if __name__ == "__main__":
    main()
