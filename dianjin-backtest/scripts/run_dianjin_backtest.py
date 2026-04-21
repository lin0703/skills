#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime


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
                'volume': float(row['volume']),
                'amount': float(row['amount']),
                'amplitude_pct': float(row['amplitude_pct']),
            })
    if not rows:
        raise RuntimeError('No rows loaded from csv')
    return rows


def median(nums):
    seq = sorted(nums)
    n = len(seq)
    if n == 0:
        raise RuntimeError('Cannot compute median of empty sequence')
    mid = n // 2
    if n % 2:
        return seq[mid]
    return (seq[mid - 1] + seq[mid]) / 2


def build_manual(code, name, anchor_row, history_rows, initial_capital, capital_ratio, profit_target):
    daily_amplitudes = [r['amplitude_pct'] / 100.0 for r in history_rows[-60:]] or [anchor_row['amplitude_pct'] / 100.0]
    weekly_amplitudes = []
    weekly_changes = []
    week_bucket = []
    for row in history_rows:
        week_bucket.append(row)
        if len(week_bucket) == 5:
            high = max(x['high'] for x in week_bucket)
            low = min(x['low'] for x in week_bucket)
            first_close = week_bucket[0]['close']
            last_close = week_bucket[-1]['close']
            if low > 0 and first_close > 0:
                weekly_amplitudes.append((high - low) / low)
                weekly_changes.append(abs(last_close - first_close) / first_close)
            week_bucket = []
    if not weekly_amplitudes:
        weekly_amplitudes = daily_amplitudes
    if not weekly_changes:
        weekly_changes = [abs(anchor_row['close'] - history_rows[max(0, len(history_rows)-2)]['close']) / history_rows[max(0, len(history_rows)-2)]['close']] if len(history_rows) > 1 else [0.03]

    grid_width = max(0.03, min(0.15, (median(daily_amplitudes) * 0.35 + median(weekly_amplitudes) * 0.4 + median(weekly_changes) * 0.25)))
    base_price = anchor_row['close']
    tiers = []
    for idx, ratio in enumerate(capital_ratio):
        buy_price = round(base_price * (1 - idx * grid_width), 3)
        sell_price = round(buy_price * (1 + profit_target), 3)
        budget = initial_capital * ratio
        lots = math.floor(budget / (buy_price * 100))
        if lots < 1:
            lots = 1
        tiers.append({
            'tier': idx + 1,
            'ratio': ratio,
            'budget': round(budget, 2),
            'buy_price': buy_price,
            'sell_price': sell_price,
            'lots': lots,
            'shares': lots * 100,
        })
    return {
        'stock_code': code,
        'stock_name': name,
        'anchor_date': anchor_row['date'],
        'base_price': base_price,
        'grid_width': round(grid_width, 6),
        'profit_target': profit_target,
        'capital_ratio': capital_ratio,
        'tiers': tiers,
        'invalid_if': '跌破最后一层后停止机械补仓，回到基本面复核'
    }


