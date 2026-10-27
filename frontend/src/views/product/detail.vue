<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import CardBlock from "@/components/CardBlock/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import RealtimeEstimateToggle from "@/components/RealtimeEstimateToggle/index.vue";
import { assetTypeLabel, useEnumLabels } from "@/composables/useEnumLabels";
import { useRealtimeQuotes } from "@/composables/useRealtimeQuotes";
import { resolveProduct, type ProductResolveResult } from "@/api/products";
import { isDetailAssetType, parseProductRef } from "@/utils/productIdentity";
import PageNav from "@/components/PageNav/index.vue";
import PageToc from "@/components/PageToc/index.vue";
import ProductDetailSections from "./components/ProductDetailSections.vue";
import { useProductPageNav } from "./composables/useProductPageNav";
import { useSkeletonThreshold } from "@/composables/useSkeletonThreshold";

/**
 * 产品详情页骨架（#1964 · 设计 §4 / §8）。
 *
 * 与 router/modules/product.ts 的 name: "ProductDetail" 逐字一致，
 * 否则 keep-alive 命中不到（从自选 / 持仓来回切详情要保住状态）。
 */
defineOptions({ name: "ProductDetail" });

const router = useRouter();
const loading = ref(false);
// 骨架屏 200ms 阈值（components.md PageSkeleton 铁律4）：快请求跳过骨架屏，避免闪屏
const { showSkeleton, startSkeleton, settleSkeleton } = useSkeletonThreshold();
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
  startSkeleton(); // 阈值（铁律4）：>200ms 才点亮骨架屏，快请求跳过避免闪屏
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
    settleSkeleton();
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

    <!-- 骨架屏：阈值控制（铁律4）在 loadProduct——≤200ms 返回时 showSkeleton 不置位 -->
    <PageSkeleton
      v-if="loading && showSkeleton"
      :cards="2"
      :chart-cols="1"
      :table-rows="4"
    />

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
           接管（见 .product-detail__body 内的 PageToc）。两级互斥，
           导航项由 composable 按 DOM 里真实渲染的锚点动态生成，不留死链。 -->
      <PageNav
        v-if="navItems.length > 1"
        :items="navItems"
        :active-id="navActiveId"
        @navigate="goToNavSection"
      />

      <div class="product-detail__body">
        <div ref="pageMain" class="product-detail__main">
          <!-- 正文区块栈：识别卡 → 持仓 → 走势 → 交易 → 各品类区块 → 关联标的 → 外链。
               顺序、门控条件与逐块理由见 components/ProductDetailSections.vue；
               本组件保持多根，因此这些卡仍是 .product-detail__main 的直接子节点。 -->
          <ProductDetailSections :product="product">
            <template #sections><slot name="sections" /></template>
          </ProductDetailSections>
        </div>

        <!-- xl+ 右目录 rail：与顶部胶囊共用 items/activeId（父级 composable 下发）。
             宽度账：xl（1280）视口下侧边栏展开 240px，内容区约 1040px，让出 160+20
             后卡片仍有约 860px——图表与内部横向滚动表格都够用（调研 §5.3 的取舍）。 -->
        <PageToc
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
  font-size: var(--text-display);
  color: var(--text-tertiary-ink);
}

.product-detail__empty-title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.product-detail__empty-text {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
