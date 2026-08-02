# 温度模块 + 投资概览页：建议评估与开发排期

> 创建：2026-08-02
> 背景：用户就「投资概览（welcome）/ 探市 / 温度计」三层架构与代码优化给了若干建议，要求先评估合理性，再区分「现在能做」与「需后端接口」，并对后者排期。
> 范围澄清（2026-08-02 更新）：用户最终明确——**核心优化对象是「投资概览页」（`frontend/src/views/welcome/index.vue`，即最初两张对比截图所在页），不是探市 / 温度计子页面**。下文 §A 为概览页 6 项建议的逐项评估；§B 为温度模块（计算后移 / 文案归集）评估。

---

## A. 投资概览页（welcome）6 项建议逐项评估

> 核实方式：通读 `welcome/index.vue` 当前实现 + 全局搜索 FAB/悬浮按钮（0 命中）。

| # | 建议 | 评估 | 结论 | 工作量 |
|---|---|---|---|---|
| 1 | 短/中/长期温度放综合卡下方 | 合理；但后端 `composite_temperature` 是**单值，无短中长分解** | 需后端（B1） | 中 |
| 2 | 统一 12 列栅格、左栏对齐 8 列 | 第一/三排已是 12 列 `col-span-8`；**第四排（财务晴雨表+心理账户）是 `flex` 未统一** | ✅ 今日已修 | 小 |
| 3 | SectionHeader 操作槽标准化 | `SectionHeader` 已存在（`--space-3` + `min-height:32px` 保证等高占位）；但 welcome 页**未使用**，手写 h3+分散操作 | ✅ 今日已接入第四排 | 小 |
| 4 | 心理账户补白底外框 | 当前心理账户**已有** `--bg-card`+圆角+阴影，与财务晴雨表基本对称 | 已满足 | — |
| 5 | 可转债温度缺状态标签 | 概览页第二排「市场温度」卡用 `TemperatureGaugeCard` 已带 `level` 徽章；该建议针对的是**温度计子页**（非概览页） | 错位，归子页 | — |
| 6 | 心理账户颜色歧义 + FAB 压页脚 | 颜色歧义属实（静态数据用 `--tag-caramel`/`--tag-sage-green` 绿）；**FAB 全局搜索 0 命中，不存在** | 颜色✅今日已修；FAB 误报 | 小 |

### A. 今日已完成（welcome/index.vue，2026-08-02）
- 第四排改为 `lg:grid-cols-12`，财务晴雨表 `col-span-8`、心理账户 `col-span-4`，与其他排对齐（问题 2）。
- 财务晴雨表 / 心理账户标题接入 `SectionHeader`（含 info tooltip），统一操作槽（问题 3）。
- 心理账户进度条改为品牌红单色 + 不同透明度（`--brand-700/500/300`），消除「绿=亏损」歧义（问题 6 颜色部分）。
- 移除未使用的 `Plus` / `IconifyIconOffline` 导入；lint / 类型检查无新增错误。

### A. 仍需处理
- **短/中/长期温度**（问题 1）：等 §B 的 B1 后端返回短中长分解后，在概览页综合卡下方加一行小字并列（切忌图2 那种三张大卡片平铺）。
- **FAB 压页脚**（问题 6）：经核实前端无 FAB，属误报；若未来新增 FAB，需加触底隐藏逻辑（滚动监听 / 安全区）。

---

## B. 温度模块（计算后移 / 文案归集）评估

## 0. 调研事实（评估依据）

- 后端 `domains/temperature/views.py` **已是薄视图**，仅委托 `services/thermometer/service.py`。
- 重计算（综合温度权重合成 + level 推导）**已在后端** `_compute_composite_temperature` 完成。
- 但：
  - `jisilu_indicator` 的 `median_pb_temperature` / `median_pe_temperature` **只回数字，无 level** → 前端 `explore` 用 `inferValuationLevel` 自己算档位。
  - `composites.composite_temperature` 是**单值**，无「短 / 中 / 长期」分解。
- 前端散落的计算 / 派生：
  - `store/modules/temperature.ts`：`cbLevel`（可转债→档位）、`buildOpportunities`（生成「市场机会清单」desc/tone 文案）、`tempTone`、`indices`（脆弱的 `name.includes` 字符串匹配）。
  - `views/explore/index.vue`：`inferValuationLevel`（PB/PE→偏低/适中/偏高）、`progressColor`（值→色）。

### 阈值前后端不一致（关键 bug，已核实）