def run_backtest(rows, manual, initial_capital, end_date, commission_rate, stamp_duty, slippage, clear_on_flat):
    available_cash = initial_capital
    realized_profit = 0.0
    holdings = {}
    trades = []
    anchor_date = manual['anchor_date']
    active_rows = [r for r in rows if r['date'] > anchor_date and r['date'] <= end_date]

    def holding_value(close_price):
        return sum(h['shares'] * close_price for h in holdings.values())

    for row in active_rows:
        for tier in manual['tiers']:
            key = tier['tier']
            h = holdings.get(key)
            if not h:
                continue
            target_sell = h['target_sell']
            if row['high'] >= target_sell:
                sell_price = max(target_sell, row['open'])
                shares = h['shares']
                gross = sell_price * shares
                commission = max(5.0, gross * commission_rate)
                tax = gross * stamp_duty
                net = gross - commission - tax - slippage * shares
                available_cash += net
                cost_basis = h['buy_cost_total']
                profit = net - cost_basis
                realized_profit += profit
                del holdings[key]
                position_value_after = holding_value(row['close'])
                total_assets_after = available_cash + position_value_after
                trades.append({
                    'date': row['date'],
                    'action': 'SELL',
                    'tier': key,
                    'price': round(sell_price, 4),
                    'shares': shares,
                    'cash_after': round(available_cash, 2),
                    'position_value_after': round(position_value_after, 2),
                    'total_assets_after': round(total_assets_after, 2),
                    'realized_profit': round(realized_profit, 2),
                    'trade_profit': round(profit, 2),
                })

        for tier in manual['tiers']:
            key = tier['tier']
            if key in holdings or tier['lots'] <= 0:
                continue
            buy_target = tier['buy_price']
            if row['low'] <= buy_target:
                buy_price = min(buy_target, row['open'])
                shares = tier['shares']
                gross = buy_price * shares
                commission = max(5.0, gross * commission_rate)
                total_cost = gross + commission + slippage * shares
                if available_cash >= total_cost:
                    available_cash -= total_cost
                    holdings[key] = {
                        'buy_price': buy_price,
                        'shares': shares,
                        'target_sell': tier['sell_price'],
                        'buy_cost_total': total_cost,
                    }
                    position_value_after = holding_value(row['close'])
                    total_assets_after = available_cash + position_value_after
                    trades.append({
                        'date': row['date'],
                        'action': 'BUY',
                        'tier': key,
                        'price': round(buy_price, 4),
                        'shares': shares,
                        'cash_after': round(available_cash, 2),
                        'position_value_after': round(position_value_after, 2),
                        'total_assets_after': round(total_assets_after, 2),
                        'realized_profit': round(realized_profit, 2),
                        'trade_profit': '',
                    })

        if clear_on_flat and not holdings:
            break

    final_row = active_rows[-1] if active_rows else rows[-1]
    stock_value = sum(h['shares'] * final_row['close'] for h in holdings.values())
    total_assets = available_cash + stock_value
    return {
        'summary': {
            'final_date': final_row['date'],
            'final_close': final_row['close'],
            'available_cash': round(available_cash, 2),
            'stock_value': round(stock_value, 2),
            'total_assets': round(total_assets, 2),
            'total_return_pct': round((total_assets - initial_capital) / initial_capital * 100, 4),
            'realized_profit': round(realized_profit, 2),
            'open_positions': len(holdings),
            'trade_count': len(trades),
        },
        'trades': trades,
    }


def write_outputs(base_dir, manual, result):
    out_dir = os.path.join(base_dir, 'backtests', f"{manual['anchor_date']}_{result['summary']['final_date']}")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'manual.json'), 'w', encoding='utf-8') as f:
        json.dump(manual, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(result['summary'], f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, 'trades.csv'), 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'action', 'tier', 'price', 'shares', 'cash_after', 'position_value_after', 'total_assets_after', 'realized_profit', 'trade_profit'])
        writer.writeheader()
        for trade in result['trades']:
            writer.writerow(trade)
    return out_dir


def parse_ratio(text):
    data = json.loads(text)
    if abs(sum(data) - 1.0) > 1e-6:
        raise RuntimeError('capital_ratio must sum to 1.0')
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--name', default='')
    ap.add_argument('--csv-path', required=True)
    ap.add_argument('--anchor-date', required=True)
    ap.add_argument('--end-date', required=True)
    ap.add_argument('--initial-capital', type=float, default=50000)
    ap.add_argument('--capital-ratio', default='[0.1,0.2,0.3,0.4]')
    ap.add_argument('--profit-target', type=float, default=0.06)
    ap.add_argument('--commission-rate', type=float, default=0.0003)
    ap.add_argument('--stamp-duty', type=float, default=0.0005)
    ap.add_argument('--slippage', type=float, default=0.01)
    ap.add_argument('--clear-on-flat', action='store_true')
    ap.add_argument('--base-dir', default=os.path.expanduser('~/workspace/tushare'))
    args = ap.parse_args()

    rows = load_rows(args.csv_path)
    ratio = parse_ratio(args.capital_ratio)
    history_rows = [r for r in rows if r['date'] <= args.anchor_date]
    if not history_rows:
        raise RuntimeError('No history rows found up to anchor date')
    anchor_row = history_rows[-1]
    manual = build_manual(args.code, args.name or args.code, anchor_row, history_rows, args.initial_capital, ratio, args.profit_target)
    result = run_backtest(rows, manual, args.initial_capital, args.end_date, args.commission_rate, args.stamp_duty, args.slippage, args.clear_on_flat)
    out_dir = write_outputs(os.path.join(args.base_dir, args.code.replace('.SZ','').replace('.SH','')), manual, result)
    print(json.dumps({'out_dir': out_dir, 'manual': manual, 'summary': result['summary']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
