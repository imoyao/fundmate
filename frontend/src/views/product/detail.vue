<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import CardBlock from "@/components/CardBlock/index.vue";
import BondExternalLinkCard from "@/components/BondExternalLinkCard/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import RealtimeEstimateToggle from "@/components/RealtimeEstimateToggle/index.vue";
import { assetTypeLabel, useEnumLabels } from "@/composables/useEnumLabels";
import { useRealtimeQuotes } from "@/composables/useRealtimeQuotes";
import { resolveProduct, type ProductResolveResult } from "@/api/products";
import { isDetailAssetType, parseProductRef } from "@/utils/productIdentity";
import ProductAdvisorSection from "./components/ProductAdvisorSection.vue";
import ProductExternalLinksSection from "./components/ProductExternalLinksSection.vue";
// #2029：此前模板用了本组件但漏掉 import，Vue 只发「Failed to resolve component」
// warning 就静默不渲染 —— 基金详情页从上线起就没有基金资料区块，且 e2e 未打桩
// fund-profile（落到兜底 404）反向掩盖。e2e 已补断言，勿再删这一行。
import ProductFundSection from "./components/ProductFundSection.vue";
import ProductIdentityCard from "./components/ProductIdentityCard.vue";
import ProductIndexSection from "./components/ProductIndexSection.vue";
import ProductPageNav from "./components/ProductPageNav.vue";
import ProductPageToc from "./components/ProductPageToc.vue";
import ProductPerformanceSection from "./components/ProductPerformanceSection.vue";
import ProductHoldingsSections from "./components/ProductHoldingsSections.vue";
import ProductPositionSection from "./components/ProductPositionSection.vue";
import ProductStockSection from "./components/ProductStockSection.vue";
import ProductTrendSection from "./components/ProductTrendSection.vue";
import ProductManagerSection from "./components/ProductManagerSection.vue";
import ProductRelatedSection from "./components/ProductRelatedSection.vue";
import ProductTransactionSection from "./components/ProductTransactionSection.vue";
import { useProductPageNav } from "./composables/useProductPageNav";

/**
 * 产品详情页骨架（#1964 · 设计 §4 / §8）。
 *
 * 与 router/modules/product.ts 的 name: "ProductDetail" 逐字一致，
 * 否则 keep-alive 命中不到（从自选 / 持仓来回切详情要保住状态）。
 */
defineOptions({ name: "ProductDetail" });

const router = useRouter();
const loading = ref(false);
const notFound = ref(false);
const product = ref<ProductResolveResult | null>(null);

/** 区块容器（锚点扫描与 MutationObserver 的挂载点，见 useProductPageNav） */
const pageMain = ref<HTMLElement>();

// 页内导航（#1968 子卡）：<xl 顶部锚点胶囊 + xl+ 右侧目录 rail。
// state / scroll-spy 全在 composable 里，本文件只接线——detail.vue 已近 400 行
// 门禁线（scripts/check_vue_size.mjs），不再往里塞监听逻辑。
const {
  items: navItems,
  activeId: navActiveId,
  goTo: goToNavSection
} = useProductPageNav(product, pageMain);

// 市场 / 场所标签已随识别卡移入 ProductIdentityCard（那里自行 ensure）；
// asset_type 标签（页头副标题）用模块级导入的那份（ composable 也返回同一个函数）。
const { ensure: ensureEnums } = useEnumLabels();

onMounted(() => {
  // 市场 / 场所的中文标签来自后端 /api/utils/enums（**无前端镜像**，不像 asset_type
  // 那样有同步回退），必须等拉取完成；marketLabel/venueLabel 读 enums ref，
  // 拉到的瞬间模板自动重渲染。
  void ensureEnums();
});

/** 路径段 → 产品引用；品类段不在一期白名单内时为 null（交 404 态） */
const productRef = computed(() => parseProductRef(router.currentRoute.value));

/** 原始 symbol：仅用于错误提示回显，原样展示不拼不剥 */
const rawSymbol = computed(() => router.currentRoute.value.params.symbol ?? "");

const headerTitle = computed(() => product.value?.display_name || "产品详情");
const headerSubtitle = computed(() =>
  product.value ? assetTypeLabel(product.value.asset_type) : ""
);

/** 实时估值只对场内品类有意义（场外基金走净值；指数无行情源；基金经理无行情）。
 *  ETF 自 #1974 起与股票同属场内，故一并放行。 */
const showRealtime = computed(() =>
  ["stock", "etf"].includes(product.value?.asset_type ?? "")
);

const {
  enabled: realtimeEnabled,
  status: realtimeStatus,
  lastUpdateTime: realtimeLastUpdate,
  toggle: toggleRealtime
} = useRealtimeQuotes(
  // 骨架期尚无持仓上下文（持仓区块在 #1966 接入），此处返回空集合：
  // 组合式函数仍按平台总闸 / 用户偏好接线，等持仓数据到位后在此传入该产品持仓即可。
  () => [],
  () => undefined
);

async function loadProduct() {
  const ref = productRef.value;
  if (!ref || !isDetailAssetType(ref.assetType)) {
    product.value = null;
    notFound.value = true;
    return;
  }

  loading.value = true;
  notFound.value = false;
  try {
    const { data } = await resolveProduct({
      symbol: ref.symbol,
      // 不带 market / venue（#2006）：详情页 URL 不承载消歧参数，从前这里传的
      // 永远是 undefined；消歧由后端按 symbol 判定（取证：库内无同码多实体）。
      // 路径段仅作提示：后端判定优先于此（设计 §3.3「不信任手输路径」）
      asset_type: ref.assetType
    });
    product.value = data;
  } catch {
    // 404（未识别）或网络异常一律进空态，不白屏、不抛错
    product.value = null;
    notFound.value = true;
  } finally {
    loading.value = false;
  }
}

