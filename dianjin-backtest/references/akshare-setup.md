# AkShare 启用说明

## 当前目标

v2 版回测 skill 优先使用 AkShare 作为历史行情源。

## 当前环境现状

- 系统 Python 受 PEP 668 保护，不能直接全局 pip install
- 当前机器缺少 `python3-venv`，所以不能直接创建独立虚拟环境

## 推荐启用方式

优先执行：

```bash
sudo apt update
sudo apt install -y python3.12-venv
python3 -m venv /root/.openclaw/workspace/skills/dianjin-backtest/.venv
/root/.openclaw/workspace/skills/dianjin-backtest/.venv/bin/pip install akshare
```

## 启用后使用方式

```bash
/root/.openclaw/workspace/skills/dianjin-backtest/.venv/bin/python \
  /root/.openclaw/workspace/skills/dianjin-backtest/scripts/fetch_kline_v2.py \
  --code 002027.SZ --start 20240103 --end 20260420 --prefer akshare
```

## 回退逻辑

如果 AkShare 不可用，`fetch_kline_v2.py` 会自动回退到东方财富，再回退到腾讯财经。

如果三者都失败，直接报错，不补假数据。

## 当前实测结论

当前机器已可安装 AkShare，但对其依赖的上游行情站点网络链路仍存在 `RemoteDisconnected` 级别的远端断连。

这意味着：
- skill 结构已升级完成
- AkShare 已可启用
- 但当前机器不应把 AkShare 设为第一优先
- 当前机器实测更稳的方案是 Baostock

所以当前推荐：
- 当前机器优先 Baostock
- AkShare 作为第二优先备用
