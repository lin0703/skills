---
name: dianjin-backtest
description: Backtest the 点金术阶梯建仓 strategy on real A-share daily K-line data and generate reproducible trade logs, operation manuals, and summary metrics. Use when the user asks to build or run a 点金术网格回测/阶梯建仓回测 model, wants historical K-line data fetched from free sources such as 东方财富, wants a per-stock backtest from a start date to an end date, or wants local scripts that strictly execute buys and sells from a generated ladder manual without fake data.
---

# 点金术阶梯建仓回测

这个 skill 负责把“点金术分析 + 阶梯建仓 + 历史回放执行”串成一个可复现的本地回测流程。

## 数据源规则

v2 现在采用 **Baostock 优先** 的多源策略：
- 第一优先：Baostock
- 第二优先：AkShare
- 第三优先：东方财富
- 第四优先：腾讯财经

原因：
- 当前机器实测 Baostock 最稳，已经成功拉到真实历史 K 线
- AkShare 在这台机器上会碰到上游远端断连
- 东方财富、腾讯财经仍保留作兜底
- 能满足从 2024-01-03 起抓历史数据的需求

脚本必须按实际环境探测可用源，不准假装某个源已经可用。

任一源失败时都要保留真实错误，不得伪造“抓取成功”。

## 回测总流程

### 1. 拉取历史数据

按股票代码抓取从 `2024-01-03` 起的前复权日 K 数据，保存到：

`~/workspace/tushare/<股票代码>/daily_k.json`

同时生成标准化 CSV：

`~/workspace/tushare/<股票代码>/daily_k.csv`

标准字段至少包含：
- date
- open
- high
- low
- close
- volume
- amount
- amplitude_pct

### 2. 生成操作手册

基于：
- 用户指定回测日期当天的数据
- 回测日期之前的历史数据
- 资金预算
- 阵型参数
- 点金术阶梯建仓规则

生成操作手册。

操作手册至少包含：
- 股票代码
- 股票名称
- 基准价
- 网格宽度
- 采用阵型
- 每层买入价
- 每层卖出价
- 每层数量
- 每层预算
- 失效条件

### 3. 执行历史回放

从回测日期之后的每日真实 K 线开始，严格按手册执行。

执行原则：
- 先检查卖出，再检查买入
- 买入用当日 `open` 与目标买点中更差的一侧处理跳空
- 卖出用当日 `open` 与目标卖点中更差的一侧处理跳空
- 计算佣金、印花税、滑点
- 每次交易记录日期、操作类型、价格、数量、现金、持仓、累计盈亏

### 4. 回测结束条件

满足任一条件即结束：
- 达到指定结束日期
- 全部仓位清空且用户要求遇清仓即停止

最后输出：
- 期末总资产
- 总收益率
- 已实现盈亏
- 未实现盈亏
- 交易次数
- 完整交易明细

## 关键实现要求

### 严禁假数据

- 只能使用真实历史数据
- 抓取失败时直接报错，不得猜
- 字段缺失时直接报错，不得补造

### 跳空处理

买入：如果当日开盘价低于目标买点，则按开盘价成交。

卖出：如果当日开盘价高于目标卖点，则按开盘价成交。

不要偷懒一律按目标价成交。

### 分红与复权

当前默认使用东方财富前复权日 K，优先让价格序列天然处理大部分分红送转影响。

如果后续需要更严格的现金分红再投或除权单独模拟，再扩展，不在第一版里假做。

### 数量约束

A 股股票按 100 股一手。

每层买入数量必须按整手处理。

如果按设定比例计算后买不起 1 手，不再直接跳过该层，而是默认把该层实际投入上调到至少买入 1 手。

也就是说：
- 能买几手就按向下取整后的整手数执行
- 不足 1 手时，默认补到 1 手
- 输出结果里要反映该层的实际买入股数与实际占用资金，不能假装仍然严格等于原比例预算

## 本 skill 自带脚本

### `scripts/fetch_kline_v2.py`
优先使用 Baostock 抓取日 K。若 Baostock 不可用，则自动回退到 AkShare、东方财富、腾讯财经。

### `scripts/fetch_eastmoney_kline.py`
保留旧版抓数脚本，作为兼容入口。

### `scripts/run_dianjin_backtest.py`
读取历史数据，生成操作手册，执行回测，输出结果。

## 推荐输入参数

- `stock_code`，如 `002027.SZ`
- `initial_capital`
- `backtest_anchor_date`
- `end_date`
- `capital_ratio`，如 `[0.1,0.2,0.3,0.4]` 或 `[0.3,0.2,0.2,0.3]`
- `profit_target`
- `slippage`
- `commission_rate`
- `stamp_duty`
- `clear_on_flat`

## 默认输出模板

对单只股票的回测结果，默认按完整版输出，至少包含：
- 基准价
- 截止日期
- 截止股价
- 总收益率
- 期末总资产
- 已实现盈利
- 当前持仓数量（若有持仓）
- 当前持仓均价（若有持仓）
- 未清仓仓位情况
- 交易次数
- 每笔交易记录
- 每笔交易后的账户总资产

不要只给汇总，不要省略截止股价、持仓均价、持仓数量、账户总资产这些字段。

## 输出文件

每次回测建议写到：

`~/workspace/tushare/<股票代码>/backtests/<anchor_date>_<end_date>/`

至少输出：
- `manual.json`
- `trades.csv`
- `summary.json`

## 语气要求

- 结果直接
- 不吹收益
- 不把回测说成实盘保证
- 明确这是历史条件下的机械回放结果
- 明确标注本次实际使用的数据源
