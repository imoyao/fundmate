# Issue #1155 回填可行性 + 基金公司/基金经理数据架构核查

> 核查日期 2026-08-29。范围：GitHub issue #1155、后端数据模型与同步抓取链路、数据域（Supabase vs SQLite）归属。
> 结论先行：#1155 可解决且低风险；基金公司/基金经理"表都建了"，但抓取与域归属存在三处需要决策的不一致。

## 一、Issue #1155 能否优化/解决

可以，且范围清晰、风险低。

根因已明确：`fund_type_id` 字段本身就存在于 `funds` 表（`backend/app/domains/funds/models.py:80`，外键指向 `fund_types.id`），参照表 `fund_types` / `fund_varieties` 也已存在且注册在 market 域（`db_factory.py:60-61`）。问题的不是"没设计"，而是"没回填全量"。

现状缺口来自抓取链路的覆盖不足，而非机制缺失：

- `fund_detail_enrich_job.py:138-140` 在做 `fund_type_id` 回填，数据源是 `akshare_adapter.fetch_fund_detail` 抓取的 `fund_info_ths` 的「投资类型/基金类型」字段（`akshare_adapter.py:314-316`，存为 `fund_type_raw`），再经 `_get_or_create_fund_type`（`fund_detail_enrich_job.py:299`）映射到 `fund_types.id`。但该 enrich 是增量式、只处理它触达的基金子集，所以全量 26938 只标了约 11.3%。
- 全量列表接口 `ak.fund_name_em()`（`akshare_adapter.py:200-224`）其实对全部 26938 只基金都返回了「基金类型」字段（`row['基金类型']`，如"货币型"），但当前这个字段只在 `search_funds` 的 akshare 分支做搜索兜底（`fund_service.py:134-169` 的 `_judge_money_fund` 三态判定），**没有回写 `fund_type_id`**——这正是 issue 里点出的"绕过去没治好"。

建议的根治路径（与 issue 一致，且代码已具备大半骨架）：

1. 新增一个批量回填任务，用 `fund_name_em` 的「基金类型」一次性映射 `fund_types.id` 并 `UPDATE funds SET fund_type_id=? WHERE fund_type_id IS NULL`。类型字符串→id 的映射复用 `_get_or_create_fund_type` 即可，无需新写解析。
2. 把该任务注册进 `DataSyncOrchestrator`（参考 `amac_institution_job`、`fund_manager_job` 的注册方式 `orchestrator.py:34/114`）。
3. 回填完成后，`_judge_money_fund` 的第 2 条（万份收益实测）与第 4 条（名称兜底）降级为纯兜底，主判据回归 `fund_type_id == 6`，与 issue"收益"段一致。

收益：除"活期+"搜不到 026029 这类直接痛点外，所有依赖基金类型的筛选/统计/风险展示整体准确度提升，且不再被名称启发式绑架。该任务纯属 market 域数据回填，不碰 user 域、不碰 Supabase，可独立成 `feat(data)` 提交。

## 二、基金公司 / 基金经理：现在到底有没有设计、有没有抓取

结论：表都设计了，但"基金公司"这个概念在代码里其实分裂成**两个互不相干的表**，而"基金经理"的抓取任务当前是**被跳过**的。

### 基金公司（两张表，两个域）

第一张 `fund_companies`（market 域，`funds/models.py:25-31`）：基金资料维度的公司，字段 `code/name/full_name/scale`。由 akshare 抓基金列表/详情时的 `company_name` 建立（`fund_list_job.py`、`fund_detail_enrich_job.py:327-334` 的 `_get_or_create_company`），被 `funds.company_id` 外键引用（`funds/models.py:82,94`）。这张是**活跃且被真正使用**的。

