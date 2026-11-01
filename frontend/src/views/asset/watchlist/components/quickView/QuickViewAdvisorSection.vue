<script setup lang="ts">
import { computed } from "vue";
import DrawerSection from "@/components/ProductDrawer/DrawerSection.vue";
import type { WatchlistItem } from "@/api/watchlist";
import { safeHttpUrl } from "./quickViewModel";

/**
 * 「投顾信息」区块（#1468）：配置目标 / 产品类型 / 策略简介 / 官方页面。
 *
 * 组合净值不再放这里——它与涨跌一样属于「主数值」，已并进抽屉锚点
 * （设计 §6.2：同一个问题不答两遍）。`.wqv-row` 只作为既有 e2e 的定位钩子保留。
 */
const props = defineProps<{
  item: WatchlistItem | null;
}>();

/** 策略简介完整文本（表格列里是单行省略的，抽屉里给全文） */
const strategySummary = computed(
  () => props.item?.advisor_strategy_summary || ""
);
const sourceUrl = computed(() => safeHttpUrl(props.item?.advisor_source_url));
</script>

<template>
  <DrawerSection title="投顾信息">
    <dl class="pd-list">
      <div class="pd-row wqv-row">
        <dt class="pd-row__label">配置目标</dt>
        <dd class="pd-row__value">
          {{ item?.advisor_allocation_label || "—" }}
        </dd>
      </div>
      <div class="pd-row wqv-row">
        <dt class="pd-row__label">产品类型</dt>
        <dd class="pd-row__value">{{ item?.advisor_product_type || "—" }}</dd>
      </div>
      <div v-if="strategySummary" class="pd-row wqv-row">
        <dt class="pd-row__label">策略简介</dt>
        <dd class="pd-row__value pd-row__value--wrap">
          {{ strategySummary }}
        </dd>
      </div>
      <div v-if="sourceUrl" class="pd-row wqv-row">
        <dt class="pd-row__label">官方页面</dt>
        <dd class="pd-row__value">
          <a
            class="wqv-link pd-link"
            :href="sourceUrl"
            target="_blank"
            rel="noopener noreferrer"
            >前往查看</a
          >
        </dd>
      </div>
    </dl>
  </DrawerSection>
</template>
