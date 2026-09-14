# 投顾持仓接口 · 技术方案与待决问题（决策记录）

> 更新时间：2026-07-22（续）
> 关联文档：[天天基金投顾ID与持仓接口_调研结论.md](./天天基金投顾ID与持仓接口_调研结论.md)
> 背景：为「越海」等天天基金投顾组合做*组合持仓*自动化抓取，并接入「组合持仓」独立看板；同时推进"市场温度计"多源情绪聚合。

---

## 0. 本次续作做了什么

按既定优先级继续**逆向签名/鉴权系统**，并从 `tradeh5` 的 `funda91a99886abf7e` 包（App.js / env.js / sdk.js）中提取了真实的投顾后端信息。关键产出两条：

1. **定位了投顾真实后端主机与 12 个接口方法**（含持仓行业配置 `getHoldWarehouseIndustryRatio`、业绩 `getTGQuoteByFavor`）。
2. **实测确认：bundle 里写的 `combine-gold.tiantianfunds.com` 公网直连被网关拦截（404）——但这是静态默认值，运行时经远程 host 配置解析到 `uni-fundts.1234567.com.cn`，后者对外公开路由 `/combine/investAdviserInfo/*`，无需登录、无需签名。**

> ⚠️ **重大更正（续二）**：此前两版结论（"签名绕不开"→"会话/cookie 绕不开"）**均被最新实测推翻**。真正绕不开的不是签名、也不是会话，而是**找对运行时 host**。`uni-fundts.1234567.com.cn` 公开可达、零鉴权，直接用 curl 就能拿投顾业绩 + 行业配置。详见第 0.5 节与第 3 节（路线表已更新为"已实现"）。

---

## 1. 关键结论速览

| 事项 | 结论 | 置信度 | 证据 |
|------|------|--------|------|
| 投顾后端 host（静态默认） | `combine-gold.tiantianfunds.com`（beta=`combine-gold-gc`、dev=`dataapineice.1234567.com.cn`） | 高 | App.js 模块 62221 的 `host:{release:...}` |
| **投顾后端 host（运行时真实）** | **`uni-fundts.1234567.com.cn`**（远程 host 配置解析结果，对外公开路由） | 高 | 实测该 host 直连 200，返回真实投顾数据 |
| 公开可用方法 | `getTGQuoteByFavor`（业绩/净值，需 `tgCodeWithDateStr=TGCODE_日期`）、`getHoldWarehouseIndustryRatio`（行业配置，仅需 `tgCode`） | 高 | 实测 200 + 真实数据 |
| 是否存在 per-request 的 `sign`/`secret` 字段 | **不存在**。App.js 中 `sign`×477 绝大多数是 `assign`/`design` 子串；`secret` 出现 0 次 | 高 | 全文 grep 计数 |
| 真正的"签名"是什么 | `validmark`（= `{uid,deviceid,passportid,force}`）+ 可选的参数加密 `encryptArr` | 高 | `getValidMark` / `createHttp` 实现 |
| 是否需要登录/签名/cookie | **不需要**。`uni-fundts` 公开接口零鉴权，表单参数（product/mobileKey/version/plat）即可 | 高 | 实测匿名 curl 200 |
| combine-gold 能否纯 curl 直连 | **不能**（公网 404，静态默认 host 未对外路由）——但同一套 API 在 `uni-fundts` 上公开可达，故"curl 拿数据"总体可行 | 高 | combine-gold 多组 404；uni-fundts 实测 200 |
| 基金级持仓（基金名+代码+占比） | **已解决**：`/combine/investAdviserInfo/getAdjustWarehouse`（`tag=0`=当前最新一次调仓的基金级前后占比；`tag=1`=历次调仓历史，数量随组合而定） | 高 | 实测 XCOVSEX 当前 11 只、历史 6 次调仓；万家非凡新质驱动 20 次；基金级 afterRatio 全精度 |
| 投顾概览（最全字段） | `https://dataapi.1234567.com.cn/dataapi/IAAGGR/FundIATGInfoAggr`（GET，FIELDS+TGCODE；响应用小写 `data`+`errorCode`/`success`） | 高 | 实测返回 TGNAME/RISKLEVEL/STRATEGY_RATE/SYL_*/BENCHSYL_*/STGCONCEPT |
| 投顾列表（462 只产品）枚举接口 | **未在 `investAdviserInfo` 下找到**；列表类方法在其它 bundle/dynamic chunk 中 | 中 | 12 个方法无 list/getAll 类 |

