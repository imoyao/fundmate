<!--
  ProductDetailSections · 产品详情页正文区块栈
  （#980 批 B11 从 `views/product/detail.vue` 抽出）

  ## 为什么是「多根」而不是包一层 div

  `.product-detail__main` 靠 `display: flex; flex-direction: column; gap: var(--space-5)`
  控制**直接子节点**之间的节奏（设计笔记 §13）。若本组件返回单根容器，父级 flex 只剩
  一个子项，gap 全部失效 —— 一页 9~14 张卡片会互相贴住。故这里刻意不包壳，
  让这些 Section 直接成为 `.product-detail__main` 的子节点。

  ## 区块顺序不是随手排的

  「表现 → 归因 → 风险 → 配置」的递进动线（见下方各块注释），且每块的 `v-if` 按品类
  门控：基金的块不给股票渲染、经理的块只认 `manager`。改顺序或改条件前先读那块的注释，
  里面记着它为什么在这个位置（多数是被用户反馈纠正过一次的）。

  `#sections` 插槽保留：目前全仓无人传入（`grep '#sections'` 只有本文件），但它是
  「后续区块槽位」的约定入口，删掉会让后来者以为这里不支持扩展。
-->
<template>
  <!-- 识别卡（#1964）：只放事实项（代码 / 市场 / 场所 / 自选 / 持仓），
       名称与品类由 PageHeaderBar 承担。独立组件见 ProductIdentityCard。 -->
  <ProductIdentityCard :product="product" />

  <!-- 我的持仓（#1966）：仅在该家庭确实持有时才拉取。
       未登录时 has_position 为 null（resolve 是「可选登录」端点），此时不渲染——
       否则等于拉一个 401 再显示成「暂无持仓」，把「未知」说成「没有」。 -->
  <ProductPositionSection
    v-if="product.has_position === true"
    id="nav-position"
    :symbol="product.symbol"
    :market="product.market"
    :asset-type="product.asset_type"
  />

  <!-- 走势（#1967）：默认 3M、无数据显空态、口径脚注写明数据日期与来源。
       位置恢复设计 §5 的 B 位（「我的持仓」之后、「公开资料」之前）——
       #1967 合入时为避免与 #1966 持仓区块互相 rebase，曾把本卡放到 slot 之后，
       结果沉到最后一屏（关联标的 / 外链之后），与「走势是用户最关注的指标」
       这一反馈正相反。各卡现均已合入，错开锚点的理由不再成立。
       无序列数据源的品类（manager / portfolio / 无日线的 index）由组件自行
       整卡不渲染（kind 为空串），不会在首屏顶一张空卡。 -->
  <ProductTrendSection
    id="nav-trend"
    :symbol="product.symbol"
    :asset-type="product.asset_type"
    :has-position="product.has_position === true"
  />

  <!-- 交易记录（#2104）：与「我的持仓」同条件——仅当前持有时渲染。
       流水是用户自己的账本数据（transactions 表带账户字段），无持仓不可能
       有流水；原来只按「品类可交易」渲染，未持有用户点进详情页会白得一张
       「暂无交易记录」空卡 + 一次无用请求，导航胶囊还多一项死重量。
       清仓用户回看完整流水（含搜索/编辑/手续费）去账本详情页，那是管理语境；
       本页只服务当前持有人快速回看最近操作。 -->
  <ProductTransactionSection
    v-if="product.has_position === true"
    id="nav-transactions"
    :symbol="product.symbol"
    :asset-type="product.asset_type"
  />

  <!-- 基金资料（#1968）：仅基金品类渲染。首屏净值与日涨跌 + 类型/经理/规模/费率，
       缺项逐项降级为「—」。「我的成本 / 持有收益」在上面的持仓区块，不重复取数。 -->
  <ProductFundSection
    v-if="product.asset_type === 'fund'"
    id="nav-fund"
    :symbol="product.symbol"
  />

  <!-- 业绩与风险（#2029 卡 B）：仅基金品类渲染。区间收益 + 最大回撤 + 年化波动率，
       后端基于 daily_worth.acc_nav 现算，与自选域同源；货基走万份收益 / 七日年化分支。 -->
  <ProductPerformanceSection
    v-if="product.asset_type === 'fund'"
    id="nav-performance"
    :symbol="product.symbol"
  />

  <!-- 高级洞察 Pro（#2272 · #994）：**紧跟业绩与风险**（用户反馈：高价值模块
       不该沉在关联标的之后——业绩与风险答「这只产品本身表现如何」，高级洞察答
       「为什么、接下来怎样」，是同一问题的自然延伸，放一起形成
       「表现 → 归因 → 风险 → 配置」的递进动线）。建设期只放占位 + 付费墙壳，
       模块内容随后端 Phase 位逐个上线。自门控 fund / etf，见组件头。 -->
  <ProductProSection id="nav-pro" :product="product" />

  <!-- 行业配置 + 持仓明细（#2029 卡 C）：仅基金品类渲染。两张卡共用一个端点，
       容器组件取一次数分发给两个纯展示子组件（各自取数就是重复往返）。
       无披露数据时整块不渲染——持仓明细没有这层壳会渲染出一个只有标题和
       「暂无数据」的空块，正是 §6 诚实降级要避免的噪声。 -->
  <ProductHoldingsSections
    v-if="product.asset_type === 'fund'"
    anchor-id="nav-holdings"
    :symbol="product.symbol"
  />

  <!-- 相似基金（#2480）：仅基金品类渲染。韭圈儿相似度名单（免登录、
       按需取 + 后端 6h 缓存，不落库）。上游取数失败按「暂时取不到」
       降级，与「上游无相似名单」的空态分开渲染——契约要求，
       详见 services/similar_fund_service.py。相似度口径是上游黑盒，
       区块脚注注明来源；similarity 为 null（上游未打分）渲染「—」。 -->
  <ProductSimilarSection
    v-if="product.asset_type === 'fund'"
    id="nav-similar"
    :symbol="product.symbol"
  />

  <!-- 投资风格（#2478）：韭圈儿月度风格箱，晨星式 8 分类 + 漂移信号 +
       历史走势。仅基金品类渲染（股票/ETF/指数不在风格箱口径内）。 -->
  <ProductStyleSection
    v-if="product.asset_type === 'fund'"
    id="nav-style"
    :symbol="product.symbol"
  />

  <!-- 场内行情（#1969 股票 / #1974 ETF）：两者同为 `securities` 表口径、共用
       `stock-profile` 端点，故合并渲染（ETF 不是基金，不能挂 `fund-profile`——
       那个端点只查 funds 表 6 位场外裸码，ETF 场内码会 404）。
       走势曲线由上面的走势区块复用同一份行情源，本区块只补「资料 + 区间高低」。 -->
  <ProductStockSection
    v-if="product.asset_type === 'stock' || product.asset_type === 'etf'"
    id="nav-stock"
    :symbol="product.symbol"
    :market="product.market"
    :asset-type="product.asset_type"
  />

  <!-- 指数资料与估值（#2028）：仅指数品类渲染。名录 + 中证官方 PE / 股息率 +
       PE 历史分位（乐咕月频近 5 年窗口现算，#1407 拍板口径）。分位样本不足时
       给定调说明而非空指标（诚实降级）。 -->
  <ProductIndexSection
    v-if="product.asset_type === 'index'"
    id="nav-index"
    :symbol="product.symbol"
  />

  <!-- 基金经理（#1970）：仅经理品类渲染。入参是 mgr_code 而非姓名——库内实测
       119 组重名（最多「吴昊」6 位），姓名不是唯一键。注意 `product.symbol` 不是
       `managers.mgr_code` 原值：自选/搜索进来带 `MGR_` 前缀，且会被
       `resolve_product_identity` 大写化。这里**原样透传**，归一由后端
       `services/manager_code.py` 收口（曾因两边都没归一，每张经理页都空白）。
       任职起止 / 规模 / 任期回报实测填充率 0%，
       逐项降级「—」并在整片为空时给出定调说明（不显示「暂无数据」白块）。 -->
  <ProductManagerSection
    v-if="product.asset_type === 'manager'"
    id="nav-manager"
    :mgr-code="product.symbol"
  />

  <!-- 投顾组合（#1975）：仅投顾组合品类渲染。入参是平台组合码
       （advisor_portfolios.code，如 ZH012926）——路由 `/portfolio/<symbol>`
       传下来的就是它。组合类标的**不展示代码**（设计 §2.6），靠「名称 + 平台 +
       机构」识别（设计要求写的「主理人」实测填充率只有 1.9%，故锚点落在机构上）。
       调仓记录不在本区块渲染：速览抽屉已有，复用需先提取共用组件（设计 §7 已登记
       为 B6 复评项），此处先给「档案 + 指标 + 成分」。 -->
  <ProductAdvisorSection
    v-if="product.asset_type === 'portfolio'"
    id="nav-advisor"
    :code="product.symbol"
  />

  <!-- 关联标的（#1976）：指数 ↔ 场内 ETF ↔ 场外联接，对所有品类都可能有关系，
       故不按asset_type 过滤（持仓里的债券/基金同样可能有联接基金）。
       无关联降级「—」并附覆盖率说明；关系覆盖率约 66.4%（缺口见 #1419）。 -->
  <ProductRelatedSection id="nav-related" :symbol="product.symbol" />
  <!-- 后续区块槽位：走势 / 基金资料 等由 #1967-#1971 各自注入。
       刻意不渲染 mock 占位（设计 §10「不用 mock / 演示数据占位」）。 -->
  <slot name="sections" />

  <!-- 可转债深度分析（#1971）：一期只做集思录外链，不做内部详情区块。
       设计 §6/§10 拍板：本地条款已含到期收益与正股 PB（#1400 / #2575），但下修历史 /
       下修进度仍缺，与其用残缺数据做一个「看起来完整」的页面，不如交给集思录。 -->
  <BondExternalLinkCard
    v-if="product.asset_type === 'bond'"
    id="nav-bond"
    :bond-code="product.symbol"
  />

  <!-- 更多数据（#1969）：我们不做行情终端——资金流 / 盘口 / 财务这类深度数据
       交给专业站，「深度研究」外包出去比半吊子自建更诚实。品类无对应站点时
       该卡自己不渲染（见 ProductExternalLinksSection）。 -->
  <ProductExternalLinksSection
    id="nav-external"
    :symbol="product.symbol"
    :asset-type="product.asset_type"
    :market="product.market"
  />
