这是为你整合生成的**完整版《多多贝 网站字体规范（方案 B：Inter + Mi Sans）》**。

我已将上一轮的**热切换机制、符号归属补全、方案回切协议**以及**开放问题的参考答案**全部合并进去，并理顺了章节编号和逻辑层级。这份文档现在可以直接交付给前端开发，也可以作为后续对比普惠体的评估基准。

---

# 多多贝 网站字体规范（方案 B：Inter + Mi Sans）

> **版本**：v1.2（评审修订稿） · **日期**：2026-09-04 · **状态**：**评审后待工程落地**
> **关联规范**：《多多贝·品牌视觉与落地页规划 v1.7》《多多贝 设计语言 v2.3.4》
> **决策路线**：本文档落地「Inter（西文/数字/UI）+ Mi Sans（中文）」双字体方案。
> **热切换预留**：已通过 CSS 变量抽象层预留「一键切换至阿里巴巴普惠体 3.0」的工程能力（见 §1.4），便于后续 A/B 对比与设计评审。
> **适用范围（v1.2 明确）**：本规范仅适用于**应用站前端 `frontend/`**（`app.duoduobei.com` 的 Vue SPA）。主站 `duoduobei-web`、文档站 `docs.duoduobei.com`、叽咕 `jigu.duoduobei.com` 的字体决策需另行评估，不适用本文件。
> **v1.1 → v1.2 修订摘要**：① 状态由「批准实施」降为「评审后待工程落地」——落地前须先跑通 Inter 获取与 Mi Sans 子集化两条路径（§11.2 阻塞项）；② 明确适用范围仅为应用站前端；③ 字体变量落地命名与现有 token 体系对齐（§11.3）；④ 补充 Mi Sans 全量体积与子集化性能预算的实测数值（§11.4）。

---

## 0. 决策快照

| 项 | 结论 |
|---|---|
| **西文 / 数字 / UI 字体** | **Inter**（自托管可变字体） |
| **中文字体** | **Mi Sans**（小米，自托管，免费商用） |
| **数字对齐机制** | `tabular-nums` 由 **Inter** 承担（中文字体通过 `unicode-range` 隔离，不参与数字渲染） |
| **字体栈（抽象层）** | `--font-latin: "Inter", system-ui, sans-serif;`<br>`--font-cjk: "MiSans", "PingFang SC", "Microsoft YaHei", sans-serif;`<br>`--font-base: var(--font-latin), var(--font-cjk);` |
| **Mi Sans 授权** | 全球免费商用 ✅；**须在产品内署名**；禁止改编字体文件（子集化合规） |
| **热切换（备选）** | 已预留 CSS 类 `font-compare-a`，可零成本全局切换至 **阿里巴巴普惠体 3.0**，便于对比测试（见 §8 回切协议） |
| **一句话定位** | 字体退居「清晰阅读」的功能角色，温暖与品牌记忆由珊瑚红 / 鹦鹉螺 / 超椭圆（n=3）承载 |

**为什么是 Mi Sans（而非普惠体 / 翔鹤黑）**：Mi Sans 的「椭圆元素 + 柔线」设计语言与品牌「Alive 生命感」（几何来源 n=3 超椭圆）存在隐性共鸣【品牌视觉 §1.1】；10 字重 + 可变字体提供最丰富的层级；同为免费商用，无预算门槛。已知代价是「小米系统字体」品牌联想与署名义务，详见 §7 风险缓解与 §8 回切协议。

---

## 1. 字体栈、回退策略与符号归属

### 1.1 核心原则

- **Inter 永远排在第一位**，负责所有拉丁字母、数字、货币符号（半角）、标点。
- **Mi Sans 通过 `unicode-range` 仅覆盖中文区块**，从机制上保证拉丁/数字不会落到 Mi Sans（即使 Mi Sans 自带拉丁字形）。这是「拉丁=Inter、中文=Mi Sans」的最干净实现，不依赖字体栈顺序的运气。
- 系统字体（`PingFang SC` / `Microsoft YaHei` / `system-ui`）作为 **web font 加载失败时的兜底**，保证任何设备可读。

