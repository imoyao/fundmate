---
title: 字体方案（方案 B：Inter + Mi Sans）决策评审
date: 2026-09-04
status: 评审意见（供讨论）
关联: docs/design/font-design.md
---

# 字体方案评审意见：Inter + Mi Sans，以及 CDN / 自托管之问

> 本文是围绕 `docs/design/font-design.md`（方案 B，v1.1，状态「批准实施」）的**落地前评审**，
> 结合多多贝前端真实实现与部署拓扑给出。分三部分：① 现有字体实现的「真相核对」；
> ② 对 font-design.md 与项目现状的匹配度判断；③ 你问的两个问题（要不要托管 CDN、Mi Sans 自托管还是 CDN）。

---

## 一、先说一个必须澄清的事实：现在的「Inter 方案」其实并没有真正生效

在讨论 Mi Sans 之前，先核对当前代码里「字体」到底长什么样，因为这会直接影响方案该「从哪起步」。

排查结果（直接读代码，非猜测）：

- `frontend/design.md`（Typography 章节）写明：正文 / UI 用 **Inter**, -apple-system, "PingFang SC", sans-serif；数字用 **SF Mono / JetBrains Mono** + `tabular-nums`。
- `frontend/src/style/colors.css`（第 199 行）定义 `--font-sans: Inter, -apple-system, "PingFang SC", sans-serif;`，`--font-mono: "SF Mono", "JetBrains Mono", monospace`。
- 但**整个仓库没有任何一处 Inter 的 `@font-face`**，也没有任何 Inter / SF Mono / JetBrains Mono 的 woff/woff2 字体文件，更没有 Google Fonts / jsDelivr 之类的 Inter CDN 引用（全局搜索 @font-face、Inter woff、fonts.googleapis 均为零命中）。
- 真正落在 `body` 上的字体栈，是 `frontend/src/style/reset.scss` 里硬编码的：`"Helvetica Neue", Helvetica, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "微软雅黑", Arial, sans-serif`——**这个列表里根本没有 Inter**，而且 reset.scss 不引用任何 CSS 变量。
- 设计令牌 `--font-ui/--font-hero → var(--font-sans)`、`--font-number → var(--font-mono)` 只是定义在 token 层，body / 绝大多数组件并未真正挂到 `var(--font-*)` 上。

结论：**当前全站实际渲染的是「系统字体」**——macOS / iOS 走 PingFang SC，Windows 走 Microsoft YaHei（雅黑），与规范里写的 Inter 没有关系。`tabular-nums` 在 MoneyDisplay 等处是加上了，但由于数字其实没吃到等宽 webfont，落在系统字体上也只是「尽力对齐」。

这带来一个非常关键的含义：font-design.md 说「回退策略：web font 加载失败时用系统字体兜底」，逻辑上没错；但**现状本来就是「只有兜底，没有 web font」**。也就是说，本次换字体不是「从 Inter 平滑切到 Inter + Mi Sans」，而是「从纯系统字体，第一次真正引入自托管 webfont」。起点不同，风险点就不同——第一次引入 CJK webfont 的加载性能、CLS、混排验收，是整个方案最大的未知数，而非「从一种 webfont 换到另一种」。

---

## 二、方案 B（Inter + Mi Sans）与项目现状匹配度的判断

### 2.1 结论：方案本身方向合理，但「批准实施」的落点为时过早

字体选择的**动机和结构是对的**，具体如下：

1. **双字体分工（Inter 管西文/数字、Mi Sans 管中文）** 对多多贝这类「金融账本」高度合适。账本核心是数字表格，`tabular-nums` 等宽对齐是刚需；中文用同一套 CJK 字体保证可读。西文与中文解耦、互不抢位，是成熟做法。
2. **Mi Sans 免费商用、10 字重、含可变字体**，与普惠体同为「免费商用」，取舍看调性偏好，这个层面选谁都可接受；文档 §8 预留热切换契约，工程上是稳健的兜底。
3. **CSS 变量抽象层 + unicode-range 隔离** 的实现思路干净，且与项目「语义 token、禁硬编码」的既有铁律一脉相承，落地阻力小。
4. **署名义务（首页页脚 / 关于页注明 MiSans）** 处理妥当，符合授权条款。

但有几处与现状不匹配、需要先补上的点：

**(a) 文档多处假设「已在使用 Inter webfont」但现实是系统字体。** 例如 §1.3 写「Inter 自托管可变字体」「Inter 永远排在第一位」——但当前 Inter 根本没被加载，若直接照做，等于同时引入两套新 webfont（Inter + Mi Sans）。建议先单独把 Inter webfont 落地并核对一遍数字场景，再叠加 CJK，避免两个变量同时变化难定位问题。

