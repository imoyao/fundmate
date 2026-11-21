---
title: 后端结构审查报告（2026-11-21）
status: 批次 0/1 已落地，批次 2~6 待排期
scope: backend/app 全量 541 模块 / 123113 行
---

# 后端结构审查报告

> 本报告由 AI 架构审查生成（2026-11-21），依据 `docs/spec/conventions.md`（冻结区）、
> `architecture.md`、`AGENTS.md` 的既有口径，**不新增规范**，只把「结构不清晰」翻译成可复跑的判据。
> 复跑命令见文末附录。
>
> **落地进度**：§2-E / §2-F 已随本报告同一 PR 修复（批次 0 / 1），详见 §5「已落地」。

---

## 0. 口径声明（先收紧定义，再报数字）

「文件太大」不是一个可验收的判据。本报告沿用仓库**已有的**两套闸门口径，不自创阈值：

| 指标 | 定义 | 新增上限 | 出处 |
|---|---|---|---|
| `lines` | 文件物理行数 | 800 | `scripts/guard_service_size.py::NEW_FILE_LIMITS` |
| `max_func` | 单函数行数（`end-start+1`） | 120 | 同上 |
| `max_cc` | 单函数 McCabe 圈复杂度 | 20 | 同上 |
| 视图层 | `views.py` 行数 / DB 调用数 | 只减不增 | `scripts/check_view_thickness.py` |

**关键事实**：审查当时 `guard_service_size.py` 的自检输出是

```
OK: services 层体量 / 复杂度无新增（基线存量：286 个文件 / 81576 行；
    最长函数 ≤ 688 行 / 最高圈复杂度 ≤ 106；只减不增）
```

也就是说——**闸门是生效的（没有回潮），但它把存量整体冻结了**：新增文件必须 ≤800 行 / ≤120 行函数 / ≤20 复杂度，
而存量里最长函数是 **688 行**、最高复杂度是 **106**。存量不会自己变小，这正是「结构不清晰」的体感来源。

同一道闸门在批次 1 扩到 `core/` 之后为（324 个文件 / 91766 行）：

```
OK: services / core 层体量 / 复杂度无新增（基线存量：324 个文件 / 91766 行；
    最长函数 ≤ 688 行 / 最高圈复杂度 ≤ 106；只减不增）
```

全量实测分布（`app/` 下 541 个模块）：

| 判据 | 越线文件数 |
|---|---|
| `lines ≥ 800` | 16 |
| `max_func ≥ 120` | 33 |
| `max_cc ≥ 20` | 66 |

**本轮 P0 = 0**。跨域同语句 0 命中、错误信封 0 处不合规、尾斜杠 5 处全在 `NO_TRAILING_SLASH_ALLOWLIST` 内。
本报告全部为 **P1（结构骨架）/ P2（卫生与一致）**，没有「必然引爆」的运行时缺陷。

---

## 1. 分级速览

