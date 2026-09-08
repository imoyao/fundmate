# 天天基金「投顾 ID 获取」与「组合持仓接口」调研结论

> 调研时间：2026-07-22
> 背景：需要以**可自动化**、**免二维码登录**的方式获取「越海」(国联民生证券 投顾组合) 在天天基金的*组合持仓*，并接入「组合持仓」独立看板。
> 本次聚焦两个问题：(1) App 首页搜索能否返回投顾 id；(2) 按持仓链接去 GitHub 找逆向思路。

> ⚠️ **续作勘误（2026-07-22 晚，已多次更正）**：本文部分结论已被后续实测修正，请以 **[投顾持仓接口_技术方案与待决问题.md](./投顾持仓接口_技术方案与待决问题.md)** 为准。要点：(1) 真实前端 bundle 为 `funda91a99886abf7e`、host 为 `tradeh5.tiantianfunds.cn`；（2）`combine-gold.tiantianfunds.com` 只是 bundle 的**静态默认 host**，公网 404；运行时经远程配置解析到 **`uni-fundts.1234567.com.cn`**，后者对外**公开路由 `/combine/investAdviserInfo/*`、零鉴权**；（3）**投顾数据现已可纯 curl 直连公开 host 拿到**（`getTGQuoteByFavor` 业绩 + `getHoldWarehouseIndustryRatio` 行业配置 + `getAdjustWarehouse` 当前/历史基金级持仓 + `dataapi` 的 `FundIATGInfoAggr` 概览），原"挖签名/拿 session 绕不开"两版假设均被推翻。

---

## 一、执行摘要

| 问题 | 结论 | 置信度 |
|------|------|--------|
| App 首页搜索能否返回投顾 id？ | **无法用 curl 复现**。搜索接口的真实方法名藏在 App 原生包 / 动态加载的 Weex chunk 里；网页版搜索 (`fundsuggest`) 只返回股票/基金/经理，**不含投顾**分类。 | 高 |
| GitHub 是否有现成逆向方案？ | **没有**。最相关的两个仓库 (`kouchao/TiantianFundApi`、`tianguzhe/tiantian-fund-api`) 都只覆盖**单只基金**，不涉及投顾组合。但从中挖出一个**可复用突破**：天天基金 App 接口的 `validmark` 请求头 + `baseData` 参数组，经实测可直调 `FundMNewApi` 任意端点。 | 高 |
| 投顾持仓接口能否纯 curl 拿到？ | **能**。投顾数据在公开 host `uni-fundts.1234567.com.cn`（`/combine/investAdviserInfo/*`，零鉴权）与 `dataapi.1234567.com.cn`（`FundIATGInfoAggr`，零鉴权）上均可纯 curl 直连；含业绩、行业配置、**当前与历史基金级持仓**（`getAdjustWarehouse` tag 0/1，越海实测当前 11 只、历史 6 次调仓）。 | 高 |
| 那 TGCode 怎么拿？ | 一次性从 App「分享→复制链接」取 `tgCode=` 值（越海=XCOVSEX、万家非凡新质驱动=JY48YPE、省心投步步盈=UFPW1GJ，已入 `advisor_watchlist.json`）；脚本 `--tgcode`/`--url` 自动解析。全量 462 只列表接口尚未定位（低优先级）。 | — |

**一句话**：App 搜索确实能呈现投顾，但其接口不可复现；GitHub 帮不上投顾持仓的忙，却意外给了 `validmark` 这把能开天天基金 App 后端的"万能钥匙"。**投顾 ID 走一次性分享链接取 `tgCode=` 即可**，其余抓取已由 `fund_advisor_holdings.py` 的**公开接口直连（默认路径，免登录）**覆盖（含 `--history` 历史持仓），Playwright 仅作极端兜底（`--playwright`）。

---

## 二、Q1：App 首页搜索能否返回投顾 id？

### 2.1 网页版搜索 —— 明确不含投顾

天天基金网页搜索端点（来自开源仓库 `kouchao` 的真实实现）：

```
https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key=越海
```

实测返回的是**股票/上市公司**（越秀资本、越剑智能、越疆…），`m` 取值 `1/3/7/8` 分别对应 基金/按字母搜公司/基金经理/基金公司，**没有任何投顾分类**。

> 结论：网页搜索这条路对"投顾 id"无效。

### 2.2 App 搜索端点 —— 真实存在，但方法名不可复现

App 搜索走 `fundmobapi.eastmoney.com/FundMNewApi/`。带上正确的 `validmark` 头后：

| 试探的方法名 | 结果 |
|------|------|
| `FundMSearchAll?key=越海` | JSON `{"ErrCode":404,…}`（控制器里无此方法） |
| `FundMSearch?key=越海` | JSON 404 |
| `FundMQuery?key=越海` | JSON 404 |
| 不带 `validmark` 头时 | JSON `{"ErrCode":61136,"ErrMsg":"网络繁忙"}`（缺鉴权头） |

