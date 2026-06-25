#!/usr/bin/env python3
import argparse
import csv
import json
import os
import statistics


def load_rows(csv_path):
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'date': row['date'],
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'amplitude_pct': float(row['amplitude_pct']),
            })
    if not rows:
        raise RuntimeError('No rows loaded from csv')
    return rows


def sma(vals, n):
    if len(vals) < n:
        return sum(vals) / len(vals)
    return sum(vals[-n:]) / n


def weekly_closes(rows):
    out, bucket = [], []
    for r in rows:
        bucket.append(r)
        if len(bucket) == 5:
            out.append(bucket[-1]['close'])
            bucket = []
    if bucket:
        out.append(bucket[-1]['close'])
    return out


def weekly_amplitudes(rows):
    out, bucket = [], []
    for r in rows:
        bucket.append(r)
        if len(bucket) == 5:
            h = max(x['high'] for x in bucket)
            l = min(x['low'] for x in bucket)
            out.append((h - l) / l if l else 0)
            bucket = []
    if bucket:
        h = max(x['high'] for x in bucket)
        l = min(x['low'] for x in bucket)
        out.append((h - l) / l if l else 0)
    return out


def pick_anchor(rows, anchor_date):
    history_rows = [r for r in rows if r['date'] <= anchor_date]
    if not history_rows:
        raise RuntimeError('No history rows found up to anchor date')
    return history_rows[-1], history_rows


def score_stock(rows, anchor_date):
    anchor_row, history_rows = pick_anchor(rows, anchor_date)
    closes = [r['close'] for r in history_rows]
    anchor_close = anchor_row['close']
    ma120 = sma(closes, 120)

    weekly_close_series = weekly_closes(history_rows)
    recent_12w = weekly_close_series[-12:]
    early_4w = recent_12w[:4] if len(recent_12w) >= 4 else recent_12w
    recent_4w = recent_12w[-4:] if len(recent_12w) >= 4 else recent_12w
    trend_ratio = 0.0
    if early_4w and recent_4w:
        trend_ratio = (sum(recent_4w) / len(recent_4w)) / (sum(early_4w) / len(early_4w)) - 1

    low_20 = min(r['low'] for r in history_rows[-20:])
    high_20 = max(r['high'] for r in history_rows[-20:])
    rebound_ratio = (anchor_close - low_20) / (high_20 - low_20) if high_20 > low_20 else 0.5

    future_rows = [r for r in rows if r['date'] > anchor_row['date']]
    future_low = min((r['low'] for r in future_rows), default=anchor_close)
    tier_hits_5 = 0
    for i in range(4):
        buy_price = anchor_close * (1 - i * 0.05)
        if future_low <= buy_price:
            tier_hits_5 += 1

    daily_med = statistics.median(r['amplitude_pct'] / 100 for r in history_rows[-60:])
    weekly_med = statistics.median(weekly_amplitudes(history_rows)[-12:]) if weekly_amplitudes(history_rows) else daily_med

    scores = {}
    details = {}

    if rebound_ratio >= 0.70:
        scores['repair_rebound'] = -3
        details['repair_rebound'] = '回撤后修复强'
    elif rebound_ratio >= 0.40:
        scores['repair_rebound'] = -1
        details['repair_rebound'] = '回撤后修复一般偏强'
    elif rebound_ratio >= 0.20:
        scores['repair_rebound'] = 1
        details['repair_rebound'] = '回撤后修复一般偏弱'
    else:
        scores['repair_rebound'] = 3
        details['repair_rebound'] = '回撤后修复弱'

    if anchor_close > ma120 * 1.03:
        scores['repair_ma120'] = -2
        details['repair_ma120'] = '位于MA120上方'
    elif anchor_close < ma120 * 0.97:
        scores['repair_ma120'] = 2
        details['repair_ma120'] = '位于MA120下方'
    else:
        scores['repair_ma120'] = 0
        details['repair_ma120'] = '位于MA120附近'

    if trend_ratio > 0.05:
        scores['repair_trend12w'] = -2
        details['repair_trend12w'] = '近12周重心上移'
    elif trend_ratio < -0.05:
        scores['repair_trend12w'] = 2
        details['repair_trend12w'] = '近12周重心下移'
    else:
        scores['repair_trend12w'] = 0
        details['repair_trend12w'] = '近12周重心横盘'

    if tier_hits_5 <= 2:
        scores['risk_trigger'] = -2
        details['risk_trigger'] = '5%下不容易快速打满仓'
    elif tier_hits_5 == 3:
        scores['risk_trigger'] = 0
        details['risk_trigger'] = '5%下补仓触发一般'
    else:
        scores['risk_trigger'] = 3
        details['risk_trigger'] = '5%下容易快速打满仓'

    if trend_ratio < -0.05 and weekly_med <= 0.10:
        scores['risk_channel'] = 2
        details['risk_channel'] = '周线偏缓跌通道'
    elif weekly_med >= 0.12 and abs(trend_ratio) < 0.04:
        scores['risk_channel'] = -2
        details['risk_channel'] = '周线偏箱体震荡'
    else:
        scores['risk_channel'] = 0
        details['risk_channel'] = '周线结构中性'

    if trend_ratio < -0.05 and rebound_ratio < 0.3:
        scores['risk_decline_pace'] = 2
        details['risk_decline_pace'] = '慢跌磨底型'
    elif weekly_med >= 0.12 and rebound_ratio >= 0.4:
        scores['risk_decline_pace'] = -1
        details['risk_decline_pace'] = '急跌急拉型'
    else:
        scores['risk_decline_pace'] = 0
        details['risk_decline_pace'] = '下跌节奏普通'

    if daily_med >= 0.04:
        scores['eff_daily_amp'] = -1
        details['eff_daily_amp'] = '日振幅活跃'
    elif daily_med <= 0.02:
        scores['eff_daily_amp'] = 1
        details['eff_daily_amp'] = '日振幅偏钝'
    else:
        scores['eff_daily_amp'] = 0
        details['eff_daily_amp'] = '日振幅中性'

    if weekly_med >= 0.10:
        scores['eff_weekly_amp'] = -1
        details['eff_weekly_amp'] = '周振幅活跃'
    elif weekly_med <= 0.03:
        scores['eff_weekly_amp'] = 1
        details['eff_weekly_amp'] = '周振幅偏钝'
    else:
        scores['eff_weekly_amp'] = 0
        details['eff_weekly_amp'] = '周振幅中性'

    total_score = sum(scores.values())
    if total_score <= -3:
        suggestion = {'grid_width': 0.05, 'label': '5%'}
    elif total_score >= 4:
        suggestion = {'grid_width': 0.10, 'label': '10%'}
    else:
        suggestion = {'grid_width': 0.08, 'label': '8%'}

    return {
        'anchor_date': anchor_row['date'],
        'anchor_close': round(anchor_close, 3),
        'ma120': round(ma120, 3),
        'rebound_ratio': round(rebound_ratio, 3),
        'trend_ratio_12w_pct': round(trend_ratio * 100, 2),
        'daily_amp_median_pct': round(daily_med * 100, 2),
        'weekly_amp_median_pct': round(weekly_med * 100, 2),
        'tier_hits_5pct': tier_hits_5,
        'scores': scores,
        'details': details,
        'total_score': total_score,
        'suggestion': suggestion,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv-path', required=True)
    ap.add_argument('--anchor-date', required=True)
    args = ap.parse_args()
    rows = load_rows(args.csv_path)
    result = score_stock(rows, args.anchor_date)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
