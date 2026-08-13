# 投资概览 vs 资产总览 · 页面分工决策（2026-08-13）

## 背景

`welcome/index.vue`（投资概览 / 「家庭资产看板」首屏）与 `AssetPanorama.vue`（资产总览 / 「资产配置」）长期存在概念混淆：五笔钱（Allocation）、投资目标（Portfolio/Objective）、心理账户被搅在一起，且「资产构成分布」环形图错接成品种/市场分布、心理账户卡片用的是 mock 五笔钱名字。本轮通过核对 GitHub Issue #859、Discussion #152、后端 `portfolios` 模型与 `docs/spec/data-model.md` §5.11，把概念与两页分工理清。

## 概念裁定（详见 concepts.md）

- **投资目标 ≠ 独立实体**：原 `objectives` 表 / `position_objectives` 多对多方案已否决且未落地；"投资目标"语义降级并入 `Portfolio.purpose` 字段。Objective 与 Allocation 平行，不存在"Objective 是五笔钱的细化"的嵌套。
- **五笔钱（Allocation）= 客观风险分层**：系统按产品风险等级+期限自动归类（活钱/稳健底仓/长期增值/高风险博弈/保险保障），不可自定义。
- **心理账户 / Portfolio（投资目标）= 主观目标**：用户自建的人生目标（养老金/教育/买房），经 `Portfolio.purpose` 承载。

## 两页分工（最终结论）

| 页面 | 定位 | 承载概念 | 性质 |
|---|---|---|---|
| 投资概览（welcome） | 我想过什么样的人生？设了什么目标？离目标多远？ | 心理账户/Portfolio（投资目标）+ 收益·XIRR·市场温度·财务健康 | **理想 / 目标 + 表现进度** |
| 资产总览（panorama） | 为了目标，怎么规划钱、走哪条路径？ | 五笔钱（配置目标）、产品类型、账户、资产端/负债端 | **生活 / 方法（composition 拆解）** |

**关键共识**：分页原则从最初的"客观 vs 主观"修正为 **"拆解（composition）vs 表现+目标"**。用户的大白话比喻更准确——投资概览是"理想"（想过的人生、设的目标、离目标多远），资产总览是"生活和方法"（怎么把钱铺成通往目标的路）。**五笔钱是"方法/路径"（按风险分层支撑目标），所以归资产总览；心理账户是"理想"（目标本身），所以归投资概览**，两者不再打架。

## 落地决策清单（待开工）

1. **welcome 顶部「家庭资产看板」大卡片保留**（净资产快照：总资产/负债/净资产/盈亏 + 本月本年变动）。它与 panorama 的数据重复通过"视角不同"消弭：welcome 回答"我有多少钱、今天涨没涨"，panorama 回答"结构健不健康"。
2. **welcome「资产构成分布」环形图（品种/市场分布）迁至 panorama**，welcome 不再展示任何结构图。
3. **welcome「心理账户」卡片**：保留名字（"投资目标"太干、不搭主题），数据源从 `overview.ts` 的 `mockPsychAccount` 换成真实 `Portfolio`（按 `purpose` 聚合），并加一句小提示："按人生目标把钱分桶，帮你看清每笔钱在为什么而存"。
4. **panorama 中部加并排双环**：左「五笔钱配置（配置目标）」、右「品种构成（股票/基金/房产/贵金属，从 welcome 迁来）」，均用现成数据（`allocation_distribution` / `market_distribution`）画 donut。
5. **panorama 四个维度（资产端/负债端/产品类型/账户/配置目标）各加注释条**，其中"配置目标"标签写明"= 五笔钱"，消除"配置目标到底是不是五笔钱"的模糊。

## 参考

- GitHub Issue [#859](https://github.com/imoyao/fundmate/issues/859)、Discussion [#152](https://github.com/imoyao/fundmate/discussions/152)
- `docs/features/concepts.md`（概念 SSOT）
- `docs/features/account.md`（Objective 章节已废弃）
- `docs/spec/data-model.md` §5.11 投资组合
