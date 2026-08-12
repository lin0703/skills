---
name: eyu-gupiao-genzong
description: 跟踪“鳄鱼股票跟踪”飞书表格中的 A 股股票，定时拉取最新价，按相对买入价涨跌幅排序并写回最新表格格式。用户提到“鳄鱼股票跟踪”、“股票跟踪表自动刷新”、“每5分钟更新股价”、“写回飞书表格”、“按买入价涨跌幅排序”时使用。
---

# 鳄鱼股票跟踪

## 概览

用这个 skill 维护固定的飞书股票跟踪表，自动完成 4 件事：读取表格、拉取最新行情、计算关键指标、按排序结果写回表格。

当前默认目标：
- 飞书表格：`https://lcn0b63y6ed6.feishu.cn/wiki/Zmllw42m9inZ5bkVUqecj7bCn0f`
- 脚本：`scripts/stock_sheet_sync.py`
- 日志：`/home/ubuntu/.hermes/state/stock_sheet_sync.log`

## 工作流

### 1. 先确认是不是这个固定表

如果用户说的是“鳄鱼股票跟踪”这张表，直接按本 skill 处理。
如果用户换了另一张表，先改脚本里的常量，再执行或重新配置 crontab。

### 2. 手动刷新时怎么做

直接运行：

```bash
/usr/bin/python3 /home/ubuntu/.hermes/skills/lin0703-skills/eyu-gupiao-genzong/scripts/stock_sheet_sync.py
```

成功后会把表格按“相对买入价涨跌幅”从低到高重排，并更新：
- 优先级
- 当前价
- 相对买入价涨跌幅
- 距离目标价剩余涨幅
- 是否还能买入
- 是否触发买点提醒
- 触发时间
- 最近价
- MA5
- 上个交易日涨跌幅
- 近五个交易日涨跌幅
- 更新时间

注意：
- 脚本写入的是原始数值。
- 百分比显示、保留几位小数、红涨绿跌都由飞书表格格式控制。

### 3. 定时运行时怎么做

推荐用系统 crontab，不要用会唤醒 agent 的 cron。

当前推荐配置，只在 A 股交易时段执行：

```cron
*/5 9-11 * * 1-5 /usr/bin/python3 /home/ubuntu/.hermes/skills/lin0703-skills/eyu-gupiao-genzong/scripts/stock_sheet_sync.py >> /home/ubuntu/.hermes/state/stock_sheet_sync.log 2>&1
*/5 13-14 * * 1-5 /usr/bin/python3 /home/ubuntu/.hermes/skills/lin0703-skills/eyu-gupiao-genzong/scripts/stock_sheet_sync.py >> /home/ubuntu/.hermes/state/stock_sheet_sync.log 2>&1
0 15 * * 1-5 /usr/bin/python3 /home/ubuntu/.hermes/skills/lin0703-skills/eyu-gupiao-genzong/scripts/stock_sheet_sync.py >> /home/ubuntu/.hermes/state/stock_sheet_sync.log 2>&1
```

### 4. 行情源规则

默认使用腾讯行情 `qt.gtimg.cn`。
原因：这台机子上东方财富 `push2` 源出现过 TLS/握手超时，腾讯源更稳。

如果腾讯源挂了，再考虑切换数据源，不要先改回东财。

### 5. 表格字段约定

脚本默认读取和写回这几列顺序，不要随便改列结构：

- A 优先级
- B 股票
- C 代码
- D 当前价
- E 目标买入价
- F 目标卖出价
- G 相对买入价涨跌幅
- H 距离目标价剩余涨幅
- I 是否还能买入
- J 是否触发买点提醒
- K 触发时间
- L 最近价
- M MA5
- N 上个交易日涨跌幅
- O 近五个交易日涨跌幅
- P 更新时间

说明：
- 当前表实际使用到 P 列，Q-S 目前为空。
- “最近价”是单列滚动观察位，不再使用最近价1/2/3三列。
- 百分比相关列一律按原始数值写入，由表格自身格式负责显示百分比、保留小数位、红涨绿跌。
- 如果显示格式丢了，先检查飞书表格格式，不要先改脚本输出。

### 6. 触发逻辑

- 相对买入价涨跌幅 = `(当前价 - 目标买入价) / 目标买入价`
- 距离目标价剩余涨幅 = `(目标卖出价 - 当前价) / 当前价`
- 上个交易日涨跌幅 = `(当前价 - 昨收) / 昨收`
- 近五个交易日涨跌幅 = `(当前价 - 5 个交易日前收盘价) / 5 个交易日前收盘价`
- MA5 = 最近 5 个交易日收盘价均值
- 当前价 `<=` 目标买入价：
  - 是否还能买入 = `是`
  - 是否触发买点提醒 = `触发`
- 当前价 `>` 目标买入价：
  - 是否还能买入 = `否`
  - 是否触发买点提醒 = `未触发`

首次触发时，如果原来没有触发时间，就写入当前时间。

## 修改点

如果用户要扩展这个 skill，优先改这里：
- 表格 token / sheet id / 读写范围：改脚本顶部常量
- 行情源：改 `quote_parts()` 和 `recent_daily_closes()`
- 排序逻辑：改 `result.sort(...)`
- 输出格式：改 `fmt_num()` / `fmt_pct()`，但优先保持百分比列输出为原始数值
- 定时频率：改 crontab，不要把调度逻辑写死在脚本里

## resources

### scripts/
- `stock_sheet_sync.py`：低 token 消耗的飞书股票表同步脚本（已按最新表格格式适配）
