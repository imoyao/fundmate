---
title: 探市页（explore/index.vue）温度区
permalink: /ai-recover
---

> 版本：v1.0（定稿） · 日期：2026-07-29
> 适用范围：`frontend/src/views/explore/index.vue` 温度区（`temperature-grid`）
> 设计依据：多多贝 设计语言 v2.3.3（`frontend/design.md`）、`frontend/src/style/colors.css`
> 关联实现任务：清理死样式 + 修颜色 bug、模板重做、后端去 PE、综合温度合成接口

---

## 1. 背景与目标

当前温度区存在三类问题：

1. **视觉重心缺失**：11 张卡片等权平铺，综合估值与"深度分析入口"长得一样，眼睛无处停留。
2. **信息不明确**：所有 value 均为 22px 粗体，无主次；来源不可见（`tempSource` 死变量从未渲染）。
3. **颜色 bug（硬伤）**：温度标签样式引用了 `colors.css` **未定义**的 `--warm` / `--cold2` / `--ok` / `--mid`，导致"偏高/偏低/放量/缩量/恐惧贪婪"等红绿语义色大面积失效（fallback 成默认色），这是"不够明确"的技术根因。

目标：在**不引入与涨跌色混淆**的前提下，建立"锚点 + 分组 + 底部来源"的信息层级，并让数据来源透明可查。

---

## 2. 信息架构（布局）

### 2.1 一级锚点区（不等宽 2:1:1）

| 卡片 | 占比 | 说明 |
|------|------|------|
| **综合温度**（hero） | 2 | 最大块。当前为"算法开发中"占位，**仍占 hero 位**（用户确认接受空位），未来由后端两源合成填充 |
| **恐惧贪婪指数** | 1 | 标题由"短期情绪"改为"恐惧贪婪指数"；值 + 后端 `label` 直出文字（如"极度恐惧"），不自分级 |
| **自算·股债利差** | 1 | 自研指标，纯股债利差温度，**不显示 PE** |

> 锚点区内部用面积（非位置）表达主次，解决"等权平铺"问题。

### 2.2 二级 · 语义分组

| 分组 | 卡片 |
|------|------|
| 市场情绪 | 韭圈儿中长期、且慢、有知有行 |
| 估值与专项 | 全市场估值（集思录）、可转债（集思录）、指数快照 |
| 流动性 | 成交额（东方财富） |

每个分组一个轻容器 + 小标题（`--text-label` 级），组内卡片字号收敛。

### 2.3 底部常驻静态来源条

整页底部一条来源列表（韭圈儿 / 集思录 / 且慢 / 有知有行 / 东方财富 / 自算·股债利差），**每个可点击跳官网**（用现有 `links`）。替代此前"逐卡 hover chip"方案，减少 clutter。

> "深度分析"入口保留，但归入分组或独立轻量模块，不再伪装成温度卡。

---

## 3. 字号梯度（锚点 vs 分组）

严格套用 `design.md` 字阶，建立三档：

| 层级 | Token | 用途 | 示例 |
|------|-------|------|------|
| 一级锚点值 | `--text-display`(32) / `--text-title`(24) | 综合温度、恐惧贪婪、自算值 | 综合温度 hero 用 32px |
| 二级卡片值 | `--text-title`(24) / `--text-heading`(20) | 分组卡片主数值 | 20–24px |
| 三级副信息 | `--text-small`(14) / `--text-label`(13) | 副标题、来源、说明 | 分组小标题 13px、弱化色 |

数字强制 `font-variant-numeric: tabular-nums` + 等宽字体（设计语言硬性要求）。

---

## 4. 间距与圆角

- 卡片内边距：`--space-standard`（24px）大卡 / `--space-compact`（16px）密排分组
- 栅格间距：`--space-3`（12px）
- 圆角：卡片 `--radius-md`（12px）/ 大卡 `--radius-lg`（16px）；标签/来源 chip 用 `--radius-pill`
- 阴影：`--shadow-raised`；hover `--shadow-float`

---

## 5. 配色规范（核心红线）

### 5.1 温度三色（新增专用 token，隔离涨跌语义）

为彻底修复 undefined 变量 bug 且不与"红涨绿跌"混淆，**新增温度专用 token**（写入 `colors.css`），替换所有 `--warm/--cold2/--ok/--mid`：

```css
--temp-low:   #4F9D69;  /* 低温 · 机会区（绿，取自 --tag-sage-green 系） */
--temp-mid:   var(--tag-warm-sand);  /* 适中 · 平稳（暖沙金，用户确认） */
--temp-high:  #D9534F;  /* 高温 · 谨慎区（红，独立于品牌涨色） */
--temp-low-bg:   rgba(79,157,105,0.14);
--temp-mid-bg:   rgba(212,200,152,0.20);
--temp-high-bg:  rgba(217,83,79,0.14);
```

> 注意：`--temp-high` 用独立红（非 `--color-rise` 品牌涨色），避免用户把"高温=红"误读成"行情好=该买"。
> 禁止在温度区直接调用 `--color-rise` / `--color-fall`（那是涨跌语义）。

### 5.2 标签/文字色映射

- 温度 `label-high` / `level-high` / `fear-high` / `vol-high` / `tag-high` → `--temp-high` + `--temp-high-bg`
- `*-mid` → `--temp-mid` + `--temp-mid-bg`
- `*-low` / `fear-low` / `vol-low` → `--temp-low` + `--temp-low-bg`

### 5.3 图例 + 免责声明（必加）

