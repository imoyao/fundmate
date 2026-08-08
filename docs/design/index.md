---
title: 设计哲学与决策记录 (ADR)
---
## 说明

*   **核心受众**：未来的你、可能的技术合伙人

*   **解决的痛点**：忘了当初为什么要“一张表”存所有资产，为什么死活不做自动同步。

*   **建议内容**：

    *   **核心设计原则**：数据主权、合规第一、极简架构。

    *   **关键决策记录**：以“问题 -> 方案 -> 理由”格式记录。

        *   **为什么用“一张表”存储所有资产？**（源于你 `国内投资记账现状.md` 和旧代码的思考）。

        *   **为什么坚决不做自动抓取数据？**（合规红线）。

        *   **自选功能为什么设计为“首页轻量+独立页”？**（直接把你 `自选功能的设计.md` 里的思考放进去）。

        *   **为什么现在用 APIFlask 而不是直接上 FastAPI？**（务实迁移策略）。

    *   **特点**：这是你**产品的灵魂**，让你未来做决策时不重蹈覆辙。

---

## 设计资产索引（design assets）

| 文档 | 内容 | 状态 |
|:---|:---|:---|
| `brand-v1.7.md` | 主站 + 落地页品牌视觉语言（v1.7 终稿：深海叙事 + 珊瑚红镜头转场 + /about 独立页 + 四生物插画映射） | 终稿 |
| `ocean-invest-ecology-illustration-v0.1.md` | 海洋投资生态图鉴插画规范（8 生物 archetype、超椭圆容器、双色、颜色双账） | 规范 v0.1，绘制/互动后置 |
| `about-page-proposal.md` | `/about` 品牌故事页方案评估（推荐轻量排版骨架 + 标准工程件补齐，四拍板已落地） | 提案已采纳 |
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