---

## 0.5 重大更正（2026-07-22 续二）：公开 host `uni-fundts` 已打通

> 用户实测发现：`https://uni-fundts.1234567.com.cn/combine/investAdviserInfo/getTGQuoteByFavor`
> 用表单参数即可返回真实投顾数据。**这推翻了"combine-gold 需会话/cookie"的判断**——
> bundle 里的 `combine-gold.tiantianfunds.com` 只是**静态默认值**，运行时 `getBaseUrl` 经远程
> host 配置（`R(e)`/`C(e,t,n)`）解析到 `uni-fundts.1234567.com.cn`，后者对外公开。

### 已验证可用的公开接口（无需登录/签名/浏览器）

**A. 投顾交易/持仓明细 host：`uni-fundts.1234567.com.cn`**

| 接口 | 方法 | 必填参数 | 返回 |
|------|------|----------|------|
| `POST /combine/investAdviserInfo/getTGQuoteByFavor` | 业绩/净值 | `tgCodeWithDateStr=TGCODE_YYYY-MM-DD`（缺则 `Data:null`） | TGNAME、管理人、各区间收益(SYL_1N/2N/3N…)、净值日期 JZRQ |
| `POST /combine/investAdviserInfo/getHoldWarehouseIndustryRatio` | 持仓行业配置 | `tgCode` | 行业名 + 占比(ratio)，如 电子 9.16% / 基础化工 4.69% |
| `POST /combine/investAdviserInfo/getAdjustWarehouse` | 调仓/持仓明细 | `tgCode` + `tag`（0=最新调仓/当前持仓；1=历史调仓列表）+ `useNewFundType=true` | `tag=0`→`latestAdjust.adjustList[].fundList`（基金代码/名称/前占比/后占比/操作类型）；`tag=1`→`adjustHistory[]`（历次调仓，数量随组合而定，实测越海 6 条、万家非凡新质驱动 20 条、省心投步步盈 14 条） |

**B. 投顾概览 host：`dataapi.1234567.com.cn`（字段最全）**

| 接口 | 方法 | 必填参数 | 返回 |
|------|------|----------|------|
| `GET /dataapi/IAAGGR/FundIATGInfoAggr` | 投顾信息概览 | `FIELDS=逗号字段列表` + `TGCODE` | TGNAME/LOGO_NAME/RISKLEVEL/STRATEGY_RATE/SYL_*/BENCHSYL_*/STGCONCEPT/ESTABDATE/STATUS…（响应用小写 `data`+`errorCode`/`success`，**不是** `Data`/`ErrCode`） |

> 通用表单参数（来自 App 抓包）：`product=EFund`、`mobileKey=123`、`version=6.5.9`、`plat=Android`。
> `getAdjustWarehouse` 的 `operationInt` 映射：1=建仓、2=加仓、3=减仓、4=新增、5=持平（后占比 `afterRatio` 即当前持仓占比）。

脚本已落地：`fund_advisor_holdings.py --tgcode XCOVSEX`（公开接口直连，默认路径；或 `--all` 遍历关注列表）；
加 `--history` 可额外抓取历次调仓的基金级前后占比。health 接口 H3–H6 已覆盖上述三类接口（实测 `status=healthy`）。

### 历史持仓（"大坑"）已解决 ✅
- 用户原话"需要一个获取投顾历史持仓信息的接口，感觉这个坑还蛮大的"——**已定位并落地**：
  历史基金级持仓 = `getAdjustWarehouse?tag=1` 的 `adjustHistory[]`，每个节点含 `dateStr`(调仓日期)、
  `reason`(调仓理由)、`adjustList[].fundList[]`(基金代码/名称 + 调仓前 `preRatio` / 调仓后 `afterRatio` + 操作类型)。
  实测 XCOVSEX 返回 6 次调仓（2022-07-26 建仓 → 2026-04-01），每次基金级前后占比全精度。
- 当前基金级持仓 = `getAdjustWarehouse?tag=0` 的 `latestAdjust`（最新一次调仓后占比 = 当前持仓）。
- 因此"业绩 + 行业配置 + 当前/历史基金级持仓"已完全闭环，无需浏览器、无需正则、无需会话。

---