| # | 级别 | 问题 | 证据（file:line） | 建议 | issue |
|---|---|---|---|---|---|
| A | **P1** | `services/` 没有二级结构：158 个扁平模块 + 13 个子包堆在同一层，与 34 个域无对应关系 | `backend/app/services/*.py` 158 个 / 47643 行 | 按域目录化（最后做，见批次 6） | 待开卡 |
| B | **P1** | 单函数 688 行 / cc 106，`while` 体 477 行 | `services/pnl_calendar.py:1184`（`_compute_days`） | 拆 6 段 + 状态对象（批次 2） | 待开卡 |
| C | **P1** | `_prefetch_all` 239 行 / cc 68，20 段预取串在一个方法里 | `services/watchlist_display.py:163` | 拆 6 个 `_prefetch_*`（批次 3） | 待开卡 |
| D | **P1** | `build_penetration` 404 行 / cc 96 | `services/penetration.py:326` | 拆 4 段（批次 4） | 待开卡 |
| E | **P1** | **`core/` 无任何体量闸门，而它装着全仓最大的文件** | `core/migrations.py` 3014L、`core/db_factory.py` 1076L、`core/database.py` 897L | 闸门扩到 `core/`（批次 1，已做）+ 按域拆迁移（批次 1b，另开 PR） | ✅ 闸门已落地（见 §5） |
| F | **P1** | 分层守卫 R1 **只拦 `core→domains/models`，不拦 `core→services`**，现存活反例且守卫全绿 | `core/entitlements.py:10`；`scripts/guard_layer_direction.py` 规则表 | R1 增补一条非法边（批次 0） | ✅ 本次 PR（见 §5） |
| G | **P1** | 上帝类：3 个类体 >900 行 | `adapters/akshare_adapter.py:1826L 类体`、`fund_service.py:985L`、`importer/orchestrator_holdings.py:1158L mixin` | 按「取数 / 计算 / 写库」三段拆（批次 5） | 待开卡 |
| H | **P2** | 编排型 job 单函数过长（职责使然，但已越过新文件上限） | `thermometer/jobs.py` max_func=287；`trade_timeline.py` 235；`conversion_service.submit_conversion` 283；`importer/orchestrator_commit.py` 217 | 抽子步骤，随批次 2–4 的范式一起做 | 待开卡 |
| I | **P2** | 存量基线缺收敛节奏：33 个文件 max_func≥120、66 个 cc≥20 全部走 `legacy` 冻结 | `guard_service_size.py -v` 输出 | 每完成一个批次同 PR 回写基线（脚本已支持 `--report`） | 随各批次 |

---

## 2. 逐条详述

### A. `services/` 层的结构问题：不是「文件大」，是「没有地方放」

这是我认为**比单个大文件更值得修**的一条，也是「结构不清晰」最直接的原因。

```
app/domains/   34 个域，每个域结构一致：models.py / schemas.py / views.py（+ 少量专属模块）
app/services/  158 个扁平 .py + 13 个子包
```

对照两侧就能看出问题：`domains/` 有清晰的域边界，`services/` 却是**一张平铺的清单**。
想找「持仓」相关代码，要在同一层里翻 `position_service.py`、`position_aggregation.py`、
`position_valuation.py`、`position_presenter.py`、`position_buy_command.py`、`position_sell_command.py`、
`position_orphan_flows.py`、`position_recompute*.py`、`position_snapshot_command.py`、
`conversion_service.py`、`trade_timeline.py`……

已经目录化的只有 13 个子包（`adapters / ai_recognizer / alerts / analytics / bias / common /
importer / mcp / performance / strategy_engine / sync / thermometer`）——**说明「按家族建包」在本仓是既有范式，
只是没有铺开**，不是新发明。

> 反驳意见（我认可其分量）：扁平化换来的是 `from app.services.foo import bar` 的短路径，
> 目录化会让 150+ 处 import 一起变。所以这条排在**最后**做，且必须一次性机械改完、不夹带逻辑变更。

### B. `pnl_calendar._compute_days` — 688 行 / cc 106（最硬的一条）

`services/pnl_calendar.py:1184-1871`。内部结构已经测出来：

| 段 | 行范围 | 行数 | 职责 |
|---|---|---|---|
| 窗口与取价预解析 | 1230–1308 | 79 | 窗口前扩 `_STALE_CARRY_DAYS`、净值/场内价批量取、交易日落表 |
| `price_of` 闭包 | 1311–1331 | 21 | 单点取价（bisect + 缓存） |
| 逐持仓 as-of 基准 | 1334–1342 | 9 | `_build_per_pos` |
| **日循环** | **1393–1869** | **477** | 见下 |
| 返回 | 1871 | 1 | |

日循环体（477 行 / 32 条顶层语句）可切成 7 段，每段都有独立语义：