### 1.2 CSS 字体变量抽象层（热切换基础）

> **工程铁律**：业务代码**只引用 CSS 变量**，严禁直接硬编码字体名称。这为后续切换至普惠体（方案 A）提供零成本热插拔能力。

```css
:root {
  /* ---- 抽象层（业务代码只认变量） ---- */
  --font-latin: "Inter", system-ui, sans-serif;              /* 拉丁/数字/半角符号 */
  --font-cjk: "MiSans", "PingFang SC", "Microsoft YaHei", sans-serif; /* 中文 */

  /* ---- 组合栈（业务场景直接调用） ---- */
  --font-base: var(--font-latin), var(--font-cjk);           /* 全局默认 */
  --font-num: var(--font-latin);                             /* 数字专用（强制 Inter） */
}

/* ---- 备选对比开关（普惠体 3.0） ---- */
body.font-compare-a {
  --font-cjk: "Alibaba PuHuiTi 3.0", "PingFang SC", "Microsoft YaHei", sans-serif;
}
```

> 设计师/测试人员仅需在 `<body>` 添加 `font-compare-a` 类，即可全站瞬时切换至普惠体进行视觉对比，无需改动任何业务组件代码。

### 1.3 @font-face 声明（自托管 + unicode-range 隔离）

```css
/* —— 1. Inter：西文 / 数字 / UI，可变字体 —— */
@font-face {
  font-family: "Inter";
  src: url("/fonts/inter-variable.woff2") format("woff2-variations");
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;            /* 避免 FOIT，先系统字后平滑替换 */
}

/* —— 2. Mi Sans：中文，仅覆盖 CJK 区块，绝不拦截拉丁 —— */
@font-face {
  font-family: "MiSans";
  src: url("/fonts/misans-variable.woff2") format("woff2-variations");
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;
  unicode-range:
    U+3000-303F,                 /* CJK 符号和标点（含全角、。、！） */
    U+3400-4DBF,                 /* 扩展 A */
    U+4E00-9FFF,                 /* 中日韩统一表意文字（主） */
    U+F900-FAFF,                 /* 兼容表意文字 */
    U+FF01-FF0F,                 /* 全角 ！＂＃＄％＆＇（）＊＋，－．／ */
    U+FF1A-FF1F,                 /* 全角 ：；＜＝＞？ */
    U+FF20-FF3F,                 /* 全角 ＠Ａ－Ｚ［＼］＾＿ */
    U+FF40-FF5E,                 /* 全角 ｀ａ－ｚ｛｜｝～ */
    U+FFE0-FFE6;                 /* 全角货币符号（￠￡¤￥｜§）——此处交 Mi Sans 匹配中文语境 */
}
```

> **关键效果**：半角 `%`、`$`、`,`、`.` 永远由 Inter 渲染（天然等宽）；全角 `％`、`￥`、`。` 由 Mi Sans 渲染（与中文排版语境匹配），两者各司其职，互不抢位。

---

## 2. 字重与字阶映射

### 2.1 映射规则

- Inter 与 Mi Sans 均支持 **100–900 全字重 + 可变字体**，按**数值字重直接对齐**（Inter 400 ↔ Mi Sans 400）。
- 同一层级的中英文使用**相同数值字重**，从字重维度保证协调；x-height / 视觉重量差由 §4 混排验收兜底。
- 正文统一 **Regular(400)**，标题逐级加重；**Bold(700) 以上仅用于标题**，正文不用重字重（避免「硬」感，呼应温暖调性）。

### 2.2 字阶表（与《设计语言》L51–L58 对齐确认）

