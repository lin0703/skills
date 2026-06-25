---
name: generate-ai-daily
description: 生成“AI日报”报纸风长图。用于用户要求生成 AI 日报、AI 新闻海报、报纸风 AI 资讯图、日报长图，或要求把 AI 新闻整理成适合小红书/聊天窗口展示的图片时。适用于从原始新闻链接/摘要出发，整理成中文报纸版式，并用 Puppeteer 渲染 PNG；也适用于修复现有 AI 日报中的占位符、英文文案、重复标题、版式不友好等问题。
---

# Generate AI Daily

把原始 AI 新闻或已有摘要，稳定产出成一张可直接发聊天窗口或社媒的中文“AI日报”长图。

## 默认流程

1. 先拿到新闻原料或用户给的摘要
2. 整理成日报 JSON 结构
3. 检查标题层级，避免“刊名=主标题”重复
4. 生成 HTML
5. 用 Puppeteer 截图成 PNG
6. 目检一遍，再发给用户

## 触发方式

用户出现下面这些说法时，直接用这套 skill：

- 生成 AI 日报
- 做一张 AI 新闻长图
- 把 AI 新闻做成报纸风
- 做成适合聊天窗口 / 小红书发的 AI 日报图
- 修一下这张 AI 日报版式
- TL;DR / Mobile Brief / 英文占位符去掉

## 日报数据结构

优先整理成下面这个 JSON：

```json
{
  "paper_name": "AI日报",
  "issue": "2026-03-26",
  "title": "AI竞争转向高投入硬碰硬",
  "subtitle": "聚焦昨日 AI 产业、模型、芯片与平台动态",
  "summary": "一句导语，直接概括当天核心变化。",
  "highlights": [
    "5 条以内，短句",
    "不要写成流水账"
  ],
  "quote": "一句适合做侧栏引用的话。",
  "sections": [
    {"heading": "大厂动作", "body": "1 段正文"},
    {"heading": "编辑判断", "bullets": ["3 条以内判断"]}
  ],
  "footer_note": "来源：公开报道整理｜生成：AI日报"
}
```

## 硬规则

### 1) 不要重复标题

默认保留：
- `paper_name`: 刊名，例如 `AI日报`
- `title`: 当天真正主标题

禁止把 `title` 再写成 `AI日报`，否则顶部会出现两行同名标题，展示很丑。

### 2) 不要留英文占位符

渲染前必须检查：
- 不要出现 `TL;DR`
- 不要出现 `Mobile Brief`
- 不要出现示例文案、模板残留、英文角标

统一改成自然中文，例如：
- `重点速览`
- `特别整理`

### 3) 适合中文社媒

- 标题要像报纸头条，不要像聊天句子
- highlights 控制在 5 条内
- sections 控制在 2-4 个
- 全中文优先，避免英中混搭的模板感
- 先发聊天窗口时，要保证图片内一眼能看到主标题和重点

### 4) 渲染完成后必须复查

至少检查这几项：
- 顶部是否重复 `AI日报`
- 右栏标题是否仍有英文
- 页脚是否仍有英文角标
- 内容是否有示例占位符没替换
- 图片是否适合直接在聊天窗口查看

## 渲染方法

### HTML 渲染

优先复用现有报纸模板脚本：

- `../newspaper-brief/scripts/render_newspaper.py`

### PNG 截图

优先用 Puppeteer，而不是直接依赖本机 Chrome 参数截图。执行：

```bash
node scripts/render_with_puppeteer.js \
  --html /abs/path/to/file.html \
  --png /abs/path/to/file.png
```

如果本地还没有 Puppeteer，先在临时目录安装，不要污染别的项目：

```bash
npm install puppeteer --prefix /root/.openclaw/workspace/tmp/puppeteer-render
```

## 推荐产物目录

- JSON：`output/newspaper-brief/<slug>.json`
- HTML：`output/newspaper-brief/<slug>.html`
- PNG：`output/newspaper-brief/<slug>.png`

## 参考

- 详细修复清单：`references/checklist.md`
- Puppeteer 截图脚本：`scripts/render_with_puppeteer.js`
