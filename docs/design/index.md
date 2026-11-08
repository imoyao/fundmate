---
title: 设计哲学与决策记录 (ADR)
---
## 说明

* **核心受众**：未来的你、可能的技术合伙人

* **解决的痛点**：忘了当初为什么要“一张表”存所有资产，为什么死活不做自动同步。

* **建议内容**：

    * **核心设计原则**：数据主权、合规第一、极简架构。

    * **关键决策记录**：以“问题 -> 方案 -> 理由”格式记录。

        * **为什么用“一张表”存储所有资产？**（源于你 `国内投资记账现状.md` 和旧代码的思考）。

        * **为什么坚决不做自动抓取数据？**（合规红线）。

        * **自选功能为什么设计为“首页轻量+独立页”？**（直接把你 `自选功能的设计.md` 里的思考放进去）。

        * **为什么现在用 APIFlask 而不是直接上 FastAPI？**（务实迁移策略）。

    * **特点**：这是你**产品的灵魂**，让你未来做决策时不重蹈覆辙。

---

## 设计资产索引（design assets）

| 文档 | 内容 | 状态 |
|:---|:---|:---|
| `navigation-ia.md` | 导航信息架构：按**财务动作**切四个顶级（资产概览 / 资产管理 / 记账中心 / 账本精灵）；菜单 4 字规则与豁免；面包屑改读菜单树（`route.matched` 因路由拍平而恒错）与去掉过渡动画的实证；单子项模块拍平（禁止 `showParent`）；守卫清单与反向约束 | 定稿（2026-10-30） |
| `brand-v1.7.md` | 主站 + 落地页品牌视觉语言（v1.7 终稿：深海叙事 + 珊瑚红镜头转场 + /about 独立页 + 四生物插画映射） | 终稿 |
| `ocean-invest-ecology-illustration-v0.1.md` | 海洋投资生态图鉴插画规范（8 生物 archetype、超椭圆容器、双色、颜色双账） | 规范 v0.1，绘制/互动后置 |
| `about-page-proposal.md` | `/about` 品牌故事页方案评估（推荐轻量排版骨架 + 标准工程件补齐，四拍板已落地） | 提案已采纳 |
| `transaction-flow-redesign.md` | 交易流水桌面端重设计：三条横带（页头 / 汇总条 / 筛选+列表）、表格 11 列 + 流水线 7 列栅格、账户轴与月轴、持仓三态语义（`held`/`cleared`/`account`）与「已清仓」胶囊取代「已删除」+ 整格置灰、状态静默化、改动映射与 12 条验收判据。原型 `transaction-flow-redesign-prototype.html`（可交互单文件） | **已实施（v1.2，2026-11-01）**：三条横带全部落地——汇总条接 `GET /api/transactions/summary/`（净投入公式在文档 §四，前端零求和），行展开详情按需取（`GET /api/transactions/{id}/`） |
| `product-detail-drawer.md` | 产品详情抽屉统一规范：唯一外壳（`components/ProductDrawer`）、720px 单宽、24/14/13 三档数字、13/500 区块标题（不复用 `SectionHeader`）、唯一出口在 sticky footer、内容删减 6 项 / 合并 7 项、组合详情页成分基金行栈 | 定稿并已实施（2026-11-01） |
| `components.md` | 组件使用规范（设计语言**实现层**）：强制复用清单、组件 props / 阈值 / 栅格类名 / 页面级约束；`frontend/design.md` 只留令牌与全局原则，二者分工不重叠 | 基线（随实现更新） |
| `font-design.md` | 网站字体规范 v1.2（方案 B：Inter + Mi Sans）：符号归属、`@font-face` 热切换机制（预留给阿里巴巴普惠体 3.0 做 A/B 对比）、方案回切协议 | 评审后待工程落地 |
| `trade-rules.md` | 交易规则引擎决策 v1.0：买入合并校验、北交所 / 可转债规则、一手规则（100 份 vs 10 张）的判定链 | 决策基线（2026-06-13） |
| `si-bi-qian.md` | 「四笔钱」为何要扩成「五笔钱」：期权 / 虚拟币等高波动博弈类资产的风险来源与资金管理属性不同，不能并入「长期投资」 | 结论已采纳 |
| `account-dialog-form.md` | 账户类表单弹窗**宽度档位与滚动契约**：四个宿主（创建 / 编辑 / 导入向导建账户 / 资产录入建账户）共用 `--dialog-width-form` / `--dialog-width-compact` / `.form-dialog`；含改前量测基线与档位判定 | 已实施（2026-11-08） |
| `reconcile-workbench-redesign.md` | 对账中心重构（第一版）：根因是信息架构按后端域编号组织 + 数据库字段直渲；按财务动作重排、P0+P1+P2 一轮做完 | 已实施（2026-11-07，PR #2974） |
| `reconcile-workbench-redesign-v2.md` | 对账中心第二轮（用户视角）：单条待办内的上下文 / 术语 / 口径与长列表交互；右侧抽屉 + 队列分页已拍板，落地结果以 §11 为准 | 已实施（2026-11-07） |
| `my-favrivate.md` | 自选功能设计（对话体原始稿）：自选放首页还是独立页的取舍依据、股票 / ETF / 可转债 / 指数与「基金经理」追踪的分类 | 设计输入（#807 跟踪） |
| `welcome-greeting-spec.md` | 首页欢迎语位置规范 v1.5：内容 / 状态 / 交互；不做数据复读机（总资产、投资以来收益、XIRR 已在底部卡片），只放底部没有、用户可控、无情绪压力的数据 | 规范 v1.5 |
| `ledger-merge-design.md` | 账本合并（批量迁移持仓）**数据正确性**：预览→确认→提交、守恒校验、回滚；账户模型本身以 `docs/working-notes/ledger-channel-category-redesign-2026-08-28.md` 为唯一权威（本文不定义模型） | 待实现（#1089） |
| 主站实现（`landing.html` / `about.html` / `story.html`） | 按 brand-v1.7 落地的静态营销三页：落地页含 eco 无缝横幅；about 章节结构与 `docs/about.md` 对齐（文案可润色）；story 为深海叙事页。共享令牌源 `site/style.css`（镜像 frontend `colors.css`）。构建：`scripts/build-landing.mjs` + `landing.content.yml` | ✅ 已落地（2026-08-05，about-us 页已删除，footer 含意见反馈/隐私政策链接） |