function goWatchlist() {
  // 自选页路由是 `/watchlist`（router/modules/home.ts）。这里曾写成 `/asset/watchlist`——
  // 那条路径并不存在，会被本页路由 `/:assetType/:symbol` 抢先匹配（assetType="asset"、
  // symbol="watchlist"），于是按钮把用户送回同一个「未找到该产品」空态，还提示
  // 「代码 watchlist 暂未被收录」：自选页面路径被当成产品代码去查了。
  router.push("/watchlist");
}

watch(productRef, loadProduct, { immediate: true });
</script>

<template>
  <div class="product-detail" :style="{ backgroundColor: 'var(--bg-page)' }">
    <PageHeaderBar :title="headerTitle" :subtitle="headerSubtitle">
      <template #action>
        <RealtimeEstimateToggle
          v-if="showRealtime"
          :enabled="realtimeEnabled"
          :status="realtimeStatus"
          :last-update-time="realtimeLastUpdate"
          text="实时估值"
          @toggle="toggleRealtime()"
        />
      </template>
    </PageHeaderBar>

    <PageSkeleton v-if="loading" :cards="2" :chart-cols="1" :table-rows="4" />

    <CardBlock v-else-if="notFound" class="product-detail__empty">
      <IconifyIconOffline icon="ep:search" class="product-detail__empty-icon" />
      <p class="product-detail__empty-title">未找到该产品</p>
      <p class="product-detail__empty-text">
        代码 {{ rawSymbol }} 暂未被收录，可能已下架或代码有误。
      </p>
      <el-button type="primary" plain @click="goWatchlist">回到自选</el-button>
    </CardBlock>

    <template v-else-if="product">
      <!-- 页内导航（#1968 子卡）：<xl 顶部锚点胶囊；xl+ 由正文右侧的目录 rail
           接管（见 .product-detail__body 内的 ProductPageToc）。两级互斥，
           导航项由 composable 按 DOM 里真实渲染的锚点动态生成，不留死链。 -->
      <ProductPageNav
        v-if="navItems.length > 1"
        :items="navItems"
        :active-id="navActiveId"
        @navigate="goToNavSection"
      />

      <div class="product-detail__body">
        <div ref="pageMain" class="product-detail__main">
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

          <!-- 行业配置 + 持仓明细（#2029 卡 C）：仅基金品类渲染。两张卡共用一个端点，
               容器组件取一次数分发给两个纯展示子组件（各自取数就是重复往返）。
               无披露数据时整块不渲染——持仓明细没有这层壳会渲染出一个只有标题和
               「暂无数据」的空块，正是 §6 诚实降级要避免的噪声。 -->
          <ProductHoldingsSections
            v-if="product.asset_type === 'fund'"
            anchor-id="nav-holdings"
            :symbol="product.symbol"
          />

          <!-- 场内行情（#1969 股票 / #1974 ETF）：两者同为 `securities` 表口径、共用
               `stock-profile` 端点，故合并渲染（ETF 不是基金，不能挂 `fund-profile`——
               那个端点只查 funds 表 6 位场外裸码，ETF 场内码会 404）。
               走势曲线由上面的走势区块复用同一份行情源，本区块只补「资料 + 区间高低」。 -->
          <ProductStockSection
            v-if="
              product.asset_type === 'stock' || product.asset_type === 'etf'
            "
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
               设计 §6/§10 拍板：本地只有静态条款，YTM / 下修历史 / 正股 PB 仍缺（#1400），
               与其用残缺数据做一个「看起来完整」的页面，不如把深度分析交给集思录。 -->
          <BondExternalLinkCard
            v-if="product.asset_type === 'bond'"
            id="nav-bond"
            :bond-code="product.symbol"
          />

          <!-- 第三方数据（#1969）：我们不做行情终端——资金流 / 盘口 / 财务这类深度数据
               交给专业站，「深度研究」外包出去比半吊子自建更诚实。品类无对应站点时
               该卡自己不渲染（见 ProductExternalLinksSection）。 -->
          <ProductExternalLinksSection
            id="nav-external"
            :symbol="product.symbol"
            :asset-type="product.asset_type"
            :market="product.market"
          />
        </div>

        <!-- xl+ 右目录 rail：与顶部胶囊共用 items/activeId（父级 composable 下发）。
             宽度账：xl（1280）视口下侧边栏展开 240px，内容区约 1040px，让出 160+20
             后卡片仍有约 860px——图表与内部横向滚动表格都够用（调研 §5.3 的取舍）。 -->
        <ProductPageToc
          v-if="navItems.length > 1"
          :items="navItems"
          :active-id="navActiveId"
          @navigate="goToNavSection"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.product-detail {
  min-height: 100%;
  padding: var(--space-6);
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

/* 页内导航两级布局（#1968 子卡）：<xl 单列（胶囊在正文上方整条横跨）；
   xl+ 主列 + 160px 右目录 rail，列间距 20px。 */
.product-detail__body {
  display: flex;
  gap: var(--space-5);
}

/* 区块纵向节奏：设计笔记（product-detail-page-design-2026-10-08.md §13）写明
   「间距由容器 gap 控制」，但实现漏了这层——实测卡片相贴（相邻 gap 全 0）。
   借页内导航接线一并补上：取 --space-5（20px），与探市页卡片节奏一致；
   本页卡片密度高（一页 9~14 张），不用 --space-section 的 48px。 */
.product-detail__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-5);
  min-width: 0;
}

.product-detail__empty {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.product-detail__empty-icon {
  font-size: 32px;
  color: var(--text-tertiary-ink);
}

.product-detail__empty-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.product-detail__empty-text {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary-ink);
}
</style>