首页 chunk (`pages-index-index`) 里搜索框只是跳转到 `tforms-fund/#/pages/search/home/index` —— **一个独立的、运行时才加载的搜索页 chunk**。因此连搜索接口的"方法名"都在动态 chunk 里，curl 无法枚举命中。

> 结论：**App 搜索在 App 内确实能呈现投顾结果（含可定位的 id），但其后端方法名被混淆在动态 chunk 中，无法用脚本直调。** 把它当作自动化数据源不可行。

---

## 三、Q2：GitHub 调研（按持仓链接找灵感）

克隆并全文 grep 了最相关的两个仓库：

- **`kouchao/TiantianFundApi`** —— 天天基金 Node.js API 服务，含 50+ 模块，但**全部是单只基金**（详情/净值/排行/经理/持仓股…），grep `投顾/TGCode/strategyDetail/combination/getCompositeInfoNew/portfolio` **零命中**。
- **`tianguzhe/tiantian-fund-api`**（2026-05 新仓库，带 API 文档）—— 同样是**单只基金**分析向（F10/评分/对比），无投顾组合。

**GitHub 上没有针对「天天基金投顾组合持仓」的逆向仓库。** 投顾持仓这条线在开源社区是空白。

### 3.1 但 GitHub 给了一个真正有用的突破：`validmark` 头

`kouchao` 的 `src/utils/index.js` 暴露了天天基金 App 接口的调用方式：

```js
const headers = { validmark: "aKVEnBbJF9Nip2Wjf4de/fSvA8W3X3iB4L6vT0Y5cxvZbEfEm17udZKUD2qy37dLRY3bzzHLDv+up/Yn3OTo5Q==" };
const baseData = {
  product: "EFund",  deviceid: "<uuid>", MobileKey: "<uuid>",
  plat: "Iphone", PhoneType: "IOS15.1.0", OSVersion: "15.5",
  version: "6.5.5", ServerVersion: "6.5.5", Version: "6.5.5", appVersion: "6.5.5",
};
```

**用这套头+参实测验证（`FundMNDetailInformation?FCODE=000001`）成功返回真实数据（华夏成长混合）**。这意味着：

> 任意 `fundmobapi.eastmoney.com/FundMNewApi/*` 端点，只要带上 `validmark` + `baseData`，都能从 curl 直调——不必登录、不必签名。这是后续探测天天基金任何 App 端点的通用钥匙。

---

## 四、接口探测的额外发现（在 GitHub 启发下继续推进）

### 4.1 锁定了"组合/投顾"真实后端 host

开源仓库 `pages-customoption-index` chunk 暴露了组合类 API 命名规律（`getCompositeInfoNew`、`getCustomComboList`、`getComboData`、`getHoldFundList`）与 host 体系。据此定位到真实后端：

```
https://uni-fundts.1234567.com.cn/combine/portfolioInfo/getCompositeInfoNew
```

实测：端点**存在**（`Success:true`），但 `code=越海` / `code=JY48YPE` 均返回 `Data:null` —— 它是**自定义组合**接口，需要自定义组合 code，不是投顾 TGCode。

### 4.2 投顾持仓方法名仍不可知 ~~（已被推翻）~~

> 本节为早期结论。后续对 bundle 的完整反编译定位到真实方法名（`getAdjustWarehouse` 等），见勘误框与权威文档——方法名**可知、可直连**，无需运行时 chunk。

在正确 host 下继续试探投顾候选方法名（`getAdvisorInfo` / `getStrategyInfo` / `getPortfolioInfo` / `getAdvisorPortfolio` / `getCombineInfo` / `queryAdvisorInfo` …）：

```
{"timestamp":"2026-07-22 ...","status":404,"error":"Not Found","path":"/combine/portfolioInfo/getAdvisorInfo"}
```

全部 Spring Boot 404。**投顾持仓接口不在 `portfolioInfo` 路径下，方法名位于 `pages-strategyDetail-index` 动态 chunk 中**，无法通过静态分析或穷举获得。

### 4.3 死路的多路径交叉确认

| 路径 | 结果 |
|------|------|
| 静态包 grep `strategyDetail` | 0 命中（`index.53d45257.js`、`chunk-vendors` 均无） |
| `__uniRoutes` 路由表 | 仅 1 条（首页），投顾路由运行时注入 |
| 首页 chunk 搜索框 | 仅跳转到独立搜索页 chunk |
| 投顾 H5 包 = webportal 应用 | 入口 HTML 只静态引用 index/me/newslist/customoption，无 strategyDetail |
| curl 穷举 投顾方法名 | 全部 404 |

> **⚠️ 结论已推翻（见上方勘误框）**：本节"纯 curl 不可达"的判断，在后续**对 App bundle 的完整分析**中被推翻——投顾方法名并不在运行时动态 chunk 里不可知，而是写在投顾模块 bundle 中，路径为 `/combine/investAdviserInfo/*`（`getTGQuoteByFavor` / `getHoldWarehouseIndustryRatio` / `getAdjustWarehouse`）+ `dataapi` 的 `FundIATGInfoAggr`。**投顾持仓现已可纯 curl 直连公开 host（零鉴权）拿到**，日常自动化以公开接口为主，`fund_advisor_holdings.py` 的 Playwright 路径仅作极端兜底（`--playwright`）。本节保留作"早期尝试过哪些穷举"的排查留痕。