| 层级 | 用途 | 字号 | 行高 | Inter 字重 | Mi Sans 字重 | 备注 |
|---|---|---|---|---|---|---|
| **Display** | 首页大标题 / Hero | 32px（移动）/ 40px（桌面） | 1.25 | 700 | 700 | 对应 `--text-display`【设计语言 L52】 |
| **H1** | 页面主标题（如「探市」页头） | 28px | 1.3 | 700 | 700 | 规范外新增，仅作页面级标题 |
| **H2** | 章节标题（如「温度解读」） | 24px | 1.4 | 600 | 600 | 对应 `--text-title`【设计语言 L53】 |
| **H3** | 卡片 / 区块标题 | 20px | 1.5 | 600 | 600 | 对应 `--text-heading`【设计语言 L54】 |
| **Body** | 正文 | 16px | 1.6 | 400 | 400 | 主要阅读场景【设计语言 L49-L50】 |
| **Small** | 辅助说明 / 表头 | 14px | 1.5 | 400 | 400 | 对应 `--text-small`【设计语言 L57】 |
| **Label** | 标签 / Badge | 13px | 1.4 | 500 | 500 | 对应 `--text-label`【设计语言 L58】 |
| **Micro** | 极小标注（仅限数字场景） | 12px（仅数字）/ **14px（中文）** | 1.4 | 400 | 400 | **中文强制禁低于 14px**【设计语言 L49-L50】 |

---

## 3. 数字与表格对齐规则（tabular-nums）

### 3.1 核心原则

- **数字、货币、百分比、收益率、数量**一律由 Inter 渲染，并强制 `tabular-nums` 等宽对齐【设计语言 L46】。
- Mi Sans **不参与数字渲染**（见 §1.3 `unicode-range`），因此其是否支持 `tnum` 对账单本对齐**无影响**。
- 等宽数字保证列对齐：同一列的金额个位对齐、小数位对齐，账本可读性关键。

### 3.2 CSS 规则

```css
/* 全局：账本类界面默认等宽数字 */
body.ledger,
.num,
.amount,
.rate,
.quantity {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;   /* 双写兼容旧引擎 */
  font-family: var(--font-num);      /* 确保 Inter 优先 */
}

/* 千分位 / 货币符号由 Inter 处理，无需额外规则 */
```

### 3.3 场景清单

| 场景 | 字体 | 对齐 |
|---|---|---|
| 总资产、持仓市值 | Inter + `tabular-nums` | 右对齐，个位对齐 |
| 收益率（含 +/-、%） | Inter + `tabular-nums` | 右对齐 |
| 交易流水金额 | Inter + `tabular-nums` | 右对齐 |
| K 线 / 数值轴标签 | Inter + `tabular-nums` | 右对齐 |
| 中文标签 / 字段名 | Mi Sans | 左对齐 |

---

## 4. 中西文混排协调（验收标准）

### 4.1 风险

Mi Sans 中文字身与 Inter 拉丁的 **x-height、视觉重量、重心**存在差异，混排时可能出现中文显大 / 拉丁显小、基线不齐。这是双字体方案的必做验收项。

### 4.2 验收清单（上线前必过）

在 **16px / 14px** 两档字号下检查：

- [ ] 中文与相邻拉丁字符**同基线**，无上下错位；
- [ ] 中文视觉重量与同字重 Inter 拉丁**平衡**（中文不显胖、拉丁不显瘦）；
- [ ] 行高一致，多行混排无跳行；
- [ ] 数字与中文混排（如「持仓 1,234 股」）视觉连贯；
- [ ] 苹果设备（PingFang 兜底）与 Windows 设备观感接近。

### 4.3 调参手段（若验收不通过）

```css
/* 若中文显大：中文段落字号下调，或限制中文最大字号 */
:lang(zh),
.zh-text {
  font-size: 0.96em;          /* 相对英文基准微调，数值须验收冻结 */
}

/* 若拉丁显小：Inter 侧微调字距 */
:lang(en),
.num {
  letter-spacing: 0.01em;
}
```

> 调参统一走 CSS 变量，避免散落；验收通过后冻结数值，**禁止在页面级单独覆写**。

---

## 5. Web 交付与性能