第二张 `fund_management_companies`（user 域，`positions/models.py:193-206`）：公募基金管理人权威名录（AMAC 公示），字段 `house_name/register_addr/office_addr/website/phone/is_active`。由 `amac_institution_job.py` 分页抓 AMAC 接口落库，并把不在公示名单的机构置 `is_active=False`。**但关键问题：positions/ledgers 主表里没有任何指向它的外键**——`db_factory.py:86` 的注释写着"被 positions 引用，随 user 域"，而全仓搜索 `positions`/`ledgers` 模型并无该表外键（详见第三节）。

你在账本里看到的"基金公司"，实际只是：
- `ledgers/constants.py:28` 里 `ORG_TYPE_TO_CHANNEL_CATEGORY` 字典的一个**机构类型标签字符串**（`'基金公司': 'other'`），用于渠道分组，不是数据库外键；
- `position_import_meta.fund_manager`（`positions/models.py:127`，`String(100)`，免费文本），来自 E 账户导入快照的「基金管理人」列，是溯源文本，不是外键，也不是经理表/公司表的引用。

所以"账本里已有基金公司"这个说法要修正：账本侧只有**字符串常量 + 快照文本**，真正的 `fund_management_companies` 表在 user 域是"建了但孤儿"，positions 并未真正引用它。

### 基金经理（表有，抓取被跳过）

`managers` + `fund_managers`（均 market 域，`funds/models.py:57-69, 102-109`）：经理主表含 `mgr_code/name/mgr_type/company_id/appointment_date/sum_scale/best_return/avatar_url`，关联表 `fund_managers` 含 `fund_id/mgr_id/is_classic/start_date/end_date`，与 `funds` 经多对多关联。设计是完整的。

抓取链路也存在：`akshare_adapter.py:239-295` 用 `ak.fund_manager_em()` 全量缓存并生成 `mgr_code = sha256(name+company)[:12]`；落库 job 是 `fund_manager_job.py`（`FundManagerSyncJob`）。**但 `fund_manager_job.py:2` 注释写明"当前接口不稳定，暂时跳过"**，逻辑里插入 `Manager` 与关联的代码虽在，编排器也注册了（`orchestrator.py:114`），实际运行时并不抓经理数据。也就是说：基金经理"表设计齐全、抓取代码写好、但线上不跑"——这是当前最实在的缺口，不是"没设计"，而是"没启用"。

## 三、该存 Supabase 还是 SQLite：数据域归属判定

项目的硬规则是"数据域以 `db_factory.DATA_DOMAIN_REGISTRY` 为准，跨域零外键零 join"（`AGENTS.md` 双引擎硬规则）。归属决策树：含 `user_id`/`family_id` 或"被 user 域表外键引用"→ user 域（生产 Supabase）；公开、读多写少、无限膨胀→ market 域（生产 Turso，本地 SQLite）。

把本次涉及的表按这个规则排一遍：

| 表 | 当前注册域 | 数据性质 | 抓取状态 | 域归属是否自洽 |
|---|---|---|---|---|
| `fund_companies` | market | 公开基金资料 | 活跃（akshare） | 自洽，应为 market/Turso |
| `fund_types` / `fund_varieties` | market | 公开分类参照 | 部分（88.7% 空） | 自洽，应为 market/Turso |
| `managers` / `fund_managers` | market | 公开经理名录 | job 被跳过 | 自洽，应为 market/Turso |
| `fund_management_companies` | user | 公开 AMAC 名录 | 活跃（AMAC）但无 positions FK | **不自洽，需决策** |

直接回答你的疑问：**基金公司（akshare 那张 `fund_companies`）和基金经理（`managers`/`fund_managers`）都属于 market 域，生产应落 Turso、本地落 SQLite，不应进 Supabase**——它们是无用户归属的公开参照数据，放进 Supabase（user 域）反而违反双引擎规则、还会带来跨域 join 的麻烦。

