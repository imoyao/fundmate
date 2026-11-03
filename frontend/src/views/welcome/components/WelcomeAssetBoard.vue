<template>
  <!-- ===== 第一排：最新收益（满宽 12）===== -->
  <div class="grid grid-cols-1 xl:grid-cols-12 gap-8 mb-8">
    <div class="xl:col-span-12 flex flex-col gap-3 card-hover card-enter">
      <SectionHeader title="家庭资产看板">
        <template #action>
          <router-link
            to="/panorama"
            class="p-2 rounded-full transition-all shadow-sm hover-card-btn"
            :style="{
              backgroundColor: 'var(--bg-soft)',
              color: 'var(--text-tertiary-ink)'
            }"
            title="查看资产详情"
          >
            <IconifyIconOffline icon="ep:full-screen" class="text-lg" />
          </router-link>
        </template>
      </SectionHeader>

      <TodayPnlCard
        :data="view"
        :subtitle="subtitle"
        :loading="loading"
        :error="error"
        :net-assets="netAssets"
        :total-liabilities="totalLiabilities"
        @retry="onRetry"
      />

      <!-- 汇总失败但当日收益仍可用：把「净资产这一层缺失」说清楚，
           而不是让底注无声消失（用户会以为负债归零了） -->
      <p
        v-if="summaryError"
        class="text-xs px-1"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        家庭净资产 / 总负债加载失败，可点上方重新加载
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { SummaryData } from "@/api/types";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import TodayPnlCard from "./TodayPnlCard.vue";
import { useTodayPnl } from "../composables/useTodayPnl";

defineOptions({ name: "WelcomeAssetBoard" });

const props = defineProps<{
  summary: SummaryData | null;
  /** 汇总请求失败（#1832）：底注降级 + 一句说明，不显示 ¥0 */
  summaryError?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();

// #119 修法 A：净资产 / 总负债一律取 `/api/summary/` 直出字段，
// 前端**不做** `总资产 − 总负债` 的二次计算（本组件曾是这条判据的落点）。
const netAssets = computed(() => props.summary?.net_assets_cny ?? null);
const totalLiabilities = computed(
  () => props.summary?.total_liabilities_cny ?? null
);

const { view, loading, error, subtitle, refresh } = useTodayPnl();

/** 卡内重试：先补自己这份，再让页面重拉汇总 / 年化（与 #1832 同一条重试链） */
const onRetry = async () => {
  await refresh();
  emit("retry");
};
</script>