**(b) 缺少落地范围界定。** font-design.md 通篇更像「设计规范定稿」，但没有说清楚：这次改动作用于**哪些站点**？多多贝站点不止应用站前端一个：`app.duoduobei.com`（Vue SPA）、`duoduobei.com` 主站（duoduobei-web 独立仓的纯静态落地页）、`docs.duoduobei.com`（VitePress 文档站）、`jigu.duoduobei.com`（叽咕）。文档里「页脚署名」「探市页」「自选页」明显指应用站，但正文/文档站若也想统一字体，是另一套产物（VitePress 主题字体、静态 HTML）。**建议在规范里显式写明「本规范适用范围 = 应用站 frontend/」**，避免一份规范被误用于所有站点。主站/文档站的字体决策应单独评估（这两类站点更轻、无登录态、更吃首屏性能）。

**(c) 全仓 CJK webfont 体积的现实约束未被量化。** 文档 §5.2 说要子集化、首屏目标 <100KB，方向正确，但正文没有任何一个具体「当前字体全量多大」的数字。实际是：你本地 `D:\MiSans\MiSans` 里**单个静态字重 woff2 就约 4.3–4.8MB**，10 个字重全量约 **47MB**；可变字体 `MiSansVF.ttf` 约 **19.2MB**。CJK 全量无论如何不能直接进前端，子集化不是「优化项」而是「必选项」，且子集化工具链（pyftsubset / fonttools）目前项目里还没接。这一块需要单独排期、验证产物与回退字表，是方案能落地的**前提**而不是收尾项。

**(d) Inter 的「可变字体 + 全字重 100–900」与你本地没有 Inter 文件矛盾。** 文档多处假设有 Inter 可变 woff2。当前仓库既无 Inter 源文件，也无 Inter 的任何引入。落地前要先解决 Inter 字体来源（Inter 为 OFL 许可，可从其官方/上游取 woff2，或用 CDN 但需下到本地自托管）。建议规范里把「Inter 文件来源与获取方式」写清楚，否则无法实施。

### 2.2 一句话建议

**方案方向可以采用，但先做两件事再谈「批准实施」：① 明确作用范围（建议先只做应用站 frontend/）；② 先把 Mi Sans 子集化与 Inter 获取这两条落地路径跑通并验收，再冻结规范。** 在此之前，这份文档更适合标为「设计评审稿」而非「唯一实施标准」。

---

## 三、你问的两个问题

### 问题 1：字体需要「托管 CDN」吗？——不需要刻意引入第三方字体 CDN

先厘清一个常见的概念混淆，它正是你在问题 1、2 之间纠结的根源：

**「字体托管在 CDN」有两种完全不同的含义：**

1. **用第三方字体 CDN / 公共资源 CDN**（Google Fonts、jsDelivr、unpkg、bootcdn 之类）来给你家的字体做分发；
2. **把字体文件放进你自己的产物目录，由你部署的边缘平台（CDN）去分发**——即「自托管文件 + 自家 CDN 分发」。

你的部署拓扑（见 `docs/ops/deployment.md`）：应用站前端跑在 **EdgeOne（主）→ Cloudflare（备）→ Vercel（兜底）** 三平台上，三者的本质都是 CDN / 边缘网络。**只要你把字体文件放进 `frontend/public/fonts/`（或让 Vite 打包进 `dist`），它就会被这三家平台的边缘缓存自动分发**——这就是「自托管 + 你的 CDN」。

所以答案分两层：

**不需要引入第三方字体 CDN（含义 1），应该自托管（含义 2，同时享受自家 CDN）。** 理由与你的部署架构强相关：

- **三平台冗余/降级的前提是「同一份产物」**：EdgeOne → Cloudflare → Vercel 靠 Load Balancer 按健康检查自动降级，每个平台都部署同一份 `dist`。如果字体走第三方 CDN（如 Google Fonts），那么字体资源不在你自家产物里、不在你的降级体系内——EdgeOne 挂了切到 Cloudflare 时，字体仍依赖那个第三方 URL，属于不受控的单点，破坏了三平台「同一份产物」的容灾语义。
- **国内访问的现实**：Google Fonts / 部分 jsDelivr 在国内不稳甚至不可达；bootcdn 这类国内公共 CDN 虽快，但把自家产品字体挂在别人域名上有不可控风险（停服、被墙、URL 失效）。文档 §5.1 说「不依赖外部 CDN（可控、合规、稳定）」，这句判断是对的，只是它把「自托管」和「CDN」对立起来了——其实你的 EdgeOne/Cloudflare 本身就是 CDN，**自托管 + 自家 CDN 不矛盾，反而是同一件事**。
- **合规/署名可控**：Mi Sans 授权要求署名且禁止改编/单独分发；文件放在自己名下、自己在页面署名，最干净。走第三方 CDN 反而难在资源上带署名信息。