### 5.1 必须自托管

- Mi Sans / Inter **均自托管**于 `/fonts/`，不依赖外部 CDN（可控、合规、稳定）。
- 字体文件格式统一 **woff2**（体积最小、渲染快）。

### 5.2 子集化（CJK 体积控制）——v1.2 实测修订

CJK 全字重体积巨大，必须子集化，否则首屏被拖垮。**v1.2 实测结论（2026-09-04）**：
文档 v1.1 声称「首屏子集 < 100 KB」在 CJK 现实下不成立——中文字形经 woff2 压缩后每字仍约 140 B，工程实测：

| 字表策略 | 字数 | 单字重 woff2 体积 |
|---|---|---|
| 仅 UI 静态源码字（1402 字） | 1,402 | ~194 KB |
| **GB2312 一级 + UI + 符号（现行决策）** | **3,823** | **~560 KB** |

**决策（2026-09-04 采纳）：采用 GB2312 全字表体验优先策略**——
- **字表 = GB2312 一级汉字（3755）+ 前端源码扫描用字 + 全角符号/标点**，共 3,823 字，覆盖日常界面文案与用户动态内容（自选备注 / 导入名称等）绝大部分，不跳字体；
- **字重**：400 / 500 / 600 / 700 四档全部子集化入库（前端实际字重主力为 500/600，400/700 次之）；
- 生僻字（超出 GB2312 一级的罕见汉字）回退系统字体，属可接受长尾；
- 半角数字 / 拉丁由 Inter 承担，不占本子集。
- **工具**：入库脚本 `backend/scripts/subset_misans.py`（fonttools API，输入本地官方母本，产物入库 `frontend/public/fonts/misans-subset-{400,500,600,700}.woff2`）。

### 5.3 加载策略

```css
/* font-display: swap 已声明，防止 FOIT */
/* 首屏仅预加载 Inter latin 与 Mi Sans Regular(400)；500/600/700 由浏览器按需拉取 */
<link rel="preload" href="/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/misans-subset-400.woff2" as="font" type="font/woff2" crossorigin>
```

- **首屏加载顺序**：Inter latin（~48 KB）→ Mi Sans 400（~560 KB）最先就绪；500/600/700 仅在页面渲染到对应字重的文本时才被浏览器请求（@font-face 天然按需）。
- **性能预算（v1.2 修正）**：首屏加载 400 单字重 ~560 KB（woff2），Inter ~48 KB；Lighthouse 评分 ≥ 90、首屏无布局抖动（CLS 归零）为达标。若后续需进一步压首屏，可评估「UI 静态字首屏子集（~194 KB）+ GB2312 全量按需」的双段方案（见 §11.2），作为性能优化预留。
- **监控**：Lighthouse 字体加载评分，首屏无布局抖动（CLS）归零为达标。

---

## 6. 授权与合规

