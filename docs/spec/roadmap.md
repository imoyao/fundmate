---
title: 项目路线图与进度表（roadmap）
---

# 项目路线图与进度表（roadmap）

> 📌 **本文件是导航层，不是进度表。**
>
> **进度以 GitHub 为唯一事实源**（里程碑 + issue）。本文件只回答三个问题：
> ① 优先级怎么定义；② 某个里程碑/编号对应哪个 issue；③ 当前 NOW/NEXT/LATER 在哪张卡上。
>
> 最后核实：**2026-10-24**（治理动作 #2407 已执行：里程碑 14 → 10，`#6`/`#8`/`#12`/`#15` 归档）。
> 历史逐卡进度表已移除，完整盘点见 `docs/working-notes/roadmap-realign-2026-10-19.md`。

## 1. 四象限优先级定义（永久标准）

- **第一象限｜重要且紧急**：阻塞核心流程、产生数据错误、影响当前阶段目标的任务，48 小时内闭环
- **第二象限｜重要不紧急**：决定产品核心价值、长期能力的功能，固定排期迭代
- **第三象限｜不重要但紧急**：临时环境、依赖、报错问题，极简快速修复
- **第四象限｜不重要不紧急**：UI 美化、细节打磨、远期创意，统一延后归档

**象限标签的维护节奏**（防标签漂移）：

- 每月**第一个周一**复查 open 的 Q1-RED 全量；
- open 的 Q1-RED **超过 5 张即视为标签漂移**，强制重新裁定；
- 挂 Q1-RED 必须在正文写明「阻塞哪件事」，否则降 Q2；
- 跟流程见 issue #2410。

> **Q1-RED 的准入标准会跟随「当前阶段目标」变化。** 当前阶段目标是**基础可用 + 免费功能跑起来**（不是付费验证——R0 口径已被推翻），所以「阻塞免费层上线与日常可用」的卡才进 Q1。

## 2. 当前阶段与路线图

**当前阶段（2026-10 → 11 月底）：基础可用 + 免费功能跑起来。**

判据：*一个真实用户能连续用一个月，不踩坑、数据不骗人、数字说得通*。

- 完整 NOW / NEXT / LATER 排序与依赖：**issue #2409**（唯一真源，含每档启动条件）
- 可视化路线图：`artifacts/roadmap-2026-10-19.html`

不复制内容到本文件——排序一改这里就会失真，这是本文件被瘦身的直接原因。

## 3. 里程碑 ↔ issue 映射

### 3.1 ⚠️ 命名陷阱（引用前必读）

**标题里的 M 编号 ≠ 里程碑内部编号。** 两者是历史错位造成的，引用时一律用内部编号。
**档位以 GitHub 里程碑描述为准**（每个描述首行都写了 NOW / NEXT / LATER），下表只是索引。

| 内部编号 | 标题 | 档位 | 说明 |
|---|---|---|---|
| #5 | **M2** 免费核心 Free Core | NOW | 标题 M2，内部是 5；**当前阶段里程碑** |
| #16 | 反馈与更新日志闭环 Feedback & Changelog | NOW | 执行级；Q1-RED 三卡在此；清完即关 |
| #13 | M0 上线 Launch | NOW | 标题 M0，内部是 13；只出不进，收尾即关 |
| #4 | **M1** 付费验证 Paid Validation | LATER（冻结） | 标题 M1，内部是 4；解冻条件见 §3.2 |
| #17 | 账本能力对齐 | NOW → NEXT | 主题容器（#2018 拆分） |
| #18 | M7 策略与纪律 Strategy & Discipline | NEXT | 2026-10-15 新立 |
| #19 | 高级洞察 Pro 面板 Pro Insight Panel | NEXT → LATER | 仅 Phase 0 数据底座 |
| #14 | 双库架构 DB Multi-Engine | NOW | 主题容器；有专项治理规则（见 AGENTS.md） |
| #2 | 基础数据 Base Data | NOW → NEXT | 主题容器，无 M 编号 |
| #9 | M6 待办积压 Backlog | LATER | **仅作远期兜底，不得再当垃圾桶** |
| ~~#6~~ | M3 量化分析 Quant Analysis | 已关闭 | 2026-10-24 归档；卡分 #18 / #9 |
| ~~#8~~ | M5 安全与体验 Security UX | 已关闭 | 2026-10-24 归档；卡分 #17 / #19 / #2 / #9 |
| ~~#12~~ | 自选增强 Watchlist Enhancement | 已关闭 | 2026-10-24 归档；卡并入 #2 |
| ~~#15~~ | 产品详情页 Product Detail | 已关闭 | 2026-10-24 归档；卡并入 #19 |

