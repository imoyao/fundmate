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

---

## 补记（2026-10-11，#2034）：落地决策 2、4 的收尾

本文件 2026-08-13 写下「welcome 不再展示任何结构图」，但该条**当时并未落地**——
「资产构成分布」环形图一直留在 welcome 首屏（#1902 收敛到 `AssetAllocationDonut`、
#1955 把口径从 `market_distribution` 换成 `category_distribution`，两次都在修图，
没人执行"迁走"这一决策）。结果是同一份 `category_distribution` 在 welcome 环形图
与 panorama 瀑布图各画一遍。

#2034 按决策 2/4 收尾，具体口径：

| 动作 | 落点 |
|---|---|
| 删除 welcome 首屏「资产构成分布」环形图 | `WelcomeAssetBoard.vue`；welcome 不再有结构图 |
| 右半边改放**家庭净资产 + 总负债** | 数据来自 `/api/summary/` 的 `net_assets_cny` / `total_liabilities_cny`（**直出，非派生**），替掉原先两处「即将上线」死位 |
| 删除随图失效的 `distributionLogic.ts` 与其单测 | 已无消费方；环形配色本就复用 panorama 桑基的语义色，无独有信息 |
| welcome 不再请求 `/api/summary/distributions/` | 该请求已无消费方，页面少一次请求 |
| panorama 瀑布图标题「总资产构成」→「资产大类构成」→（二轮）「资产大类」 | 与同页桑基「资产构成流向」区分；且瀑布实际含负债，叫「总资产构成」名实不符。二轮去掉「构成」：`AssetInsightPanel` 的切换按钮就写着「资产构成」，标题若为「资产大类构成」，按钮态与标题态几乎同名，切过去像按住没反应 |
| **删除** panorama「资产透视」两张名为「资产分布 / 基金类型分布」的环形图 | 标题与字段对不上（#2032）：左环实为 `type_distribution`（产品类型）、右环实为 `allocation_distribution`（五笔钱）；而本页「多维视图」已有这两套数据的正确命名出口，留着就是同一份数据在首屏重复第二遍。去重优先于改名 |
| 口径 tooltip「按资产大类拆解：…」→「口径：…」 | 「按资产大类 X」正是原卡（GitHub #2034，本文件的镜像来源）里「长得像可切换控件」的病灶措辞，改成说明语气；「拆解」一词在本页已被桑基占用为一张图的名字，一并去掉 |

**为何右半边放净资产而不是别的**：welcome 的职责是「我有多少钱 · 离目标多远」，
而净资产（资产 − 负债）才是家庭资产负债表的真刻度——它此前只出现在 panorama。
结构图让位后由它补位，既避免空洞，也不越界去讲「结构怎么拆」（那仍归 panorama）。

**守门**：`scripts/tests/welcome_structure_dedup.test.js` 钉住「welcome 资产看板
不得再出现结构图」（判据锚在数据源 `category_distribution` / `market_distribution`
与组件 `AssetAllocationDonut` 上，换组件名也拦得住），并自带回退探针。

**留给 panorama 的（不在本卡范围）**：#2032（资产透视两环标题与字段对不上）、
#2033（摘要卡与日历同排的高度冲突）。

### 二轮收尾（同日，#2034 二次核对）

一轮的动作只落了一半，二次核对时发现三处仍在：

1. **「按资产大类拆解」原样跟去了 panorama**：环形图走了，但这句措辞（原卡「问题一」的病灶）
   被写进了瀑布图的口径 tooltip。已改为「口径：各大类金额逐项累加，扣除负债后落到净资产」。
2. **「资产大类构成」与 `AssetInsightPanel` 切换按钮同名**：按钮态写着「资产构成」，
   切到瀑布态后标题是「资产大类构成」，两个字几乎一样，用户看不出已经切过去了。
   标题收敛为「资产大类」，与卡片内 (i) 口径说明分工互补。
3. **「资产透视」两张环的名与字段仍然对不上**（#2032 范围）：本页「多维视图」已能
   分维度看同一批数据，标题是对的，故按「同一口径只出现一次」删除该区块，
   而不是顺着现有实现改名。

**判据**：同一份数据在一个视口里第二次出现，**先问能不能去掉**，再问怎么命名。