| 项 | 要求 | 多多贝动作 |
|---|---|---|
| **免费商用** | ✅ Mi Sans 全球免费商用，任何商业项目 | 已满足 |
| **署名义务** | 「应在软件中特别注明使用了 MiSans 字体」 | 统一致谢页 `docs/acknowledgements.md`（站点 `/acknowledgements`）署名 Mi Sans + Inter；应用站页脚版权区挂「开源致谢」入口链接 |
| **禁止改编** | 不得对字体外观改编 / 二次开发 / 单独分发字体文件 | 子集化属「使用」合规；**不得修改字形轮廓** |
| **来源记录** | — | 存档授权页：[hyperos.mi.com/font/faq](https://hyperos.mi.com/font/faq) |

> **署名位置决策（2026-09-04 修订）**：改为**统一开源致谢文件** `docs/acknowledgements.md`（对外站点 `/acknowledgements`）——集中承载全部第三方字体 + 开源项目署名，一页到位、便于维护；应用站 AppFooter 版权区保留一行「开源致谢」入口链接指向该页。原「页脚内联字体说明」方案废止（避免在页脚堆叠技术说明、稀释品牌收束文案）。

---

- 补充说明：如果未来连「关于」页都不想放

假如你觉得“技术致谢”出现在品牌故事里还是稍显割裂，还有两个更低侵入性的合规备选位置：

网站控制台（Console）：在页面加载时 console.log('Font: MiSans © Xiaomi') —— 这严格符合“软件中注明”，但用户看不见，略显“应付”，不推荐用于追求品牌质感的产品。

隐私政策 / 用户协议页面：在冗长的法律条款底部加一行“本产品使用的第三方字体资源包括 MiSans……”。这完全合规，但法律页面通常无人问津，适合不想在任何设计页面露出的情况。

## 7. 风险登记与缓解措施

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| **小米品牌联想**（用户误读为小米系） | 中 | 字体退居功能角色，品牌记忆靠珊瑚红 / 鹦鹉螺 / 超椭圆建立；上线后监测用户反馈与问卷 |
| **温暖温差**（Mi Sans 字面仍偏中性） | 低 | 温暖由色 / 形 / 涟漪动效承载，字体不做情绪主角（参见 §0 定位） |
| **Mi Sans × Inter 协调未实测** | 中 | **必须**在真实环境中通过 §4.2 验收，否则阻塞上线 |
| **工具链成熟度**（Mi Sans 新于普惠体） | 低 | 社区已有分包方案；可变字体降低多字重复杂度 |
| **品牌方向误判**（选错字体） | 低 | **已预留热切换机制**（§1.2），可零成本切回普惠体，见 §8 协议 |

---

## 8. 方案回切协议（阿里巴巴普惠体 3.0 对比评估）

> 实现你“后续如果有需要，我们可以再次切换到阿里巴巴普惠体做对比”的诉求，将其标准化为产品级评估流程。

### 8.1 触发条件

当以下**任意一项**发生时，启动普惠体对比评估：

1. 上线后用户调研反馈 Mi Sans 带来的“小米品牌联想”干扰超过阈值（如问卷中 > 15% 用户误认产品为小米系）；
2. Mi Sans 与 Inter 在 14px 小字号下的混排协调性**无法**通过 §4.2 验收，且 §4.3 调参后仍不达标；
3. 品牌方决策倾向于“更中性、更通用”的字形以强化“工具中立”属性。

### 8.2 切换步骤（零业务影响）

| 步骤 | 动作 | 产出 |
|---|---|---|
| **1** | 获取阿里巴巴普惠体 3.0 官方 woff2，执行同等子集化（首屏 ~3,500 字） | `/fonts/alibaba-puhuiti-subset.woff2` |
| **2** | 声明 `@font-face`，`font-family: "Alibaba PuHuiTi 3.0"`，复用相同 `unicode-range` | CSS 新增，不改业务代码 |
| **3** | 在测试环境 `<body>` 添加 `font-compare-a` 类（见 §1.2），触发普惠体渲染 | 全站瞬时切换 |
| **4** | 执行 §4.2 中西文混排验收清单（16px/14px） | 通过 / 阻塞报告 |
| **5** | 内部设计评审 + 灰度 5% 用户（埋点监测跳出率变化） | 数据反馈 |
| **6** | 决策：维持 Mi Sans / 切普惠体 / 混合策略（如标题 Mi Sans，正文普惠体） | 终稿 |

### 8.3 两种字体的一句话选择矩阵

| 维度 | Mi Sans（现行） | 普惠体（备选） |
|---|---|---|
| **调性** | “椭圆柔线” → 暖、有机 | “年轻挺拔” → 中性、现代 |
| **品牌联想** | 小米生态（双刃剑） | 无特定联想（工具感） |
| **字重弹性** | 10 固定 + **可变字体** | 9 固定，无可变 |
| **署名成本** | 需页脚署名 | **零** |
| **对比切换难度** | **极低（已有 CSS 变量抽象）** | |

---

## 9. 实施检查清单（上线前必过）

- [ ] 获取 Mi Sans 官方字体文件（variable / 按字重），确认授权条款；
- [ ] 子集化：生成首屏子集 + 完整子集；
- [ ] 编写 `@font-face`（Inter + Mi Sans，`unicode-range` 限定中文）；
- [ ] **CSS 变量抽象层**写入 `:root`（业务代码禁硬编码）；
- [ ] 数字场景加 `tabular-nums` 规则（§3.2）；
- [ ] 首页**页脚**加 Mi Sans 署名（§6）；
- [ ] **16px / 14px 中西文混排验收**（§4.2），结果记入测试报告；
- [ ] Lighthouse 字体评分 ≥ 90 + CLS 归零；
- [ ] 字阶表与《设计语言》L51–L58 逐条对齐（已确认，见 §2.2）；
- [ ] 确认 `font-compare-a` 热切换开关在测试环境有效（§1.2）。

---

## 10. 开放问题（已全部闭环）

| 原问题 | 最终决策 |
|---|---|
| **1. 字阶表与《设计语言》冲突？** | **按 §2.2 落地**。经核对，Display(32/40)、Body(16)、Small(14) 与规范完全一致；H1(28) 为规范外新增页面级标题，Micro 中文锁定 **14px 下限**。 |
| **2. Mi Sans 实际可用字重文件？** | 生产环境**优先使用可变字体**（`MiSans-VF.woff2`）；若分包，下载 **Regular(400)、Medium(500)、Semibold(600)、Bold(700)** 四个固定字重即可覆盖 90% 场景。 |
| **3. 署名文案最终位置？** | **统一开源致谢页 `docs/acknowledgements.md`**（站点 `/acknowledgements`，2026-09-04 修订，原「首页页脚内联」方案废止）。文案：“界面中文由 MiSans 字体渲染，版权归小米科技。” + Inter（OFL）。应用站 AppFooter 版权区挂「开源致谢」链接入口。 |
| **4. 探市/自选页是否单独微调？** | **暂不微调**。待 §4.2 混排验收完成后，若需调整，统一走 `:lang(zh)` 全局缩放，**禁止页面级覆写**。 |

---

## 11. 工程落地评审（v1.2 追加，2026-09-04）

> 本节约由 `docs/working-notes/font-plan-review-2026-09-04.md` 的评审结论落地。评审核对代码库发现：本文档原 v1.1 多处假设「应用站已在使用 Inter webfont」，但**实际仓库不存在任何 Inter 的 `@font-face` 或字体文件**——当前全站真实渲染的是系统字体（macOS→PingFang SC / Windows→Microsoft YaHei，见 `frontend/src/style/reset.scss` 的 `body` 硬编码栈）。因此本次变更的实质是「首次引入自托管 webfont」，而非字体替换。以下修订供工程落地遵循。

### 11.1 适用范围（硬边界）

- **仅应用站前端 `frontend/`**（`app.duoduobei.com`）。主站（`duoduobei-web` 独立仓）、文档站（`docs.duoduobei.com` VitePress）、叽咕（`jigu.duoduobei.com`）**不适用**本规范，字体决策另行评估。
- 本文档「页脚署名」「探市/自选页」等措辞均指应用站。

### 11.2 落地前置（2026-09-04 已闭环，含两条路径验收）

1. **Inter 字体来源已明确并落地**：采用 `@fontsource-variable/inter` 的 latin 可变子集（OFL 许可），下载自 jsDelivr（`inter-latin-wght-normal.woff2`，~48KB，wght 100–900 全轴，覆盖数字/西文/货币/全角符号以外账本所需全部字符），已校验 cmap 无缺字，自托管入库 `frontend/public/fonts/`，无运行时第三方外链。
2. **Mi Sans 子集化工具链已跑通并验收**：实测 `D:\MiSans\MiSans` 本地母本单字重 woff2 ≈ 4.3–4.8MB，**全量 10 字重 ≈ 47MB，可变字体 `MiSansVF.ttf` ≈ 19.2MB**（且仅 ttf、无 VF.woff2）。入库脚本 `backend/scripts/subset_misans.py`（fonttools API）已产出 4 档子集（400/500/600/700，每档 ~560KB，字表 3,823 = GB2312 一级 + UI 源码字 + 符号），产物入库 `frontend/public/fonts/`。
3. **Inter 先行已落实**：Inter latin（~48KB）与 Mi Sans 400 为首屏预加载对象，500/600/700 按需懒加载，见 §5.3。

### 11.3 变量命名与现有 token 体系对齐（修订 §1.2 的落地映射）

原 §1.2 定义的抽象层（`--font-latin` / `--font-cjk` / `--font-base` / `--font-num`）为「规范层语义」，工程落地时与现有 token 体系（`frontend/src/style/colors.css`、`design-tokens.css`）**对齐映射**，业务组件继续引用现有语义变量，禁止双轨：

| 现有 token（业务代码已引用） | 落地取值 | 说明 |
|---|---|---|
| `--font-sans`（colors.css，现为 `Inter, -apple-system, "PingFang SC", sans-serif`） | `var(--font-latin), var(--font-cjk)` | 全局默认 UI/正文栈 |
| `--font-mono` / `--font-number` / `--font-ui` / `--font-hero` | 经 design-tokens.css 语义别名指向 `--font-sans` 即可 | 数字等宽由 `tabular-nums` + Inter 承担，不再依赖系统 mono |
| `--font-latin`（新增） | `"Inter", system-ui, sans-serif` | 西文/数字/半角符号 |
| `--font-cjk`（新增） | `"MiSans", "PingFang SC", "Microsoft YaHei", sans-serif` | 中文 |

- `@font-face` 的 `unicode-range` 隔离（§1.3）照常生效，拉丁/数字不落 Mi Sans。
- **落地动作**：在 `colors.css` 声明 `--font-latin` / `--font-cjk`，改 `--font-sans` 取值为两变量组合；`reset.scss` 的 `body` 硬编码字体栈替换为 `var(--font-sans)`（同步处理 `.dark` 场景），并核对所有业务组件引用路径。

### 11.4 性能预算实测数值（落地验收锚点）

| 项 | 数值 | 说明 |
|---|---|---|
| Mi Sans 全量静态 | ~47MB（10 字重 × ~4.3–4.8MB woff2） | 严禁直接入库或进产物 |
| MiSansVF.ttf | ~19.2MB | 仅 ttf，无 VF.woff2；可变字体后续单独索取官方 woff2 再评估 |
| Inter latin 可变 woff2 | **~48KB**（已落地） | `frontend/public/fonts/inter-latin-wght-normal.woff2` |
| Mi Sans 子集 woff2（单字重） | **~560KB**（3,823 字） | `misans-subset-{400,500,600,700}.woff2`；v1.1「<100KB」目标经实测修正 |
| 首屏实际加载 | ~610KB（Inter 48KB + MiSans 400 ~560KB） | 500/600/700 按需懒加载，不占首屏 |

### 11.5 验收门槛（上线前必过，承接 §4.2）

- 16px / 14px 两档中西文混排验收（同基线、视觉重量平衡、行高不跳、数字与中文混排连贯、Mac/Windows 观感接近）；
- Lighthouse 字体评分 ≥ 90 且 CLS 归零；
- 确认 `font-compare-a` 热切换开关在测试环境有效；
- 统一致谢页 `docs/acknowledgements.md` 上线并可从 AppFooter「开源致谢」入口访问（Mi Sans/Inter 署名义务落地）。

---

*本文档为 多多贝 项目字体方案（方案 B）的工程落地依据（适用范围：应用站前端 `frontend/`）。v1.1「批准实施」状态已在 v1.2 修订为「评审后待工程落地」，请以 v1.2 为准。若需启动普惠体对比评估，严格按 §8 回切协议执行。变更记录归档至 `docs/spec/changelog.md`。*