## 2. 签名/鉴权系统逆向结论（从 App.js / sdk.js）

### 2.1 请求组装链路

```
Request()                         // 组装 commonConfig
  ├─ getCommonParams(_||v)  -> D  // 通用参数（deviceid/version/plat…）
  ├─ getCommonHeaders(_||v) -> C  // 通用头
  ├─ getValidMark(E)        -> validmark  // 仅当该方法标记 createSecretStr 时附加
  └─ getBaseUrl(v,...)      -> baseURL    // = combine-gold.tiantianfunds.com

createHttp()                       // 真正发请求
  ├─ 合并 headers：default(content-type:application/json) + iOS(Accept-Encoding:gzip) + 调用头 + O(参数) + A(扩展参数)
  ├─ 参数加密：q = encrypt(O, encryptArr)   // 对 encryptArr 指定的字段做 AES 加密
  ├─ deleteSecretStr 为真时：delete validmark
  └─ 按 method 调 v(GET)/_(POST)/w(upload)
```

### 2.2 `validmark` 的真相

```js
// App.js: getValidMark()
getValidMark = function(){
  c = await $f.getUserInfo();      // 已登录才有值
  t = s({}, c, e);
  return { uid: t.uid||"", deviceid: t.deviceid||"",
           passportid: t.passportid||"", force: true };
}
```

- 匿名用户：`uid/deviceid/passportid` 全部为空字符串，`force:true`。
- **没有任何 RSA/AES 对 validmark 做二次加密**——它就是明文 JSON 对象直接作为请求参数/头传入。

### 2.3 "签名算法"到底重不重

- App.js 中 `RSA`/`AES` 各仅出现 **1 次**，且都是**内嵌的 base64 密钥常量**（公钥/AES key），不是加密调用。
- sdk.js（HTTP 引擎）有 `AES`×11（crypto-js 调用），但**无 `sign`/`secret` 字段逻辑**。
- 投顾 H5 接口的鉴权本质是：**通用参数 + `validmark` + 个别字段 `encryptArr` 参数加密**，没有逐请求签名。

> 结论：此前把"挖签名"当成绕不开的硬骨头，是**高估了复杂度**。真正拦路的既不是签名也不是会话，而是**找错 host**——bundle 静态默认的 `combine-gold` 公网不路由，运行时解析到的 `uni-fundts` 才是对外公开、零鉴权的真身（见第 0.5 / 第 3 节）。

### 2.4 实测：combine-gold 直连全部 404

```
GET https://combine-gold.tiantianfunds.com/combine/investAdviserInfo/getHoldWarehouseIndustryRatio
    ?tgCode=XCOVSEX&deviceid=...&version=6.5.5&plat=Iphone&appVersion=6.5.5
    &product=EFund&validmark={"uid":"","deviceid":"","passportid":"","force":true}
    + User-Agent(iPhone) + Referer/Origin(tradeh5) + 已抓取的 tradeh5 cookie
→ <title>404 Not Found</title> (tengine)

变体全部同样 404：
  - 参数名 tgCode / strategyId / code
  - beta 主机 combine-gold-gc.tiantianfunds.com
  - POST
  - 伪造路径 /combine/nonexistent（同样 404 → 确认是网关层拦截，不是路径/参数问题）
  - tradeh5 主机反代 /combine/...（404，未做反代）

> 注：`combine-gold` 公网 404 是**事实**，但它只是 bundle 的**静态默认 host**。同一套
> `investAdviserInfo` API 在运行时解析到的 `uni-fundts.1234567.com.cn` 上**公开可达、零鉴权**
> （见第 0.5 节）。所以"combine-gold 404"并不等于"投顾接口不可达"——只是 host 找错了。
```

---

## 3. 假设校正（重要，与既定路线冲突，已二次更正）

> 原假设（用户 msg 8）：*"挖签名算法是一个特别重要而且绕不开的路线"*
> 第一版结论：**签名不是绕不开的，会话/cookie 才是。**
> **第二版（最新、实测确证）：签名不是绕不开的，会话也不是——真正绕不开的是「找对运行时 host」。**