---

## 五、投顾 TGCode 的可靠获取路径

抓取脚本的**唯一前置输入**是投顾的 TGCode。两条获取路径：

### 路径 A（推荐，一次性，零开发）
在天天基金 App 打开「越海」→ 右上角「分享」→「复制链接」，得到形如：

```
https://tradeh5.tiantianfunds.cn/tradeh5/funda91a99886abf7e/detailindex?tgCode=XXXX
```

把链接直接喂给脚本，它自动用正则 `(?:tgCode|id)=([^&]+)` 提取 TGCode（兼容新版 tgCode= 与旧版 id=）：

```bash
python fund_advisor_holdings.py --url "https://tradeh5.tiantianfunds.cn/tradeh5/funda91a99886abf7e/detailindex?tgCode=XXXX"
```

### 路径 B（全自动，需浏览器环境）
扩展脚本：用 Playwright 打开 H5 搜索页 `tforms-fund/#/pages/search/home/index` → 输入"越海" → 点击投顾结果 → 读取跳转后 URL 的 `tgCode=`。**因沙箱 Chromium 渲染超过时限会被杀，此流程只能在你能跑浏览器的本机运行。** 当前脚本未内置该搜索流程（方法名仍依赖动态 chunk），如需我可补一个 search-then-scrape 的变体。

> 关于"似乎没法手动获取 ID"：App 的分享链接**一定**带 `tgCode=`（新版）或 `id=`（旧版），若之前拿不到，多半是分享入口没点到"复制链接"、或复制到的是口令而非 URL。只要拿到的是以 `tradeh5.tiantianfunds.cn/tradeh5/` 开头的链接，里面的 `tgCode=` / `id=` 就是 TGCode。

---

## 六、当前落地状态

| 项 | 状态 | 说明 |
|----|------|------|
| 投顾持仓抓取（公开 API，默认） | ✅ 已具备 | `fund_advisor_holdings.py` 直连 `uni-fundts`+`dataapi`（免登录），输入 TGCode/分享链接，输出结构化 JSON；Playwright 仅兜底 |
| 越海 TGCode | ✅ 已知 | `XCOVSEX`（已写入 `advisor_watchlist.json`），无需再人工提供 |
| 且慢持仓（远足/成长五剑） | ✅ 已具备 | 且慢 MCP `BatchGetStrategiesComposition` 可用 |
| 组合持仓独立看板 | 🔲 待整合 | 拿到越海 TGCode 后跑脚本，与且慢数据合并即可 |
| App 搜索自动取 ID | ❌ 不可行 | 方法名在动态 chunk，curl 无法复现 |
| GitHub 现成方案 | ❌ 不存在 | 仅有单只基金仓库；但 `validmark` 头已反哺探测能力 |

---

## 七、下一步行动清单

1. **你**：在天天基金 App 打开越海 → 分享 → 复制链接 → 把链接发我（路径 A）。
2. **我**：用 `fund_advisor_holdings.py --url <链接>` 在本机跑通越海持仓抽取，校验正则对"基金名+6位代码+占比%"的覆盖。
3. **我**：将越海持仓 JSON 与且慢（远足/成长五剑）合并，落成「组合持仓」独立看板的数据源。
4. （可选）**我**：补一个 Playwright 搜索自动解析 TGCode 的变体，彻底去掉手动粘贴（需你在本机运行）。
5. （可选）用 `validmark` 头继续探测其他 App 端点（如估值、收益走势），扩充看板指标——投顾持仓已走公开 API，无需浏览器渲染。

---

### 附：本次实测关键证据（curl）

```
# 网页搜索：只返回股票，无投顾
fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key=越海
→ 越秀资本 / 越剑智能 / 越疆 ...

# validmark 生效验证：成功返回基金详情
fundmobapi.eastmoney.com/FundMNewApi/FundMNDetailInformation?FCODE=000001  (+validmark+baseData)
→ {"Datas":{"FCODE":"000001","SHORTNAME":"华夏成长混合",...}}

# App 搜索方法名不可复现
fundmobapi.eastmoney.com/FundMNewApi/FundMSearchAll?key=越海 (+validmark)
→ {"ErrCode":404,...}

# 真实组合后端 host（自定义组合，非投顾）
uni-fundts.1234567.com.cn/combine/portfolioInfo/getCompositeInfoNew?code=越海
→ {"Data":null,"Success":true,...}

# 投顾持仓方法名穷举全部 404
uni-fundts.1234567.com.cn/combine/portfolioInfo/getAdvisorInfo?code=JY48YPE
→ {"status":404,"error":"Not Found",...}
```
