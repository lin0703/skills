#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request


def normalize_code(raw: str):
    raw = raw.strip().upper()
    if raw.endswith('.SZ'):
        return '0.' + raw[:-3], raw[:-3], raw[:-3] + '.sz'
    if raw.endswith('.SH'):
        return '1.' + raw[:-3], raw[:-3], raw[:-3] + '.sh'
    if raw.startswith('6'):
        return '1.' + raw, raw, raw + '.sh'
    return '0.' + raw, raw, raw + '.sz'


def request_json(req, retries=3):
    last_error = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except Exception as e:
            last_error = e
            time.sleep(1)
    raise last_error


def fetch_eastmoney(code: str, start: str, end: str):
    secid, pure, _ = normalize_code(code)
    url = (
        'https://push2his.eastmoney.com/api/qt/stock/kline/get'
        f'?secid={secid}&fields1=f1,f2,f3,f4,f5,f6'
        '&fields2=f51,f52,f53,f54,f55,f56,f57,f58'
        '&klt=101&fqt=1'
        f'&beg={start}&end={end}'
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json,text/plain,*/*', 'Referer': 'https://quote.eastmoney.com/'})
    data = request_json(req)
    payload = data.get('data') or {}
    klines = payload.get('klines') or []
    if not klines:
        raise RuntimeError('Eastmoney returned no kline data')
    rows = []
    for line in klines:
        parts = line.split(',')
        rows.append({
            'date': parts[0],
            'open': float(parts[1]),
            'close': float(parts[2]),
            'high': float(parts[3]),
            'low': float(parts[4]),
            'volume': float(parts[5]),
            'amount': float(parts[6]),
            'amplitude_pct': float(parts[7]),
        })
    return {'source': 'eastmoney', 'code': pure, 'name': payload.get('name', ''), 'rows': rows}


def fetch_tencent(code: str, start: str, end: str):
    _, pure, tencent_code = normalize_code(code)
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=' + urllib.parse.quote(f'{tencent_code},day,{start},{end},640,qfq')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/'})
    data = request_json(req)
    payload = (((data.get('data') or {}).get(tencent_code) or {}).get('qfqday')) or []
    if not payload:
        raise RuntimeError('Tencent returned no kline data')
    rows = []
    for parts in payload:
        date, open_p, close_p, high_p, low_p, volume = parts[:6]
        low_v = float(low_p)
        high_v = float(high_p)
        amplitude = 0.0 if low_v == 0 else (high_v - low_v) / low_v * 100
        rows.append({
            'date': date,
            'open': float(open_p),
            'close': float(close_p),
            'high': high_v,
            'low': low_v,
            'volume': float(volume),
            'amount': 0.0,
            'amplitude_pct': amplitude,
        })
    return {'source': 'tencent', 'code': pure, 'name': pure, 'rows': rows}


def fetch(code: str, start: str, end: str):
    errors = []
    for fn in (fetch_eastmoney, fetch_tencent):
        try:
            return fn(code, start, end)
        except Exception as e:
            errors.append(f'{fn.__name__}: {e}')
    raise RuntimeError(' | '.join(errors))


def save(result, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, 'daily_k.json')
    csv_path = os.path.join(out_dir, 'daily_k.csv')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'amplitude_pct'])
        writer.writeheader()
        for row in result['rows']:
            writer.writerow(row)
    return json_path, csv_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--start', default='20240103')
    ap.add_argument('--end', required=True)
    ap.add_argument('--base-dir', default=os.path.expanduser('~/workspace/tushare'))
    args = ap.parse_args()

    result = fetch(args.code, args.start, args.end)
    out_dir = os.path.join(args.base_dir, result['code'])
    json_path, csv_path = save(result, out_dir)
    print(json.dumps({'source': result['source'], 'code': result['code'], 'name': result['name'], 'json': json_path, 'csv': csv_path}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
