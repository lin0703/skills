#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

APP_ID = "cli_a920f046e1b9dcca"
SECRET_FILE = Path("/root/.openclaw/credentials/lark.secrets.json")
SPREADSHEET_TOKEN = "WMplsfFrDhFSOht8uidcsCGtnMg"
SHEET_ID = "ae24d9"
SHEET_RANGE = f"{SHEET_ID}!A1:P200"
WRITE_RANGE = f"{SHEET_ID}!A2:P200"
TZ = ZoneInfo("Asia/Shanghai")
UA = "Mozilla/5.0"


def load_app_secret() -> str:
    data = json.loads(SECRET_FILE.read_text())
    secret = data.get("lark", {}).get("appSecret")
    if not secret:
        raise RuntimeError("missing appSecret in lark.secrets.json")
    return secret


def post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_tenant_access_token() -> str:
    payload = {"app_id": APP_ID, "app_secret": load_app_secret()}
    data = post_json("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", payload)
    if data.get("code") != 0:
        raise RuntimeError(f"tenant token error: {data}")
    return data["tenant_access_token"]


def sheet_read(token: str) -> list[list]:
    url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values/{}".format(
        SPREADSHEET_TOKEN,
        urllib.parse.quote(SHEET_RANGE, safe="!:")
    )
    data = get_json(url, headers={"Authorization": f"Bearer {token}"})
    if data.get("code") != 0:
        raise RuntimeError(f"sheet read error: {data}")
    return data["data"]["valueRange"].get("values", [])


def sheet_write(token: str, values: list[list]) -> None:
    body = {"valueRange": {"range": WRITE_RANGE, "values": values}}
    url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values".format(SPREADSHEET_TOKEN)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"sheet write error: {data}")


def quote_parts(code: str) -> list[str]:
    symbol = ("sh" if code.startswith(("6", "688")) else "sz") + code
    url = f"https://qt.gtimg.cn/q={symbol}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("gbk", errors="ignore")
    if '="' not in text:
        raise RuntimeError(f"quote error for {code}: {text[:200]}")
    payload = text.split('="', 1)[1].rsplit('"', 1)[0]
    parts = payload.split('~')
    if len(parts) < 4 or not parts[3]:
        raise RuntimeError(f"quote parse error for {code}: {text[:200]}")
    return parts


def quote(code: str) -> float:
    return float(quote_parts(code)[3])


def recent_daily_closes(code: str, count: int = 5) -> list[float]:
    symbol = ("sh" if code.startswith(("6", "688")) else "sz") + code
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{max(count + 5, 20)},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    code_data = data.get("data", {}).get(symbol, {})
    klines = code_data.get("qfqday") or code_data.get("day") or []
    closes = []
    for item in klines:
        if len(item) >= 3:
            closes.append(float(item[2]))
    if not closes:
        raise RuntimeError(f"kline parse error for {code}: {str(data)[:200]}")
    return closes[-count:]


def as_float(v):
    if v in (None, ""):
        return None
    return float(v)


def fmt_num(v, digits=10):
    if v in (None, ""):
        return ""
    return round(v, digits)


def fmt_pct(v, digits=10):
    if v in (None, ""):
        return ""
    return round(v, digits)


def build_rows(values: list[list]) -> list[dict]:
    rows = []
    for row in values[1:]:
        if len(row) < 3 or not row[2]:
            continue
        row = list(row) + [""] * (16 - len(row))

        def clean_recent(v):
            if v in (None, ""):
                return ""
            s = str(v)
            if "/" in s and ":" in s:
                return ""
            return v

        rows.append({
            "name": row[1],
            "code": str(row[2]).zfill(6),
            "buy": row[4],
            "sell": row[5],
            "trigger_time": row[10],
            "recent": clean_recent(row[11]),
        })
    return rows


def main():
    now = datetime.now(TZ).strftime("%Y/%-m/%-d %H:%M")
    token = get_tenant_access_token()
    values = sheet_read(token)
    rows = build_rows(values)
    result = []
    for item in rows:
        parts = quote_parts(item["code"])
        price = float(parts[3])
        prev_close = float(parts[4]) if len(parts) > 4 and parts[4] else None
        daily_closes = recent_daily_closes(item["code"], 5)
        buy = as_float(item["buy"])
        sell = as_float(item["sell"])
        rel = ((price - buy) / buy) if buy else None
        remain = ((sell - price) / price) if sell else None
        prev_day_change = ((price - prev_close) / prev_close) if prev_close else None
        five_day_change = ((price - daily_closes[0]) / daily_closes[0]) if len(daily_closes) >= 5 and daily_closes[0] else None
        ma5 = sum(daily_closes) / len(daily_closes) if daily_closes else None
        can_buy = "是" if buy is not None and price <= buy else "否"
        triggered = "触发" if can_buy == "是" else "未触发"
        trigger_time = item["trigger_time"] if triggered == "触发" else ""
        if triggered == "触发" and not trigger_time:
            trigger_time = now
        result.append({
            "name": item["name"],
            "code": item["code"],
            "price": price,
            "buy": item["buy"],
            "sell": item["sell"],
            "rel": rel,
            "remain": remain,
            "can_buy": can_buy,
            "triggered": triggered,
            "trigger_time": trigger_time,
            "recent": price,
            "ma5": ma5,
            "prev_day_change": prev_day_change,
            "five_day_change": five_day_change,
            "updated_at": now,
        })
        time.sleep(0.15)

    result.sort(key=lambda x: (999 if x["rel"] is None else x["rel"], x["code"]))

    out = []
    for idx, r in enumerate(result, start=1):
        out.append([
            idx,
            r["name"],
            r["code"],
            r["price"],
            r["buy"],
            r["sell"],
            fmt_pct(r["rel"]),
            fmt_pct(r["remain"]),
            r["can_buy"],
            r["triggered"],
            r["trigger_time"],
            r["recent"],
            fmt_num(r["ma5"], 2),
            fmt_pct(r["prev_day_change"]),
            fmt_pct(r["five_day_change"]),
            r["updated_at"],
        ])

    sheet_write(token, out)
    print(json.dumps({"ok": True, "rows": len(out), "updated_at": now}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
