<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import CardBlock from "@/components/CardBlock/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import RealtimeEstimateToggle from "@/components/RealtimeEstimateToggle/index.vue";
import { assetTypeLabel } from "@/composables/useEnumLabels";
import { useRealtimeQuotes } from "@/composables/useRealtimeQuotes";
import { resolveProduct, type ProductResolveResult } from "@/api/products";
import { isDetailAssetType, parseProductRef } from "@/utils/productIdentity";
import ProductPositionSection from "./components/ProductPositionSection.vue";

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

/** 路径段 → 产品引用；品类段不在一期白名单内时为 null（交 404 态） */
const productRef = computed(() => parseProductRef(router.currentRoute.value));

/** 原始 symbol：仅用于错误提示回显，原样展示不拼不剥 */
const rawSymbol = computed(() => router.currentRoute.value.params.symbol ?? "");

const headerTitle = computed(() => product.value?.display_name || "产品详情");
const headerSubtitle = computed(() =>
  product.value ? assetTypeLabel(product.value.asset_type) : ""
);

/** 实时估值只对场内品类有意义（场外基金走净值；基金经理无行情） */
const showRealtime = computed(() => product.value?.asset_type === "stock");

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
      market: ref.market,
      venue: ref.venue,
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
  router.push("/asset/watchlist");
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
      <CardBlock class="product-detail__hero">
        <div class="product-detail__hero-head">
          <h2 class="product-detail__hero-name">{{ product.display_name }}</h2>
          <span class="product-detail__hero-type">{{
            assetTypeLabel(product.asset_type)
          }}</span>
        </div>
        <dl class="product-detail__facts">
          <div class="product-detail__fact">
            <dt class="product-detail__fact-label">代码</dt>
            <dd class="product-detail__fact-value product-detail__symbol">
              {{ product.symbol }}
            </dd>
          </div>
          <div v-if="product.market" class="product-detail__fact">
            <dt class="product-detail__fact-label">市场</dt>
            <dd class="product-detail__fact-value">{{ product.market }}</dd>
          </div>
          <div v-if="product.venue" class="product-detail__fact">
            <dt class="product-detail__fact-label">场所</dt>
            <dd class="product-detail__fact-value">{{ product.venue }}</dd>
          </div>
          <!-- 未登录时这两项为 null（端点为可选登录），此时不渲染徽标，
               不能当成「未自选 / 未持有」——那是「未知」不是「没有」 -->
          <div
            v-if="product.in_watchlist === true"
            class="product-detail__fact"
          >
            <dt class="product-detail__fact-label">自选</dt>
            <dd class="product-detail__fact-value">已关注</dd>
          </div>
          <div
            v-if="product.has_position === true"
            class="product-detail__fact"
          >
            <dt class="product-detail__fact-label">持仓</dt>
            <dd class="product-detail__fact-value">已持有</dd>
          </div>
        </dl>
      </CardBlock>

      <!-- 我的持仓（#1966）：仅在该家庭确实持有时才拉取。
           未登录时 has_position 为 null（resolve 是「可选登录」端点），此时不渲染——
           否则等于拉一个 401 再显示成「暂无持仓」，把「未知」说成「没有」。 -->
      <ProductPositionSection
        v-if="product.has_position === true"
        :symbol="product.symbol"
        :market="product.market"
      />

      <!-- 后续区块槽位：走势 / 基金资料 等由 #1967-#1971 各自注入。
           刻意不渲染 mock 占位（设计 §10「不用 mock / 演示数据占位」）。 -->
      <slot name="sections" />
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

.product-detail__hero {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
}

.product-detail__hero-head {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
}

.product-detail__hero-name {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.product-detail__hero-type {
  font-size: 13px;
  color: var(--text-tertiary-ink);
}

.product-detail__facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: 0;
}

.product-detail__fact-label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.product-detail__fact-value {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--text-primary);
}

/* 代码原样展示：不做缩写 / 不补前缀 / 不剥市场前缀 */
.product-detail__symbol {
  font-family: var(--font-mono, monospace);
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