页面底部固定一行图例：
`温度色：🟢 绿=低温·机会区　🔴 红=高温·谨慎区　🟡 金=适中·平稳`
并标注：**"温度色与观察列表'红涨绿跌'相互独立；本页仅供参考，不构成投资建议。"**

---

## 6. 组件拆分

```plain
temperature-grid
├─ temp-card temp-card-main      (综合温度 · hero · 2 份宽 · 占位)
├─ temp-card temp-card-anchor    (恐惧贪婪指数 · 1 份宽)
├─ temp-card temp-card-anchor    (自算·股债利差 · 1 份宽)
├─ group (市场情绪)
│   ├─ temp-card (韭圈儿中长期)
│   ├─ temp-card (且慢)
│   └─ temp-card (有知有行)
├─ group (估值与专项)
│   ├─ temp-card (全市场估值·集思录)
│   ├─ temp-card (可转债·集思录)
│   └─ temp-card (指数快照)
└─ group (流动性)
    └─ temp-card (成交额·东方财富)

footer (常驻来源条 + 图例 + 免责)
```

卡片结构统一：`header(title + 可选 badge) → body(value + label/tag) → footer(来源/副信息)`。

---

## 7. 前端实现要点（B 阶段）

1. **清理死样式**：删除 `<style>` 中上版残留 `.hero-section` / `.market-overview` / `.valuation-card` / `.snapshot-row` / `.tabs-wrapper` / `.temp-sources` / `.fear-greed` / `.conversion-section` 等（模板已不使用），及死变量 `tempSource`。
2. **修颜色 bug**：所有 `var(--warm)` 等改为 `var(--temp-*)`；`label-low/mid/high`、`level-*`、`fear-*`、`vol-*`、`tag-*` 全部映射到新 token。
3. **模板重做**：按 §2 的 2:1:1 锚点 + 语义分组 + 底部来源条重写 `temperature-grid` 与 `footer`。
4. **恐惧贪婪**：标题改"恐惧贪婪指数"，文字取 `fearData.label` 直出，配色按 `getFearClass`（恐惧类→low / 贪婪类→high / 中性→mid）。
5. **来源条**：用 `data.links` 渲染可点击 chip。

---

## 8. 后端改造点（B 阶段）

### 8.1 `SelfCalcFetcher` 去 PE（文件：`backend/app/services/thermometer/fetchers.py`）

- 对外字段去掉 `pe`（不再暴露 PE 给前端）；保留内部 `spread`（股债利差）计算。
- 对外仅输出：`spread_pct`（利差百分点）、`percent`（利差历史分位）、`level`（偏低/正常/偏高）、`y10`、`cpi`。
- 前端"自算·股债利差"卡只展示 `spread_pct` / `percent` + `level`，不出现 "PE"。
- 内部 `ey = 1/pe` 仍用于盈利收益率（这是股债利差的标准算法），只是**不对外暴露 PE 数值**。

### 8.2 新增"综合温度"两源合成（文件：`service.py` + `views.py`）

综合温度 = 加权参考（第三方）× 权重 + 自算·股债利差 × 权重，建议：

| 源 | 权重 | 取值 |
|----|------|------|
| 韭圈儿恐惧贪婪 `jiucaishuo_fear.value` | 0.25 | 0–100 归一 |
| 韭圈儿中长期 `jiucaishuo_medium.value` | 0.15 | ℃ 归一 |
| 且慢 `qieman.value` | 0.15 | 温度 % |
| 有知有行 `youzhiyouxing.value` | 0.15 | 温度 ° |
| 集思录估值 `jisilu_indicator.median_pe_temperature` | 0.10 | 温度 % |
| 东财成交额 `eastmoney_volume`（量价维度，单独加权） | 0.05 | 放量/缩量归一 |
| **自算·股债利差 `self_calc.percent`** | 0.15 | 分位 % |

- 在 `TemperatureService.get_overview()` 中新增 `composites.composite_temperature = { value, level, composed_of: [...] }`。
- `level` 复用 `label_temp` 风格（偏高/适中/偏低）映射到 `--temp-*`。
- 任一源缺失时按剩余源重新归一权重（容错）。
- 接口契约补充到 `frontend/src/api/temperature.ts` 的 `TemperatureOverviewResponse`。

---

## 9. 合规与可访问性

- 温度色与观察列表涨跌色**物理隔离**（不同 token + 图例说明），杜绝"红=涨=该买"误读。
- 颜色不作为唯一信息载体：温度标签同时带文字（偏低/适中/偏高、极度恐惧……），不靠纯色传达。
- 所有新增/修改颜色变量须通过 axe-core / Lighthouse 对比度回归（设计语言 Do's & Don'ts）。
- 底部免责声明常驻。

---

## 10. 验收清单

- [ ] 11 卡不再是等权平铺；综合温度明显最大（2 份宽）
- [ ] 恐惧贪婪卡标题正确、文字取后端 label、颜色正确
- [ ] 自算卡不出现 "PE" 字样，显示股债利差
- [ ] 颜色全生效（无 undefined 变量）；低温绿/高温红/适中金
- [ ] 底部来源条常驻、可点击跳官网
- [ ] 图例 + 免责声明可见
- [ ] 死样式 / 死变量已清理（grep `--warm` / `tempSource` 为空）
- [ ] 后端 `self_calc` 不再返回 `pe`；`composite_temperature` 接口可用
- [ ] 类型检查 + dev server 通过，温度区视觉与交互符合本方案
