<template>
  <!-- ===== 第一排：核心资产看板（#1812 后扩为满宽 12） ===== -->
  <div class="grid grid-cols-1 xl:grid-cols-12 gap-8 mb-8">
    <!-- 左侧：家庭资产看板 -->
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
      <CardBlock class="flex-1">
        <!-- 失败态（#1832）：汇总请求失败时**不显示 ¥0**。
             「0」在资产语境里是结论（我确实没资产），不是「不知道」——
             过去 `summary?.total_assets_cny ?? 0` 把两者混为一谈，首屏看着像数据被清空了。 -->
        <div
          v-if="error"
          class="flex flex-col items-center justify-center gap-3 py-10"
          role="alert"
        >
          <p class="text-sm" :style="{ color: 'var(--text-secondary)' }">
            家庭总资产加载失败，请检查网络后重试
          </p>
          <el-button size="small" type="primary" @click="emit('retry')">
            重新加载
          </el-button>
        </div>

        <div
          v-else
          class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center h-full"
        >
          <div class="lg:col-span-7 flex flex-col gap-6">
            <div>
              <p
                class="text-sm mb-2"
                :style="{ color: 'var(--text-tertiary-ink)' }"
              >
                家庭总资产
              </p>
              <div class="flex items-baseline gap-2">
                <MoneyDisplay
                  :value="summary?.total_assets_cny ?? 0"
                  size="hero"
                  :show-sign="false"
                />
                <span
                  class="text-xl font-medium"
                  :style="{ color: 'var(--text-secondary)' }"
                  >元</span
                >
              </div>
            </div>
            <div class="flex gap-6">
              <div class="flex flex-col">
                <span
                  class="text-xs mb-1"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >总盈亏（人民币）</span
                >
                <MoneyDisplay :value="summary?.total_pnl_cny ?? 0" size="xl" />
              </div>
            </div>
          </div>
          <!-- 右半边：净资产 / 总负债（#2034）。
               原「资产构成分布」环形图已移除——它消费 `category_distribution`，
               与资产总览瀑布图**同字段同口径**，同一份「资产大类」在两页画两遍；
               而按两页分工（page-split-welcome-vs-panorama-2026-08-13.md），
               **结构拆解归资产总览**，本页只讲「我有多少钱、涨没涨」。
               结构图让位后，这里补上此前一直缺席的**净资产**——它是家庭资产负债表的
               真刻度（资产 − 负债），比「总资产」更该出现在首屏；总负债同时给出，
               两者都由 `/api/summary/` 直出（`net_assets_cny` / `total_liabilities_cny`），
               非派生计算、非编造。 -->
          <div
            class="lg:col-span-5 flex flex-col justify-center gap-5 h-full"
            :style="{ borderLeft: '1px solid var(--border-light)' }"
          >
            <div class="flex flex-col">
              <span
                class="text-xs mb-1"
                :style="{ color: 'var(--text-tertiary-ink)' }"
                >家庭净资产</span
              >
              <MoneyDisplay
                :value="summary?.net_assets_cny ?? 0"
                size="xl"
                :show-sign="false"
              />
              <span
                class="text-[10px] mt-1"
                :style="{ color: 'var(--text-tertiary-ink)' }"
                >总资产 − 总负债</span
              >
            </div>
            <div
              class="flex flex-col pt-5"
              :style="{ borderTop: '1px solid var(--border-light)' }"
            >
              <span
                class="text-xs mb-1"
                :style="{ color: 'var(--text-tertiary-ink)' }"
                >家庭总负债</span
              >
              <MoneyDisplay
                :value="summary?.total_liabilities_cny ?? 0"
                size="lg"
                :show-sign="false"
              />
              <span
                class="text-[10px] mt-1"
                :style="{ color: 'var(--text-tertiary-ink)' }"
                >房贷、车贷等有息负债合计</span
              >
            </div>
          </div>
        </div>
      </CardBlock>
    </div>

    <!-- #1812：原「收益趋势」空占位已移除。
         该栏自 2026-08 起一直是「即将上线」文字占位（无 ECharts 实例、无数据请求），
         而它的承诺口径（累计收益 / 净资产随时间走势）是**净值曲线**，
         与 #1812 的「逐日盈亏日历」不是同一形态，硬塞进日历组件属口径混淆。
         逐日盈亏已由welcome 第三排的 PnlCalendar 承担；净值曲线归复盘页
         （docs/features/asset-review.md 组件 3）规划。
         左栏因此从 xl:col-span-8 扩为满宽 12，避免右侧留 4 列空洞
         （design.md MetricGrid 条：禁止右侧大片空白）。 -->
  </div>
</template>

<script setup lang="ts">
import type { SummaryData } from "@/api/types";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";

defineOptions({ name: "WelcomeAssetBoard" });

defineProps<{
  summary: SummaryData | null;
  /** 汇总请求失败（#1832）：为 true 时渲染「加载失败 + 重试」，不显示 ¥0 */
  error?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();

/*
 * #2034：本组件原持有一张「资产构成分布」环形图（口径 `category_distribution`），
 * 已整体移除——它与资产总览瀑布图同字段同口径，属结构性重复；
 * 按两页分工（`docs/working-notes/page-split-welcome-vs-panorama-2026-08-13.md`
 * 「拆解 vs 表现+目标」），结构图只归资产总览。
 * 首页因此不再需要 `distributions` 入参，`distributionLogic.ts` 亦无消费方。
 */
</script>
