<script setup lang="ts">
import { computed } from "vue";
import type { WatchlistItem } from "@/api/watchlist";
import { navTextOf, safeHttpUrl } from "./quickViewModel";

const props = defineProps<{
  item: WatchlistItem;
}>();

/** 策略简介完整文本（表格列里是单行省略的，抽屉里给全文） */
const strategySummary = computed(
  () => props.item.advisor_strategy_summary || ""
);
const navText = computed(() =>
  navTextOf(props.item.advisor_nav, props.item.advisor_nav_date)
);
const sourceUrl = computed(() => safeHttpUrl(props.item.advisor_source_url));
</script>

<template>
  <!-- 投顾组合信息（#1468）：配置目标 / 产品类型 / 净值 / 策略简介 / 官方链接 -->
  <section class="wqv-sec">
    <h4 class="wqv-sec__title">投顾信息</h4>
    <dl class="wqv-list">
      <div class="wqv-row">
        <dt class="wqv-label">配置目标</dt>
        <dd class="wqv-value">
          {{ item.advisor_allocation_label || "—" }}
        </dd>
      </div>
      <div class="wqv-row">
        <dt class="wqv-label">产品类型</dt>
        <dd class="wqv-value">{{ item.advisor_product_type || "—" }}</dd>
      </div>
      <div class="wqv-row">
        <dt class="wqv-label">组合净值</dt>
        <dd class="wqv-value">{{ navText || "—" }}</dd>
      </div>
      <div v-if="strategySummary" class="wqv-row">
        <dt class="wqv-label">策略简介</dt>
        <dd class="wqv-value wqv-value--wrap">{{ strategySummary }}</dd>
      </div>
      <div v-if="sourceUrl" class="wqv-row">
        <dt class="wqv-label">官方页面</dt>
        <dd class="wqv-value">
          <a
            class="wqv-link"
            :href="sourceUrl"
            target="_blank"
            rel="noopener noreferrer"
            >前往查看</a
          >
        </dd>
      </div>
    </dl>
  </section>
</template>

<style scoped lang="scss">
@use "./wqv-base";
</style>