| 位置 | 偏低 | 适中/正常 | 偏高 |
|---|---|---|---|
| 后端 `constants.py:55` | ≤40 | 40–70 | >70 |
| 后端 `fetchers.py:639` | 偏低 | **正常**（非「适中」） | 偏高 |
| 前端 `explore.inferValuationLevel` | **<30** | 30–70 | >70 |
| 前端 `explore.progressColor` | <40 | 40–60 | >60 |
| 前端 `store.cbLevel` | 极冷≤15 / 偏冷≤35 | 适中≤65 | 偏热≤85 / 极热 |

结论：档位语义在前后端、甚至后端内部都不一致，必须先统一为单一权威来源。

## 1. 逐条评估

### 建议 1：任务执行与规划（a 现在做 / b 写文档排期）
合理，已据此分类（见 §2 / §3）。

### 建议 2a：计算逻辑后移
**合理，但需修正范围与边界：**
- 你担心的「前端大量计算」确实存在，但**重计算（权重合成）已在后端**；真正散的是「值→档位 / 颜色 / tone / 解读文案」的派生，且集中在**前端 store 与 explore 页**，不在你以为的 domain view 层（那个已是薄视图）。
- 边界建议：后端拥有**语义派生**（level、tone、insights、短中长 composite）；前端拥有**呈现**（颜色 token、布局、width%）。不要过度后移——「前端只做展示」是目标，但颜色/宽度本就是视图关注点。
- 必须先做 §0 的阈值统一，否则后移会继承不一致。

### 建议 2b：提示文案归集
**合理，但需界定范围：**
- 仅「**数据驱动的解读文案**」应后端归集：`buildOpportunities` 的 `desc`/`tone`、各指标带动态值的 `caption`（如「估值温度 X° · 越低越便宜」）。
- 纯静态 UI 文案（如「成交量热度反映市场活跃度」）留前端 / i18n，不应后端化。

### 图1 / 图2 的 UI 建议
- **概览页展示短/中/长期**：产品思路合理；但需后端先返回短中长分解（B1），否则无法落地。
- **状态胶囊等高占位**：设计语言已强制，explore 已对所有卡传 `level` 且卡片有 `min-height`，基本满足；仅「暂无」文案可改为透明占位（低优先）。
- **8+4 栅格右栏放图表**：设计决策，需你确认 spec，不盲做。
- **流动性卡资金流向可视化**：需数据，部分依赖后端（B5）。
- **温度计卡片收拢**：当前代码已用 `MetricGrid` 分组（core / detail 两区），block 描述的散卡片应是旧版，已基本满足。
- **陈旧提示视觉污染**：已执行（见 §2）。

## 2. 现在可做（纯前端，无需后端新接口）

- [x] **温度计页陈旧提示** → 标题行右侧「折角胶囊 + hover 气泡」（`temperature/index.vue`，2026-08-02 已完成，含 `.bias-stale-pill` 样式）。
- [ ] 探市页状态占位微调：「暂无」徽章改为透明等高占位 —— 低优先，待确认。
- [ ] 探市页 8+4 栅格右栏图表 —— **需你先定 spec**，不盲做。

## 3. 需要后端接口 / 改造（排期）

### P1（先打通数据，解除前端重复计算）—— 阻塞项，优先做前半
- [x] **B4 统一权威阈值（先于其它）**：✅ 已落地。`constants.py` 新增 `TempLevel` 枚举作唯一权威来源；`label_temp` 收敛到枚举（并处理 None→`未知`）；`fetchers.py` self_calc 与 `service.py` composite 散落阈值逻辑均改用 `label_temp`，消灭 `fetchers.py` 的「正常」与不一致的 30/70 阈值；`views.py` 示例 payload 的「正常」亦改为「适中」。前端 `explore` 的 `selfCalcLevel` 兜底由「正常」改为「暂无」。
- [x] **B2 `jisilu_indicator` 补 `level`**：✅ 已落地。后端 `fetchers.py` 的 `jisilu_indicator` 新增 `median_pb_level` / `median_pe_level`（`label_temp` 派生）；前端 `explore` 删除本地 `inferValuationLevel`，`pbLevel`/`peLevel` 改用后端 `level`。
- [x] **B1 短/中/长期 composite 分解**：✅ 已落地。`/overview` 的 `composites` 新增 `temperature_bands`：`short`(短期情绪=jiucaishuo_fear) / `medium`(中期温度=jiucaishuo_medium) / `long`(长期估值=self_calc.percent)，各含 `name`/`value`/`level`。
  - ⚠️ **待产品复核**：「长期」当前取股债利差估值分位原值（高=估值贵=热，与 PB/PE 温度同向，不反向）；其「历史低位」等解读文案归 B3，不在 B1 生成。若你希望「长期」改为有知有行/且慢等其它长周期源，或反向表达，需调整 `_compute_temperature_bands`。