真正需要决策的是 `fund_management_companies`：它被注册为 user 域（隐含"将来 positions 要引用它"的前提），但 positions 至今没引用它。两个走向二选一：
- 走向 A（推荐，若坚持它属于公开名录）：把它重新注册为 market 域，和 `fund_companies` 合并或并列作为公开基金管理人名录，落 Turso。前提是放弃"positions 引用公司表"的设想，账本侧继续用 `position_import_meta.fund_manager` 免费文本做快照溯源即可。
- 走向 B（若确实要让持仓关联到权威管理人）：在 `positions` 上加外键指向 `fund_management_companies`（保留 user 域），让 `db_factory.py:86` 的注释从"文档遗留"变成"真实约束"。但这会引入 user 域引用一张本质是公开名录的表，需评估是否值得。

我的建议：基金公司/经理这类公开参照数据一律走 market 域（Turso/SQLite）；user 域（Supabase）只放真正带 `user_id`/`family_id` 的私有数据。因此 `fund_management_companies` 优先考虑走向 A 重归 market 域，并校准 `db_factory.py:86` 那条已过时的注释。

## 四、建议的下一步（按优先级）

1. 先解决 #1155：实现 `fund_name_em` 全量回填 `fund_type_id` 的 sync job，注册进编排器。低风险、纯 market 域、可独立 PR。这是你提到的"回填"最直接的落点。
2. 决策 `fund_management_companies` 的域归属（走向 A/B），并修正 `db_factory.py:86` 注释漂移——这是当前唯一违反双引擎自洽的点。
3. 评估是否 revive `fund_manager_job`（akshare 接口稳定性若已恢复则启用，否则标注为 tech-debt 而非静默跳过），让 `managers`/`fund_managers` 真正有数据。

## 附：关键证据定位

- `funds.fund_type_id` 字段与外键：`backend/app/domains/funds/models.py:80-82`
- 类型回填逻辑：`backend/app/services/sync/jobs/fund_detail_enrich_job.py:136-152, 299-319`
- 全量类型字段未回写：`backend/app/services/sync/adapters/akshare_adapter.py:200-224`（仅搜索兜底用）
- 货基三态判定：`backend/app/services/fund_service.py:134-169`
- 基金公司双表：`fund_companies` `funds/models.py:25-31`；`fund_management_companies` `positions/models.py:193-206`
- 基金经理双表：`managers`/`fund_managers` `funds/models.py:57-69, 102-109`
- 经理抓取被跳过：`fund_manager_job.py:2` 注释；注册 `orchestrator.py:114`
- 域注册表：`backend/app/core/db_factory.py:56-98`
- 账本侧"基金公司"仅字符串/文本：`ledgers/constants.py:28`、`positions/models.py:127`


---

## 结论回填（2026-09-10）

本文第二节提出的「`fund_management_companies` 归属待决策（走向 A 重归 market 域 / 走向 B 在 positions 上加外键）」**已按第三条路径收束**：**合并进 `fund_companies` 后删除死表**。

- 死表判定复核通过：唯一写方 `amac_institution_job`，**零读者、零外键、零接口**；`db_factory` 那句「被 positions 引用」确认为**假注释**（positions 只 FK `sales_institutions`）。
- AMAC 基金管理人公示信息（全称/注册地址/办公地址/官网/客服电话）改为 enrich 进 `fund_companies`（`full_name` + 4 个新列 + `is_active`），`name` 语义定为**简称**（界面默认显示）、`full_name` 为**权威全称**。
- 未新建行：AMAC 不提供东财 8 位编码，硬造编码等于给公司主数据开第二个写者——这正是死表当初诞生的机制。
- 顺带修掉的真实缺陷：`fund_companies` 内 8 组「简称行 + 全称行」重复实体（成因是四个 job 各自「查名建行」，东财给简称、akshare 给全称），招商基金的经理被分裂挂在 103 + 9 两行；现已收口唯一写入口 `company_resolver.get_or_create_fund_company` 并合并历史数据。
- 决策全文见 `docs/spec/decisions.md` 2026-09-10 行；迁移脚本 `backend/scripts/migrate_fund_company_merge.py`。