</template>

<script setup lang="ts">
import BondExternalLinkCard from "@/components/BondExternalLinkCard/index.vue";
import type { ProductResolveResult } from "@/api/products";
import ProductAdvisorSection from "./ProductAdvisorSection.vue";
import ProductExternalLinksSection from "./ProductExternalLinksSection.vue";
// #2029：detail.vue 曾用了本组件却漏掉 import，Vue 只发「Failed to resolve component」
// warning 就静默不渲染 —— 基金详情页从上线起就没有基金资料区块。搬到这里后风险不变，
// 勿再删这一行（e2e/product-detail-* 有断言兜着）。
import ProductFundSection from "./ProductFundSection.vue";
import ProductHoldingsSections from "./ProductHoldingsSections.vue";
import ProductIdentityCard from "./ProductIdentityCard.vue";
import ProductIndexSection from "./ProductIndexSection.vue";
import ProductManagerSection from "./ProductManagerSection.vue";
import ProductPerformanceSection from "./ProductPerformanceSection.vue";
import ProductPositionSection from "./ProductPositionSection.vue";
import ProductProSection from "./ProductProSection.vue";
import ProductRelatedSection from "./ProductRelatedSection.vue";
import ProductSimilarSection from "./ProductSimilarSection.vue";
import ProductStockSection from "./ProductStockSection.vue";
import ProductStyleSection from "./ProductStyleSection.vue";
import ProductTransactionSection from "./ProductTransactionSection.vue";
import ProductTrendSection from "./ProductTrendSection.vue";

defineOptions({ name: "ProductDetailSections" });

/** resolve 出的产品实体：各区块自己按需取数，这里只做分发 */
defineProps<{ product: ProductResolveResult }>();
</script>