### 3.2 里程碑归属规则（治理修订 R1）

- **当前阶段执行级**：M2 免费核心（#5）、M16 反馈闭环（#16）、M0 上线（#13，只出不进）；
- **主题容器**：M17 账本对齐（#17）、M18 策略引擎（#18）、M19 Pro 面板（#19，仅 Phase 0 数据底座）、双库架构（#14）、基础数据（#2）；
- **冻结**：M1 付费验证（#4）整块冻结至免费层稳定——**卡保持原样，不清零**。解冻条件（三条同时满足）：
  ① 免费层连续 2 个月无 P0/P1 缺陷；② NOW 档里程碑 #5 / #16 / #13 全部关闭归档；③ owner 明确决定启动付费验证；
- **M6 Backlog（#9）**：只接收「永不承诺」的远期卡与 LATER 档体验打磨 / 增长实验。战略卡（「债务:」前缀、Q4-GRAY 之外的付费主线）一律迁出；
- **已关闭归档（2026-10-24）**：#6 M3、#8 M5、#12 M12、#15 M15 的 open 卡按路线图分流后清空关闭，**归档不复活**——这些主题不再新开里程碑，新卡按主题就近挂载（分析能力 → #18，数据 → #2，账本 → #17，体验打磨 / 远期 → #9）。

详见 issue #2407 / #2408。

## 4. GitHub issue ↔ 文档反链索引

> **两条铁律**：① **文档↔issue 双向交叉引用**——issue 评论区标注关联文档，文档侧回链 issue；② **文档↔历史差异必须拉平**——文档描述与代码现状不符时，要么改文档、要么开 issue 跟踪，不留悬空描述。

