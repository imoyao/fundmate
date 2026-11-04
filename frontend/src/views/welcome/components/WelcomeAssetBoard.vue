<template>
  <!-- ===== 第一排：最新收益（满宽 12）===== -->
  <div class="grid grid-cols-1 xl:grid-cols-12 gap-8 mb-8">
    <div class="xl:col-span-12 flex flex-col gap-3 card-hover card-enter">
      <SectionHeader title="家庭资产看板">
        <template #action>
          <!-- 隐私模式开关：放在看板级 action 而不是卡内角落——
               它是「这个人在什么场合看」的视图状态，一旦打开，全站金额一起藏
               （MoneyDisplay 单点生效），不该伪装成某张卡的局部开关。 -->
          <el-tooltip
            placement="top"
            :content="
              masked
                ? '显示金额'
                : '隐藏金额（只保留百分比，长按卡面可临时查看）'
            "
          >
            <button
              type="button"
              class="p-2 rounded-full transition-all shadow-sm hover-card-btn"
              :style="{
                backgroundColor: 'var(--bg-soft)',
                color: 'var(--text-tertiary-ink)'
              }"
              :aria-pressed="masked ? 'true' : 'false'"
              :aria-label="masked ? '显示金额' : '隐藏金额'"
              @click="toggleMask"
            >
              <BoardActionIcon :name="masked ? 'eye-off' : 'eye'" />
            </button>
          </el-tooltip>
          <router-link
            to="/panorama"
            class="p-2 rounded-full transition-all shadow-sm hover-card-btn"
            :style="{
              backgroundColor: 'var(--bg-soft)',
              color: 'var(--text-tertiary-ink)'
            }"
            title="查看资产详情"
          >
            <BoardActionIcon name="maximize" />
          </router-link>
        </template>
      </SectionHeader>

      <TodayPnlCard
        :data="view"
        :subtitle="subtitle"
        :loading="loading"
        :error="error"
        :show-skeleton="showSkeleton"
        :total-assets="totalAssets"
        :net-assets="netAssets"
        :total-liabilities="totalLiabilities"
        :liability-ratio="liabilityRatio"
        @retry="onRetry"
      />

      <!-- 汇总失败但当日收益仍可用：把「家庭这一层缺失」说清楚，
           而不是让底注无声消失（用户会以为负债归零了） -->
      <p
        v-if="summaryError"
        class="text-xs px-1"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        家庭总资产 / 净资产 / 总负债加载失败，可点上方重新加载
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { SummaryData } from "@/api/types";
import SectionHeader from "@/components/SectionHeader/index.vue";
import TodayPnlCard from "./TodayPnlCard.vue";
import BoardActionIcon from "./BoardActionIcon.vue";
import { useTodayPnl } from "../composables/useTodayPnl";
import { usePrivacyMode } from "@/composables/usePrivacyMode";

defineOptions({ name: "WelcomeAssetBoard" });

const props = defineProps<{
  summary: SummaryData | null;
  /** 汇总请求失败（#1832）：底注降级 + 一句说明，不显示 ¥0 */
  summaryError?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();

// #119 修法 A：净资产 / 总负债一律取 `/api/summary/` 直出字段，
// 前端**不做** `总资产 − 总负债` 的二次计算（本组件曾是这条判据的落点）。
// 负债率同理直取后端 `liability_ratio`——它已经是 `总负债 ÷ 总资产` 的唯一出口。
const totalAssets = computed(() => props.summary?.total_assets_cny ?? null);
const netAssets = computed(() => props.summary?.net_assets_cny ?? null);
const totalLiabilities = computed(
  () => props.summary?.total_liabilities_cny ?? null
);
const liabilityRatio = computed(() => props.summary?.liability_ratio ?? null);

// 「投资类资产占家庭总资产」的分母必须与卡面「家庭总资产」是**同一个数**：
// 传取值器而非值，summary 异步到时 overlay 会自动重算（详见 useTodayPnl 选项注释）
const { view, loading, error, subtitle, refresh, showSkeleton } = useTodayPnl({
  householdAssets: () => props.summary?.total_assets_cny ?? null
});

// 隐私模式：状态是全局单例，这里只负责切换按钮
const { masked, toggle } = usePrivacyMode();
const toggleMask = () => toggle();

/** 卡内重试：先补自己这份，再让页面重拉汇总 / 年化（与 #1832 同一条重试链） */
const onRetry = async () => {
  await refresh();
  emit("retry");
};
</script>