### P2（文案 / 数据归集）
- **B3 解读文案后端归集**：`/overview` 增加 `insights`（每项 `name`/`desc`/`tone`），消除前端 `store.buildOpportunities`；各 singles 补充 `caption` 字段，消除前端动态文案。
- **B3 边界（防矫枉过正）**：后端只给 `level` 字符串；**颜色 Token / CSS 变量必须留在前端** `computed`。前端维护一份 `level → { label, colorVar, class }` 映射表（如 `{ '偏低': { color: '--tag-low' } }`），为暗色模式留余地。绝不可把颜色码塞进 JSON。
- **B5 流动性资金流向数据接入 explore**：确认复用 `/multi` 的 `sector_flow` 或新增接口，支撑流动性卡右侧可视化。

### P3（页面层）
- [x] **概览页短/中/长期落地（行内三连）**：✅ 已落地。`welcome/index.vue` 综合温度卡下方接入 `temperature_bands` 行内三连（短期/中期/长期，各含数值°+档位胶囊），颜色令牌用前端 `level→--temp-*` 映射（符合 B3 边界），未下发颜色码。
  - 待 B3：综合温度环下方的「结论副文案」（如「短期情绪偏冷，中期估值适中，长期处于历史低位」）应由后端 `insights` 归集返回，前端不写死。当前未实现该文案。
  - ⚠️ 仍依赖 B1 的「长期」映射待复核决策（见 P1 B1 说明）。

## 4. 概览页落地执行记录（前端，纯展示层）

- 2026-08-02：第四排 12 列栅格对齐 + 接入 `SectionHeader`；心理账户配色改品牌红三档透明度（消除歧义）。
- 2026-08-02（补充）：第一/二/三排共 6 个区块标题全部接入 `SectionHeader`（含动态标题「置顶资产 / 持仓市值最大资产」与各自操作槽），消除「上半身粗鲁」隐患，全页标题结构统一。

## 5. 涉及文件

- 后端：`app/services/thermometer/service.py`、`constants.py`、`fetchers.py`、`app/domains/temperature/views.py`、`schemas`（如有）
- 前端：`store/modules/temperature.ts`、`views/explore/index.vue`、`views/temperature/index.vue`、`views/welcome/index.vue`、`api/temperature.ts`

## 6. 提交建议（原子化，便于回滚）
- `feat(welcome): 全页区块标题接入 SectionHeader 并统一 12 列栅格`
- `fix(psych-account): 进度条统一品牌红以消除颜色歧义`
- `fix(temperature): 陈旧提示改为折角胶囊 + hover 气泡`
- `docs(spec): 更新投资概览页评估与后端排期`
- 注意：勿将 `design.md` / `components.md` 的零散改动混入上述提交。

## 7. 同步指令速查（2026-08-02 新增）

统一入口 `backend/app/tools/sync_cli.py`（封装常用同步指令）。在 `backend` 目录下用 pdm 运行：

```powershell
# 跑市场温度（集思录估值温度 / 韭圈儿 / 自算估值分位；乖离率已跳过）
pdm run python -m app.tools.sync_cli temperature

# 跑全部同步任务
pdm run python -m app.tools.sync_cli all

# 单独跑某个 Job（透传 Orchestrator.run_job）
pdm run python -m app.tools.sync_cli job fund_nav

# 只读诊断：确认 jisilu_indicator 是否已含 level（B2 端到端验证）
pdm run python -m app.tools.sync_cli verify-jisilu
```

或沿用旧入口 `sync_metadata.py`（等价）：
```powershell
pdm run python -m app.tools.sync_metadata --job temperature
```

> `verify-jisilu` 期望输出 `level 字段: ['median_pb_level', 'median_pe_level']`；若为空说明 B2 尚未在真实数据生效，需先跑 `temperature` 抓取。

## 8. 乖离率计算暂停（2026-08-02）

- **现状**：`TemperatureJob._fetch_data` 内的乖离率块在运行时会出错。已在 `jobs.py` 顶部加 `SKIP_BIAS = True` 开关，跳过时记 `logger.warning` 提醒，**不落库乖离率数据**。原逻辑保留为注释块（`TODO(乖离率)`）备查。
- **放开条件**：后期找到可行方案后，将 `SKIP_BIAS` 置 `False` 并取消原逻辑块注释即可。放开不影响 `sync_cli.py` 用法。
- **影响**：本次温度同步不含乖离率（前端若依赖乖离率展示需另行处理，当前概览页三连不依赖）。