| issue | 标题 | 象限 | 对应文档 / 代码 |
|:---|:---|:---|:---|
| [#2407](https://github.com/imoyao/fundmate/issues/2407) | 里程碑收敛 14 → 7 | — | 本文 §3；`docs/working-notes/roadmap-realign-2026-10-19.md` §5.1 |
| [#2408](https://github.com/imoyao/fundmate/issues/2408) | M6 Backlog 大扫除 | — | 本文 §3.2；同上 §5.2 |
| [#2409](https://github.com/imoyao/fundmate/issues/2409) | R1 路线图排序（免费优先） | Q1 | 本文 §2；同上 §3/§4 |
| [#2410](https://github.com/imoyao/fundmate/issues/2410) | Q 标签月度复查机制 | — | 本文 §1 |
| [#2411](https://github.com/imoyao/fundmate/issues/2411) | 事实源统一（本文瘦身） | — | 本文抬头 |
| [#783](https://github.com/imoyao/fundmate/issues/783) | 记账功能需求检查单 | Ⅰ | `docs/dev/import-trade-records.md`；清单正文在 issue 内 |
| [#807](https://github.com/imoyao/fundmate/issues/807) | 自选页面实时估值功能设计文档 | Ⅰ（已收窄关闭） | `docs/features/watchlist.md`；`docs/design/my-favrivate.md` |
| [#821](https://github.com/imoyao/fundmate/issues/821) | 探市页（免登录沙盒）缺陷与缺口跟踪 | Ⅰ | `frontend/src/views/explore/index.vue`；`backend/app/core/auth.py` |
| [#229](https://github.com/imoyao/fundmate/issues/229) | 基本数据抓取及组织 | Ⅱ | `docs/spec/tech-debt.md`（里程碑 基础数据 `#2`） |
| [#427](https://github.com/imoyao/fundmate/issues/427) | 基于 dataclasses 实现 choices 类型 | Ⅱ（技术债） | `docs/dev/choices-for-sqlalchemy.md` |
| [#508](https://github.com/imoyao/fundmate/issues/508) | 消息推送机制 | Ⅱ（远期） | 暂无专门文档 |
| [#782](https://github.com/imoyao/fundmate/issues/782) | 资产简记和投资记录页面设计 | Ⅱ | `docs/features/holding-record.md` |
| [#808](https://github.com/imoyao/fundmate/issues/808) | 自选「探市」体验版设计文档与任务计划 | Ⅱ | `docs/spec/temperature-architecture-plan.md`；`docs/features/watchlist.md` |
| [#809](https://github.com/imoyao/fundmate/issues/809) | 数据库存储选择 | Ⅱ | `docs/spec/decisions.md` D3/D2；`docs/dev/db-choice.md` |
| [#819](https://github.com/imoyao/fundmate/issues/819) | 交割单导出功能跟踪 | Ⅱ | `backend/app/services/importer/` |
| [#820](https://github.com/imoyao/fundmate/issues/820) | FeeRatio 增加币种字段并落库 | Ⅱ | `docs/dev/fund-fee-ratio.md`；`backend/app/domains/funds/models.py` |
| [#273](https://github.com/imoyao/fundmate/issues/273) | 自选基金拖拽排序 | Ⅳ | `frontend/src/views/asset/watchlist/index.vue` |
| [#817](https://github.com/imoyao/fundmate/issues/817) | 鹦鹉螺 nautilus 作为 logo | Ⅳ | `docs/design/brand-v1.7.md` |
| [#911](https://github.com/imoyao/fundmate/issues/911) | 后端持仓身份统一键与列表性能整改 | Ⅱ | `backend/app/services/position_service.py`；`ledger_service.py` |
| [#898](https://github.com/imoyao/fundmate/issues/898) | 文档与代码误差追踪（会议纪要） | — | `docs/spec/tech-debt.md` §14-B |
| [#937](https://github.com/imoyao/fundmate/issues/937) | 导入持仓快照（position_import） | Ⅰ | `frontend/src/views/asset/inventory/index.vue` |
| [#933](https://github.com/imoyao/fundmate/issues/933) | 前端统一提交层（ImportOrchestrator） | Ⅰ | `composables/useQuickEntry.ts` |
| [#934](https://github.com/imoyao/fundmate/issues/934) | 资产简记截图导入入口 | Ⅰ | `docs/spec/tech-debt.md` §14-B |
| [#825](https://github.com/imoyao/fundmate/issues/825) | DB 快照导出/导入层 | Ⅱ | `sync/orchestrator.py` |
| [#894](https://github.com/imoyao/fundmate/issues/894) | 上线计划（Turso / EdgeOne） | Ⅱ | `docs/spec/tech-debt.md` §14-B；里程碑 双库架构 `#14` |
| [#1028](https://github.com/imoyao/fundmate/issues/1028) | 独立 dev Supabase 项目 + .env 隔离 | Ⅰ（NOW N2） | 里程碑 双库架构 `#14` |
| [#2001](https://github.com/imoyao/fundmate/issues/2001) | feedback 站间歇性 503 | Ⅰ（NOW N4） | 里程碑 M16 `#16` |
| [#2130](https://github.com/imoyao/fundmate/issues/2130) | 账本对齐汇总卡（13 卡推进与拍板） | Ⅱ | 里程碑 M17 `#17` |
| [#2132](https://github.com/imoyao/fundmate/issues/2132) | 账本对齐 B' 快照体系收口 | Ⅰ（NOW N5） | 里程碑 M17 `#17`；所有口径计算的前置 |
| [#2136](https://github.com/imoyao/fundmate/issues/2136) | 账本对齐 F 现金闭环 | Ⅰ（NOW N5） | 里程碑 M17 `#17` |
| [#2133](https://github.com/imoyao/fundmate/issues/2133) | 账本对齐 C TWR 时间加权收益率 | Ⅰ（NOW N5） | 里程碑 M17 `#17` |
| [#2324](https://github.com/imoyao/fundmate/issues/2324) | Pro 端点缺后端权益校验 | LATER（Pro 对外可见前必做） | 里程碑 M19 `#19` |

新增或关闭 issue 时须同步维护本表。

## 5. 历史进度表去向

原 §1.2 完整 P1 任务进度总表、§1.3 P2 功能规划、§1.4 进度总览、§2 支持计划（含 2.7 账本精灵立项）已移除。

- **逐卡状态** → GitHub issue（唯一真源）
- **技术债台账** → `docs/spec/tech-debt.md`
- **2026-10-19 全量盘点与分流表** → `docs/working-notes/roadmap-realign-2026-10-19.md`
- **历史差异已闭环项** → 本文件 §4 与 `docs/spec/tech-debt.md`

需要恢复某条历史上下文时，从 GitHub issue 时间线与对应 working-notes 找，不要在本文件重新维护状态列。