- 签名为轻量结构（`validmark` + 可选字段加密），无逐请求签名字段；
- `combine-gold.tiantianfunds.com`（bundle 静态默认）公网直连被网关 404；但实测**带 web cookie 的匿名/登录请求同样 404**——证明不是 cookie/会话问题，而是**该 host 公网未路由**；
- bundle 运行时经远程 host 配置把 `igbCombineApi` 解析到 **`uni-fundts.1234567.com.cn`**，后者对外公开 `/combine/investAdviserInfo/*`，**零鉴权**，curl 直出真实数据。

**路线优先级（最终版）：**

| 路线 | 是否还需要挖签名 | 可行性 | 说明 |
|------|------------------|--------|------|
| A. 直连公开 host `uni-fundts`（表单参数即可） | 否 | ★★★ 已实现 | **推荐且已落地**：公开接口直连（默认）模式 + health H3/H4 实测 `healthy` |
| B. Playwright 渲染 H5 页（兜底） | 否 | ★ | 仅作极端兜底（公开 host 整体故障时）；基金级持仓现已由 `getAdjustWarehouse` 覆盖，无需浏览器 |
| C. 抓包/重放 App 真实请求 | 否 | ★★ | 若后续要基金级明细，抓包定位真实 host/方法仍是最快路径 |
| D. 复刻签名 / 拿 session cookie 直连 combine-gold | — | ✗ | 已证伪：combine-gold 公网不路由，与签名/会话无关 |

---

## 4. 用户明确要求记录的点：包/路径不稳定 → 必须做 health 接口

> 用户原话：*"这个包总是不是每次它都会变呀…每一次这个 APP 更新之后我们这个路径相当于要每一次去变化…我们的接口好像并不是很稳定所以我们要在系统的 health 接口里面去验证这个接口是不是正常，这也是一个需要记录的一个点。"*

### 4.1 不稳定的来源（已证实）

| 不稳定项 | 当前值（2026-07-22） | 变化频率 | 影响 |
|----------|----------------------|----------|------|
| 前端 bundle 名 | `funda91a99886abf7e` | 每次 App 发版 | 所有静态资源路径（App.js/env.js/sdk.js）随之变化 |
| 投顾后端 host（运行时真实） | `uni-fundts.1234567.com.cn` | 低（网关层） | 公开 host 相对稳；但**接口路径/方法名**随业务迭代会变 |
| API 路径/方法名 | `/combine/investAdviserInfo/getTGQuoteByFavor` 等 12 个 | 中 | 方法名混淆在 bundle 内，发版即可能增删 |
| 鉴权 | **无**（公开接口零鉴权） | — | 不再依赖会話/cookie，这是比路线 A 更稳的关键 |

> 注意：公开 host 零鉴权，意味着"签名复刻 / cookie 维护"这两类脆弱性**直接消失**。剩下的唯一脆弱性是 bundle/host/方法名随发版变化——所以 health 接口（H1–H6）仍是必选项，用来在发版后第一时间发现路径失效。

### 4.2 health 接口设计草案（建议落地）

**职责**：在每次「市场温度计」微信推送前（建议每日盘后 + 一次凌晨预热），主动验证整条链路是否正常，异常即告警。

| 检查项 | 方法 | 正常判定 | 异常含义 |
|--------|------|----------|----------|
| H1 bundle 可达 | `GET tradeh5.../{bundle}/App.js` | HTTP 200 | bundle 名被换（发版）→ 更新 `ADVISOR_BUNDLE` |
| H2 bundle 未轮换 | 比对当前 `{bundle}` 与上次记录值 | 一致 | 发版导致路径失效 → 触发重新定位 |
| H3 接口可达（公开） | `POST uni-fundts.../getTGQuoteByFavor`（表单，含 `tgCodeWithDateStr`） | HTTP 200 且 `Succeed=true` | host 下线 / 接口变更（发版） |
| H4 数据可解析 | 校验返回 `Data` 非空 | 通过 | 后端改了响应结构（schema 漂移） |
| H5 概览接口（dataapi） | `GET dataapi.../FundIATGInfoAggr`（TGCODE=XCOVSEX） | HTTP 200 且 `success=true` 且 `data` 非空 | dataapi host 下线 / 接口变更 |
| H6 历史持仓接口 | `POST uni-fundts.../getAdjustWarehouse`（`tag=1`） | HTTP 200 且 `adjustHistory` 非空 | 历史持仓接口变更 |

