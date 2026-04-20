#!/usr/bin/env python3
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
import urllib.parse
import urllib.request


def normalize_code(raw: str):
    raw = raw.strip().upper()
    if raw.endswith('.SZ'):
        return {'market_id': '0', 'pure': raw[:-3], 'eastmoney': '0.' + raw[:-3], 'tencent': raw[:-3] + '.sz', 'baostock': 'sz.' + raw[:-3]}
    if raw.endswith('.SH'):
        return {'market_id': '1', 'pure': raw[:-3], 'eastmoney': '1.' + raw[:-3], 'tencent': raw[:-3] + '.sh', 'baostock': 'sh.' + raw[:-3]}
    if raw.startswith('6'):
        return {'market_id': '1', 'pure': raw, 'eastmoney': '1.' + raw, 'tencent': raw + '.sh', 'baostock': 'sh.' + raw}
    return {'market_id': '0', 'pure': raw, 'eastmoney': '0.' + raw, 'tencent': raw + '.sz', 'baostock': 'sz.' + raw}


def has_module(name):
    return importlib.util.find_spec(name) is not None


def save_result(result, base_dir):
    out_dir = os.path.join(base_dir, result['code'])
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


def fetch_baostock(code: str, start: str, end: str):
    import baostock as bs
    meta = normalize_code(code)
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f'baostock login failed: {lg.error_msg}')
    try:
        rs = bs.query_history_k_data_plus(meta['baostock'], 'date,code,open,high,low,close,volume', start_date=f'{start[:4]}-{start[4:6]}-{start[6:8]}', end_date=f'{end[:4]}-{end[4:6]}-{end[6:8]}', frequency='d', adjustflag='2')
        if rs.error_code != '0':
            raise RuntimeError(f'baostock query failed: {rs.error_msg}')
        rows = []
        while rs.next():
            date, _, open_p, high_p, low_p, close_p, volume = rs.get_row_data()
            low_v = float(low_p)
            high_v = float(high_p)
            rows.append({'date': date, 'open': float(open_p), 'close': float(close_p), 'high': high_v, 'low': low_v, 'volume': float(volume), 'amount': 0.0, 'amplitude_pct': 0.0 if low_v == 0 else (high_v-low_v)/low_v*100})
        if not rows:
            raise RuntimeError('baostock returned no rows')
        return {'source': 'baostock', 'code': meta['pure'], 'name': meta['pure'], 'rows': rows}
    finally:
        bs.logout()


def fetch_akshare(code: str, start: str, end: str):
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    retry = Retry(total=3, connect=3, read=3, backoff_factor=1, allowed_methods=frozenset(['GET']))
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    old_get = requests.get
    requests.get = session.get
    try:
        import akshare as ak
        meta = normalize_code(code)
        df = ak.stock_zh_a_hist(symbol=meta['pure'], period='daily', start_date=start, end_date=end, adjust='qfq')
    finally:
        requests.get = old_get
    if df is None or df.empty:
        raise RuntimeError('AkShare returned empty dataframe')
    rows = []
    for _, r in df.iterrows():
        low = float(r['最低']); high = float(r['最高'])
        amount = float(r['成交额']) if '成交额' in df.columns else 0.0
        rows.append({'date': str(r['日期'])[:10], 'open': float(r['开盘']), 'close': float(r['收盘']), 'high': high, 'low': low, 'volume': float(r['成交量']), 'amount': amount, 'amplitude_pct': 0.0 if low == 0 else (high-low)/low*100})
    return {'source': 'akshare', 'code': meta['pure'], 'name': meta['pure'], 'rows': rows}


def fetch_eastmoney(code: str, start: str, end: str):
    meta = normalize_code(code)
    url = ('https://push2his.eastmoney.com/api/qt/stock/kline/get' f"?secid={meta['eastmoney']}&fields1=f1,f2,f3,f4,f5,f6" '&fields2=f51,f52,f53,f54,f55,f56,f57,f58' '&klt=101&fqt=1' f'&beg={start}&end={end}')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json,text/plain,*/*', 'Referer': 'https://quote.eastmoney.com/'})
    data = request_json(req)
    payload = data.get('data') or {}
    klines = payload.get('klines') or []
    if not klines:
        raise RuntimeError('Eastmoney returned no kline data')
    rows = []
    for line in klines:
        p = line.split(',')
        rows.append({'date': p[0], 'open': float(p[1]), 'close': float(p[2]), 'high': float(p[3]), 'low': float(p[4]), 'volume': float(p[5]), 'amount': float(p[6]), 'amplitude_pct': float(p[7])})
    return {'source': 'eastmoney', 'code': meta['pure'], 'name': payload.get('name', meta['pure']), 'rows': rows}


def fetch_tencent(code: str, start: str, end: str):
    meta = normalize_code(code)
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=' + urllib.parse.quote(f"{meta['tencent']},day,{start},{end},640,qfq")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/'})
    data = request_json(req)
    payload = (((data.get('data') or {}).get(meta['tencent']) or {}).get('qfqday')) or []
    if not payload:
        raise RuntimeError('Tencent returned no kline data')
    rows = []
    for p in payload:
        low_v = float(p[4]); high_v = float(p[3])
        rows.append({'date': p[0], 'open': float(p[1]), 'close': float(p[2]), 'high': high_v, 'low': low_v, 'volume': float(p[5]), 'amount': 0.0, 'amplitude_pct': 0.0 if low_v == 0 else (high_v-low_v)/low_v*100})
    return {'source': 'tencent', 'code': meta['pure'], 'name': meta['pure'], 'rows': rows}


def fetch(code: str, start: str, end: str, prefer: str):
    order_map = {
        'baostock': [fetch_baostock, fetch_akshare, fetch_eastmoney, fetch_tencent],
        'akshare': [fetch_akshare, fetch_baostock, fetch_eastmoney, fetch_tencent],
        'eastmoney': [fetch_eastmoney, fetch_baostock, fetch_akshare, fetch_tencent],
        'tencent': [fetch_tencent, fetch_baostock, fetch_akshare, fetch_eastmoney],
    }
    errors = []
    for fn in order_map[prefer]:
        if fn is fetch_baostock and not has_module('baostock'):
            errors.append('fetch_baostock: baostock not installed')
            continue
        if fn is fetch_akshare and not has_module('akshare'):
            errors.append('fetch_akshare: akshare not installed')
            continue
        try:
            return fn(code, start, end)
        except Exception as e:
            errors.append(f'{fn.__name__}: {e}')
    raise RuntimeError(' | '.join(errors))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--start', default='20240103')
    ap.add_argument('--end', required=True)
    ap.add_argument('--prefer', default='baostock', choices=['baostock', 'akshare', 'eastmoney', 'tencent'])
    ap.add_argument('--base-dir', default=os.path.expanduser('~/workspace/tushare'))
    args = ap.parse_args()
    result = fetch(args.code, args.start, args.end, args.prefer)
    json_path, csv_path = save_result(result, args.base_dir)
    print(json.dumps({'source': result['source'], 'code': result['code'], 'name': result['name'], 'json': json_path, 'csv': csv_path}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