| 段 | 行范围 | 职责 |
|---|---|---|
| 日初始化 | 1394–1428 | 缓存清理、split 判定 |
| as-of 推进 | 1416–1428 | 多头寸份额推进 |
| 逐持仓估值 | 1429–1508 | `ResidualBook`、市值/成本/已实现 |
| 日合计与差分 | 1509–1549 | `daily_pnl = total − prev` |
| **七态判定** | 1550–1665 | 出 `state_code`（116 行，cc 贡献最大） |
| 非交易日冻结 | 1666–1749 | 陈旧判定 / 冻结基准 |
| 区间内 emit | 1750–1851 | 归因 / 分类 / 基点 / 精确率 |

**拆法**（关键：状态是闭包里的 20+ 个可变局部变量，不能简单提函数）：
引入 `_DayRun`（或叫 `_CalendarAccumulator`）持有 `day_level / day_class_* / prev_* / price_cache /
last_known` 等状态，7 段各变成一个方法；`_compute_days` 只留「建对象 → 循环 → 收结果」。

**验收**：`lines ≤ 800`、`max_func ≤ 120`、`max_cc ≤ 20`（与新增文件上限对齐）；
`tests/services/test_pnl_calendar*.py` 4 个文件、16 个引用点全绿；对外 API 零变更（`conventions.md §2.4`）。

### C. `watchlist_display._prefetch_all` — 239 行 / cc 68

`services/watchlist_display.py:163`。20 段预取串成一条直线（positions 聚合 → 均价 → 元数据 →
价格 → 净值 → 估算 → 日历截止 → 标签 → 投顾 → 经理 → 基金名 → 去前缀码 → 展示段）。
cc 68 主要来自每段都有的 `if x:` 短路。

拆成 `_prefetch_positions / _prefetch_quotes / _prefetch_fund_meta / _prefetch_advisors /
_prefetch_display`，各段之间**无数据依赖**（只写 `BatchContext` 字段），是三个大函数里最容易的一个。

**注意**：「当前持仓」口径必须继续走 `position_scope.active_holdings()`
（`scripts/guard_watchlist_active_scope.py` 静态拦截，拆的时候别绕过）。

### D. `penetration.build_penetration` — 404 行 / cc 96

`services/penetration.py:326`。段结构：直投腿（380–423）→ 基金腿（437–462）→ 直投补全（473–482）→
**其他方案的对照（505–573，69 行）** → 基金腿补数（584–599）→ 排序截断（603–626）。

其中「其他方案对照」是纯展示逻辑、与主计算无耦合，优先抽出 `_other_scheme_notes()`。

### E. `core/` 是闸门盲区，而且它装着全仓最大的文件

三个体量闸门的分工：

| 闸门 | 覆盖范围 | `core/` |
|---|---|---|
| `guard_service_size.py` | `backend/app/services/**` | ❌ |
| `check_view_thickness.py` | `app/domains/*/views.py` | ❌ |
| `check_vue_size.mjs` | 前端 | ❌ |

结果：**`app/core/` 39 个模块 / 10251 行，一个闸门都没有**，而全仓最大的文件就在里面：
`migrations.py` 3014 行、`db_factory.py` 1076 行、`database.py` 897 行（`init_db` 单函数 156 行）。

**已修（批次 1，本次 PR）**：`SCAN_DIRS` 改为 `services + core`，判据与上限不变，core 整层按实测
冻结进 `BASELINE`（38 个模块）。闸门自检输出随之变成 324 个文件 / 91766 行。
覆盖范围的退化由 `test_core_layer_is_scanned_and_frozen` 钉住——把 `SCAN_DIRS` 退回只扫 services
时它定向转红（已做反向验证）。

### F. 分层守卫有一条没设防的边（本轮最值得警惕的一条）

`guard_layer_direction.py` 的 docstring 写明了依赖方向：

```
core  ←  domains.<域>.models / schemas  ←  services  ←  domains.<域>.views
```

但它的 **R1 只拦 `app.core.* → app.domains.* / app.models.*`**，没有 `core → services`。
于是 `core/entitlements.py:10` 模块顶层 `from app.services.entitlement_check import ...`
**活着，而且守卫输出 OK（R1~R7 全绿）**。

