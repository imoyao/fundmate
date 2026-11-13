<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { AggregationProductGroup } from "@/api/ledger";
import ProductDrawer from "@/components/ProductDrawer/index.vue";
import { PRODUCT_DISCLAIMER } from "@/components/ProductDrawer/disclaimer";
import { resolveDetailPath } from "@/utils/productDetailNav";
import AggregationAmountAnchor from "./aggregationProductDetail/AggregationAmountAnchor.vue";
import AggregationHoldingsSection from "./aggregationProductDetail/AggregationHoldingsSection.vue";

/**
 * 产品详情抽屉（#1133）：产品聚合数据 → 抽屉。
 *
 * 骨架（宽度 / 两条线 / 头部 / 唯一出口 / 免责声明）全部由 `ProductDrawer` 承担
 * （docs/design/product-detail-drawer.md）。本文件只剩编排与跳详情的路由副作用：
 * - 头部：产品名 + 代码由外壳渲染（原先自绘的红色头部与 header 内的「查看详情」已删除，
 *   出口只在 footer 一处）；
 * - 锚点：资产情况（元），可就地改总价 + 分摊预览 + 资金进出提示（#1176 / #1217，
 *   算法与取数链路一律不动）；
 * - 区块：三格信息 + 基金管理人 + 分渠道持仓详情 / 单渠道账户信息；
 * - 免责声明：文案在 `ProductDrawer/disclaimer.ts`，12–13px 单行，不再是块状提示。
 */
defineOptions({ name: "AggregationProductDetail" });

const props = withDefaults(
  defineProps<{
    /** 是否展示 */
    modelValue?: boolean;
    /** 产品聚合数据 */
    group?: AggregationProductGroup | null;
  }>(),
  {
    modelValue: false,
    group: null
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  /** 总价分摊保存成功；调用方需刷新聚合数据（#1176） */
  (e: "saved"): void;
}>();

const router = useRouter();
const detailLoading = ref(false);

/** 跳详情页那一次关闭不播收起动画（否则与路由 fade-transform 交叠，见 `_pd.scss`） */
const instantClose = ref(false);
watch(
  () => props.modelValue,
  visible => {
    if (visible) instantClose.value = false;
  }
);

/**
 * 跳详情页（#1965）。
 *
 * 聚合分组**只有 symbol**——没有 asset_type / market / venue，故一律回后端取权威品类
 * （设计 §3.3：前端不推断）。按既有范式「先关抽屉再跳」，否则抽屉会盖住详情页。
 */
async function goDetail() {
  const g = props.group;
  if (!g?.symbol || detailLoading.value) return;
  detailLoading.value = true;
  try {
    const path = await resolveDetailPath({ symbol: g.symbol });
    if (!path) {
      ElMessage.warning("该品类详情页暂未开放");
      return;
    }
    instantClose.value = true;
    emit("update:modelValue", false);
    await router.push(path);
  } catch {
    ElMessage.warning("未找到该产品，可能已下架或代码有误");
  } finally {
    detailLoading.value = false;
  }
}

/** 分摊保存成功：向上转发，调用方据此刷新聚合数据 */
function handleSaved() {
  emit("saved");
}
</script>

<template>
  <ProductDrawer
    :model-value="modelValue"
    :name="group?.name"
    :symbol="group?.symbol"
    :type-label="group?.fund_type"
    detail-hint="查看完整资料、持仓与历史记录"
    :detail-loading="detailLoading"
    :disclaimer="PRODUCT_DISCLAIMER"
    :instant-close="instantClose"
    class="product-detail-drawer"
    @update:model-value="emit('update:modelValue', $event)"
    @detail="goDetail"
  >
    <template #anchor>
      <AggregationAmountAnchor
        :group="group"
        :visible="modelValue"
        @saved="handleSaved"
      />
    </template>

    <AggregationHoldingsSection :group="group" />
  </ProductDrawer>
</template>