### 设计文档 ↔ issue 反链（2026-08-08 triage）

| issue | 主题 | 象限 | 状态 | 对应设计文档 |
|:---|:---|:---|:---|:---|
| [#807](https://github.com/imoyao/fundmate/issues/807) | 自选页面实时估值功能设计文档 v2.0 | **Ⅰ 重要且紧急** | 部分实现 / 偏离文档（三组件缺失） | 设计正文在 issue 内；关联 `my-favrivate.md`、`docs/features/watchlist.md` |
| [#782](https://github.com/imoyao/fundmate/issues/782) | 资产简记和投资记录页面设计 | Ⅱ 重要不紧急 | 设计文档基线 | 设计正文在 issue 内；关联 `docs/features/holding-record.md` |
| [#808](https://github.com/imoyao/fundmate/issues/808) | 「探市」体验版设计文档与任务计划 | Ⅱ 重要不紧急 | 设计文档基线 | 设计正文在 issue 内；关联 `docs/spec/temperature-architecture-plan.md` |
| [#817](https://github.com/imoyao/fundmate/issues/817) | 鹦鹉螺 nautilus 作为 logo | Ⅳ 不重要不紧急 | 部分实现（正式稿未产出、清晰度待验证、跨站未统一） | `brand-v1.7.md` §5 / §实现对齐清单 |

> **维护约定（文档↔issue 双向交叉引用）**：设计文档须回链其跟踪 issue，issue 评论区须标注对应文档路径；两侧描述不一致时按「文档↔历史差异必须拉平」处理——要么改文档、要么开 issue 跟踪，不留悬空描述。反链总表见 `docs/spec/roadmap.md` §3。
>
> **注意**：#807 / #782 / #808 的设计正文目前**只存在于 GitHub issue**，尚未沉淀为 `docs/design/` 下的文档；待其落地或定稿后再迁入本目录并在上表回填文件名。

> 关联：about 页的生态装饰条、未来空状态/新手引导插画均以 `ocean-invest-ecology-illustration-v0.1.md` 为生物隐喻唯一来源；视觉约束（超椭圆、双色、禁 3D）与 `brand-v1.7.md` §5/§9 一致。插画实际绘制与互动开发按该规范 §八 排期后置。盈亏语义走独立色板，品牌珊瑚红不得承担涨跌（见插画规范 §六 颜色双账、brand-v1.7 §3.1）。