这正是「看起来像闸门、实际不设防」的形态：规则文字写了方向，判据只覆盖一半。
（另一处 `core/migrations.py:1453,2048` 是**延迟导入** + 显式注释说明，属已登记的可接受写法，不算违规。）

**修法不是「把它拆成纯函数下沉到 core」，而是「这个模块放错了层」**：
`core/entitlements.py` 只有 61 行，内容是 `flask.g` + `database.get_session()` + services 调用的
**Flask 装饰器**（docstring 自称「Flask 集成层」）。它是 HTTP 集成适配器，`core/` 里没有任何东西依赖它，
唯一消费方是 `domains/products/views.py:20`。

⇒ 正解：移到 `app/services/entitlements/`（跟 `services/alerts`、`services/insight` 同级的薄集成层），
更新 1 处 import，再给 R1 补上 `core → services` 判据。**移动 1 个文件即可闭合，不需要改 `entitlement_check` 的内部实现**
（它依赖 `core.exceptions` + `domains.entitlements.models`，本身方向完全合法）。

### G. 三个上帝类

| 文件 | 类体 | 形态 |
|---|---|---|
| `adapters/akshare_adapter.py` | `AkshareAdapter` 1826 行（文件 2023 行，8 个顶层定义） | 单一数据源适配器，按数据类型堆方法 |
| `importer/orchestrator_holdings.py` | `HoldingsMixin` 1158 行（占文件 96%） | Mixin，职责天然混杂 |
| `fund_service.py` | `FundService` 985 行（占文件 96%） | 基金域全部读写 |

拆法与 B 同理：`AkshareAdapter` 可按「行情 / 基础信息 / 持仓 / 行业」分文件为 4 个 mixin 或
4 个协作对象（外面仍暴露同一个 `AkshareAdapter` 门面，调用方零改动）。

---

## 3. 已核查但排除的项（避免后人重复怀疑）

| 项 | 实测 | 为什么不算缺陷 |
|---|---|---|
| `domains/funds/advisor_catalog.py` 1386 行 | 最大函数 6 行、cc 3 | 单一真相源注册表，docstring 明示；**数据文件不是逻辑文件** |
| `core/migrations.py` 3014 行 / 39 个 `migrate_*` | 最大函数 131 行 | 模块 docstring 定义的是「每个迁移函数约定」，append-only 登记式结构。**建议按域拆文件（批次 1），但不按「上帝模块」定性** |
| `services/daily_scheduler.py` 1136 行、依赖 13 个域 | max_func 仅 39 行 | 调度器天然认识所有域，职责使然 |
| 48 组「双向依赖对」 | 扫描器输出 | 全部是 `views→services` + `services→models` 两条**合法边**叠加；守卫已明示不判 |
| `core/migrations.py` 延迟 import services | 2 处，带注释 | 运行期安全，规避导入环，已有说明 |
| `core.entitlements → services` | 1 处顶层 import | **不排除**，见 §2-F |
| 跨域同语句 | 0 命中 | `check_cross_domain_query.py` 口径下已清零 |
| 错误响应信封 | 0 处不合规 | `guard_error_envelope.py` 全绿 |
| 端点尾斜杠 | 5 处无斜杠，全在 allowlist | `/health` + 温度计 4 个，已由 D28 登记 |

---

## 4. 建议的重构批次（先补闸门，再拆存量）

> 顺序的理由：**先有棘轮再拆**。否则拆完的文件没有闸门守住，两个迭代后又长回去（#2873 的教训）。

