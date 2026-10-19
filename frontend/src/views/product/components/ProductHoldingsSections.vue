<script setup lang="ts">
import { ref, watch } from "vue";
import ProductHoldingSection from "./ProductHoldingSection.vue";
import ProductIndustrySection from "./ProductIndustrySection.vue";
import {
  getFundHoldingsDetail,
  type FundHoldingsDetailResult
} from "@/api/products";

/**
 * 详情页「行业配置 + 持仓明细」容器（#2029 卡 C · 设计卡 §4.1 #4 #5）。
 *
 * **为什么有这层容器**：两张卡共用一个端点 `GET /api/products/fund-holdings-detail/`
 * （设计卡 §4.1：两者同属持仓穿透、同一次 job 落库、同一条「取最新报告期 + 选口径」
 * 逻辑）。若让两张卡各自 `watch` + 取数，就是同一个响应被请求两次 ——
 * 详情页每加一张卡都多一次往返，正是 #1968 起就在收敛的反模式。
 *
 * 取数在此处一次完成，两个子组件都是纯展示（props 驱动，无副作用）。
 *
 * 两张卡**各自独立降级**：只有行业配置没有个股披露、或反之时，只渲染有值的那张，
 * 不因为另一张空就把整块藏掉 —— 后端用 `has_industry` / `has_holding` 区分。
 */

const props = defineProps<{
  symbol: string;
  /** 页内导航锚点 id（#1968 子卡）。挂在根节点上：无披露数据 / 未收录时整块
      不渲染，锚点随之消失，导航项由 useProductPageNav 的 DOM 存在性过滤收走，
      不会留死链。多根组件吃不到父级的 attribute fallthrough（Vue 会丢弃并告警），
      故由 prop 显式下发。 */
  anchorId?: string;
}>();

const loading = ref(false);
const detail = ref<FundHoldingsDetailResult | null>(null);
const failed = ref(false);

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getFundHoldingsDetail(props.symbol);
    detail.value = res.data;
  } catch {
    // 非基金代码 / 未收录 / 网络异常：静默降级，不影响详情页其余区块。
    // 与卡 A 的教训一致——这里是「没有持仓可穿透」而非「页面出错」，
    // 抛错打断整页是错的。
    detail.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <!-- 单根容器：#1968 页内导航的锚点宿主（多根无法被父级挂 id，见 anchorId 注释）。
       根节点带 v-if，无披露数据 / 未收录时不渲染——与旧版「整块不渲染」语义一致。 -->
  <div
    v-if="detail?.applicable || failed"
    :id="anchorId"
    class="product-holdings"
  >
    <template v-if="detail?.applicable">
      <ProductIndustrySection
        v-if="detail.has_industry"
        :detail="detail"
        :source="detail.source"
      />

      <ProductHoldingSection
        v-if="detail.has_holding"
        :detail="detail"
        :source="detail.source"
      />
    </template>

    <!-- 取数失败才提示；「无披露数据」是常态（多数基金未到披露期），不打扰用户 -->
    <p v-else-if="failed" class="product-holdings__hint">
      持仓数据读取失败，可稍后重试
    </p>
  </div>
</template>

<style scoped>
/* 与 .product-detail__main 同一套纵向节奏（gap 由容器给，见 detail.vue） */
.product-holdings {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.product-holdings__hint {
  padding: var(--space-3);
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}
</style>