**告警**：任意一项失败 → 立即通知（微信/邮件），并附失败项 + 最近一次成功时间。
**落点**：`fund_advisor_holdings.py` 已实现 `healthcheck` 子命令（H1–H6 实测 `status=healthy`）与公开接口直连（默认）模式（含 `--history` 抓历史持仓），输出 JSON 报告供监控消费。

---

## 5. 待决问题清单（含此前 A/B/C 三问的当前答案）

- **A. 投顾列表拿不到 → 前端无法做搜索**
  - 当前：`investAdviserInfo` 下 11 个方法**无列表/枚举类**；462 只产品列表在其它 bundle/dynamic chunk。
  - 影响：前端搜索自动解析 TGCode 暂不可做（仍依赖一次性分享链接取 `id=`）。
  - 待办：若要走"前端搜索"，需另寻列表接口（可能是 `igbCombineApi` 之外的搜索类 host，或动态 chunk）。**优先级低于持仓抓取本身。**

- **B. 客户端签名能否解决？**
  - 当前：签名本身轻量（`validmark`+可选字段加密），但**无需复刻**——`uni-fundts` 与 `dataapi` 均零鉴权，公开 host 直连即可。
  - 结论：**"复刻签名"与"拿 session cookie"均非关键路径**，找对运行时 host 才是。见第 3 节路线表。

- **C. 用前端正则抽比例会不会丢精度？**
  - 当前：正则 `名 + 6位代码 + 占比%` 对渲染后的 DOM 文本抽取，**可能漏掉长基金名/特殊字符、把行业占比误判为个基占比**。
  - 解法：一旦走路线 A（cookie 直连），拿的是**接口原始 JSON，全精度、零正则**——C 问题自然消失。
  - 若暂时只能走 Playwright（路线 B），建议改抓接口响应（DevTools 网络面板里的 XHR）而非 DOM 文本，提升精度。

- **D.（已作废）会话如何持续供给？**
  - 原判断"没有 session 路线建不起来"已被推翻：`uni-fundts` 与 `dataapi` 均**零鉴权**，公开 host 直连即可拿全量数据（业绩/行业/当前与历史基金级持仓）。会话供给不再是需要决策的点。

---

## 6. 决策与下一步

1. **已落地（代码）**：`fund_advisor_holdings.py` 的公开接口直连（默认）模式 + `--history` 历史持仓 + `healthcheck`（H1–H6）。数据闭环 = 概览(`FundIATGInfoAggr`) + 业绩(`getTGQuoteByFavor`) + 行业配置(`getHoldWarehouseIndustryRatio`) + 当前/历史基金级持仓(`getAdjustWarehouse` tag 0/1)。全部零鉴权、免浏览器、免正则。
2. **你（关键确认）**：
   - 「组合持仓」看板是否就展示上述四类数据即可？如够用，则接口侧已全部交付，下一步是接「市场温度计」每日微信推送的消费格式。
   - 三只关注组合（越海 XCOVSEX / 万家非凡新质驱动 JY48YPE / 省心投步步盈 UFPW1GJ）的 tgCode 已入 `advisor_watchlist.json`，如需增删直接改该文件。
3. **仍待决（低优先级）**：
   - 投顾全量列表（462 只）枚举接口尚未定位（在其它 bundle / dynamic chunk），影响"前端搜索自动解析 tgCode"；目前靠分享链接一次性取 `tgCode=`，可接受。
   - `combine-gold` 直连模块不再需要（公开 host 已覆盖），路线 D 删除。
4. **结构约束（你此前要求）**：组合持仓保持**独立接口/页面**，不并入"市场温度计"。本记录与看板代码均遵守。

---

### 附：本次实测关键证据（curl）

```
# 投顾真实后端 host（App.js 模块 62221）
combine-gold.tiantianfunds.com  (release)
combine-gold-gc.tiantianfunds.com (beta)
dataapineice.1234567.com.cn (dev)

# 持仓接口（GET，入参 tgCode）
/combine/investAdviserInfo/getHoldWarehouseIndustryRatio

# 直连实测：全部 404（tengine 网关拦截）
curl -G combine-gold.tiantianfunds.com/combine/investAdviserInfo/getHoldWarehouseIndustryRatio \
     --data-urlencode "tgCode=XCOVSEX" --data-urlencode "validmark={...}" ...
→ <title>404 Not Found</title>

# 伪造路径同样 404 → 确认是网关层未路由（与 session/cookie 无关），非路径/参数问题
```