结论：**字体要自托管到 `frontend/public/fonts/`（或 `dist`），由 EdgeOne/Cloudflare/Vercel 边缘分发。不引入 Google Fonts / jsDelivr 等第三方字体 CDN。** 这既满足「想用 CDN 加速」，又满足「自托管可控」，两者通过「自家平台即 CDN」统一起来。

### 问题 2：Mi Sans 用你给的 `D:\MiSans\MiSans` 自托管，还是 CDN？

先说结论：**自托管（把子集化后的文件放进 `frontend/public/fonts/`）。不要再纠结「要不要用 CDN」——你三平台部署后，自托管文件天然就被 CDN 边缘分发，二者不冲突。** 需要讨论的不是「自托管 or CDN」，而是**「自托管的话，这份本地文件要怎么处理」**，这才是有决策价值的点。

已核对你给的目录 `D:\MiSans\MiSans`：

- 含 10 个静态字重的 otf / ttf / woff / woff2 四种格式；
- 静态 woff2 每个约 **4.3–4.8MB**；
- 另有一个可变字体 `MiSansVF.ttf`（约 **19.2MB**，在「可变字体」子目录里，文件名带 VF）。

自托管的关键处理路径（也是你要决策的）：

1. **绝不能全量放**：任何一个静态 woff2（~4.6MB）或 19MB 的 VF.ttf 直接进前端，首屏都被拖垮。必须**子集化**——用 `pyftsubset`（fonttools）或 `glyphhanger`，把字体裁到「GB2312 常用字 ~3500 + 数字 + 标点」级别，生成一个几 KB~几十 KB 的 woff2 首屏子集，生僻字再按需懒加载。font-design.md §5.2 的方向正确，就差落地执行和数值验证。
2. **优先做 woff2 子集，别直接用 19MB 的 VF.ttf**：ttf 大且浏览器对 ttf 压缩不如 woff2。官方 MiSans 是按字重分包（你这目录就是 10 个静态字重）；「可变字体」虽灵活，但你这份 VF 只有 ttf 没有 woff2，直接上不划算。稳妥做法是：按文档 §10 开放问题 2 的结论，先取 **Regular(400)、Medium(500)、Semibold(600)、Bold(700)** 四档，各自子集化出 woff2；后续真要上可变再单独要官方 VF.woff2。
3. **入库 + 版本管理**：子集化产物是资产，应放进仓库、由 build 带出（类比 `all_pb.csv` 必须入库的纪律），不要依赖本机 `D:\` 盘路径在构建机上的存在。构建 CI（EdgeOne/Cloudflare/Vercel 都是云端构建）读不到你本机 `D:\MiSans`，所以字体的「源」必须以文件形式进仓库或进对象存储。

一句话：**Mi Sans 自托管到 `frontend/public/fonts/`，用 woff2 子集（先 4 个常用字重），把子集产物作为仓库资产入库；由 EdgeOne/Cloudflare/Vercel 分发（它们就是你的 CDN）。不需要任何第三方字体 CDN。** 你本机 `D:\MiSans\MiSans` 是「母本/源」，用来做子集化，之后不直接进前端产物。

---

## 四、给你的落地建议清单（供讨论，非定稿）

1. 先把 font-design.md 适用范围明确为**应用站 `frontend/`**，主站 / 文档站的字体决策单独再评（它们更轻、更吃首屏、无登录态）。
2. 单独接一条 Inter 的落地（来源、自托管 woff2、数字 tabular-nums 验证），再叠加 Mi Sans，避免变量叠加。
3. Mi Sans 走自托管：子集化（首屏 ~3500 常用字 + 数字 + 标点）→ 4 档常用字重 woff2 → 放 `frontend/public/fonts/` → 入库。
4. 把「Mi Sans 全量静态 ~47MB / VF 19MB」和「子集后目标 <100KB」的数值写进规范，让性能预算有锚点。
5. 16px / 14px 中西文混排验收（§4.2）是上线前的硬门槛，务必在真实环境、而非设计稿里做。
6. 页脚/关于页署名 MiSans（§6），并在规范里定一个「主站 / 文档站若也用 Mi Sans 时各自署名位置」的口径，或明确它们暂不用。