| 批次 | 内容 | 风险 | 依赖 | 状态 |
|---|---|---|---|---|
| **0** | `core/entitlements.py`（61 行 Flask 装饰器）移到 `services/entitlements_flask.py`；R1 增补 `core → services` 导入期判据 | 低 | 无 | ✅ 本次 PR |
| **1** | `guard_service_size.py` 扩到 `app/core/`（整层按实测冻结，只减不增） | 低 | 0 | ✅ 本次 PR |
| **1b** | `migrations.py`（3014 行 / 39 个迁移）按 init_db 已有的 `app_eng` / `user_eng` 分组拆成 `migrations/{market,user,_helpers}` + 门面 re-export | 中 | 1 | ⏸ 单独 PR |
| **2** | `pnl_calendar` 拆 `_compute_days` | 中（金融口径，16 个引用点） | 1 | 待排期 |
| **3** | `watchlist_display` 拆 `_prefetch_all` | 低 | 1 | 待排期 |
| **4** | `penetration` 拆 `build_penetration` | 中 | 1 | 待排期 |
| **5** | 三个上帝类（`AkshareAdapter` / `HoldingsMixin` / `FundService`） | 中高 | 2–4（先立范式） | 待排期 |
| **6** | `services/` 按域目录化 | 高（150+ import） | 全部 | 待排期 |

**为什么 1b 单独一个 PR**（审查后来补的判断）：`migrations.py` 是**生产启动路径**上的代码——
`init_db()` 末尾的 `_validate_schema` 一旦因结构漂移失败就会拒绝启动（#2469 / #2532 两次生产停摆）。
拆分本身是纯搬移（调用顺序写在 `database.py` 里，不受文件划分影响），但它同时牵动
`scripts/guard_migrations_pg_aware.py` 的单文件路径假设与它的基线口径，属于「改一个地方要同时改判据」
的形态——与本次这批「加闸门 / 移文件」混在一个 PR 里，出问题时不好二分。故单独走。

每批次的完成判据固定为三条：`lines ≤ 800 / max_func ≤ 120 / max_cc ≤ 20`、
相关测试全绿、**同 PR 内 `guard_service_size.py --report` 回写基线**（脚本 docstring 已写明这一纪律）。

---

## 5. 已落地（本次 PR）

| 项 | 改动 | 判据 |
|---|---|---|
| §2-F 分层盲区 | `core/entitlements.py` → `services/entitlements_flask.py`（1 处 import 同步） | `guard_layer_direction.py` 全绿；`tests/core/test_layer_direction.py` 47 passed |
| §2-F 判据补齐 | R1 增补 `core → services`（**仅导入期**；函数体延迟 import 属已登记例外） | 反向验证：把 `from app.services.…` 放回 `core/` 顶层 → 守卫转红（R1）；删除后复绿 |
| §2-E 闸门盲区 | `SCAN_DIRS = services + core`，core 38 个模块按实测冻结进 `BASELINE` | 反向验证：`SCAN_DIRS` 退回只扫 services → 2 红 8 绿；恢复后 10 绿 |
| 文档 | `AGENTS.md` 的体量闸门条目补上 core；`RULE_REGISTRY` 两条边界说明同步 | `guard_rule_registry.py` exit 0（纯文字硬约束仍 88） |

**没有做**（避免把「加闸门」和「动生产启动路径」混在一起）：批次 1b 的 `migrations.py` 拆分，见上表理由。

---

## 附录：复跑命令

```bash
cd /d/codes/fundmate

# 1) 官方闸门 + 实测（权威口径）
python scripts/guard_service_size.py -v
python scripts/guard_service_size.py --report

# 2) 架构六面扫描（依赖 / 跨域 / 视图厚度 / 信封 / 尾斜杠）
python "C:/Users/imoyao/.workbuddy/skills/fundmate-backend-arch-audit/scripts/backend_arch_scan.py"

# 3) 分层方向
python scripts/guard_layer_direction.py

# 4) 单函数热点定位：`--report` 已逐文件给出 max_func / max_cc，
#    想看「哪个函数」时按文件内 `ast` 排序即可（本报告的数字即由此得来）
python scripts/guard_service_size.py --report | sort -t"'" -k4 -rn | head
```
