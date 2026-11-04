<!--
  WatchlistWidget · 首页「置顶资产 / 持仓市值最大资产」紧凑摘要表（#1954 重做）

  ── 为什么是「紧凑摘要」而不是自选页那张表的缩小版──
  首页只有 5 行、通栏满宽、要的是「一眼看到关键数」，与自选页的高密度可排序表
  是两种形态。故本组件保留原生 <table>（不套 el-table），样式本地维护——
  这是对 el-table.css 全局基线的**已声明例外**，改样式只改 WatchlistWidgetTable。

  ── 与自选页的对齐契约（#1954，用户反馈「数据列应向自选页面对齐」）──
  本表每一列的口径 / 呈现形态都与 columnDefs.ts + columnRenderers.tsx 同源，
  改动其中一侧必须同步另一侧：
    · 产品信息  → ProductDisplay **compact** 两行（名称 / #代码 + 类型标签）
    · 最新价    → MoneyDisplay，精度 pricePrecision(asset_type)，
                  无行情 → --；静态价把 price_as_of 挂title 标注数据日期
    · 涨跌幅    → RiseFallText，null → --
    · 持仓市值  → MoneyWithRatio（金额在上 + 占比在下），金额不带正负号，
                  占比分母 = 投资类产品（投资理财大类）总市值（#2239，与自选页同口径）
    · 持仓收益  → MoneyWithRatio（金额在上 + 收益率在下），金额带正负号、不带 ¥
  刻意**不搬**的三列：「添加自选日」「持有数量」「走势」——对「即时行情摘要」
  信息价值低且会撑宽首页卡片，需要时去自选页看。

  ── 图标语义（全站统一，勿在本组件另立）──
  图钉 mdi:pin = 置顶；星标 ep:star = 特别关注。与自选页 renderActions 一致。
  此前本组件用黄色星标表示置顶，与自选页的「星标=特别关注」直接冲突（#1954）。

  ── #980 拆分 ──
  表格本体（含全部 .wl-* 样式）→ `WatchlistWidgetTable.vue`。
  本文件只保留卡片外壳、空态 / 骨架、取数与「置顶优先」的展示口径。
-->
<template>
  <div
    class="watchlist-widget rounded-2xl p-6 h-full flex flex-col"
    :style="{
      backgroundColor: 'var(--bg-card)',
      boxShadow: 'var(--shadow-raised)',
      border: '1px solid var(--border-light)'
    }"
  >
    <div class="flex-1 flex flex-col min-h-20">
      <!-- 空状态 -->
      <div
        v-if="displayItems.length === 0 && !loading"
        class="flex-1 flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer"
        :style="{
          borderColor: 'var(--border-light)',
          color: 'var(--text-tertiary-ink)'
        }"
        role="button"
        tabindex="0"
        @keydown.enter="emit('add')"
        @click="emit('add')"
      >
        <IconifyIconOffline
          icon="ep:star"
          class="text-3xl mb-3"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        />
        <p
          class="text-base font-medium mb-1"
          :style="{ color: 'var(--text-primary)' }"
        >
          暂无自选资产
        </p>
        <p class="text-xs">点击右上角「添加」开始关注资产</p>
      </div>

      <!-- 加载骨架 -->
      <div v-if="loading" class="space-y-3 w-full">
        <div
          v-for="n in 5"
          :key="n"
          class="h-10 rounded-lg animate-pulse"
          :style="{ backgroundColor: 'var(--bg-soft)' }"
        />
      </div>

      <!-- 表格 -->
      <WatchlistWidgetTable
        v-if="!loading && displayItems.length > 0"
        :items="displayItems"
        @select="handleItemClick"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { getHomeSummary, type HomeSummaryItem } from "@/api/watchlist";
import { refreshInvestmentTotalMv } from "@/composables/useInvestmentTotalMv";
import { IconifyIconOffline } from "@/components/ReIcon";
import WatchlistWidgetTable from "@/components/WatchlistWidget/WatchlistWidgetTable.vue";

/**
 * 对外抛 `add`（空态点击 → 打开添加弹窗）与 `select`（行点击 → 该产品详情）。
 *
 * #1954 曾摘掉 `select`、把行点击改成组件内部跳自选页，原因是当时详情页不存在、
 * 欢迎页的处理器是空函数（`// TODO: 跳转到资产详情`）——事件抛出去无人消费。
 * 现详情页已落地（路由 #1964 / 接线 #1965），故**恢复 `select` 并交回父组件**：
 * 取权威品类、拼详情路径属页面层职责，组件只负责「用户点了哪一行」。
 */
const emit = defineEmits<{
  add: [];
  select: [item: HomeSummaryItem];
}>();

const items = ref<HomeSummaryItem[]>([]);
const loading = ref(true);

const hasPinned = computed(() =>
  items.value.some(item => item.is_pinned === true)
);

const displayItems = computed(() => {
  if (hasPinned.value) {
    return items.value.filter(item => item.is_pinned === true);
  }
  return items.value;
});

/**
 * 行点击 / 操作按钮 → 抛 `select` 给父组件（欢迎页）跳产品详情。
 *
 * 组件自己不碰路由：品类判定（可能需回后端问权威）与详情路径拼接都已收口到
 * `utils/productDetailNav`，使用方是页面层——这正是 #1954 摘掉 select 时划的边界，
 * 现在详情页落地了，只是把它接回去。
 */
function handleItemClick(item: HomeSummaryItem) {
  emit("select", item);
}

async function fetchData() {
  loading.value = true;
  try {
    const res = await getHomeSummary();
    items.value = res.data ?? [];
  } catch (e) {
    console.error("Failed to fetch home summary:", e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  fetchData();
  refreshInvestmentTotalMv();
});
defineExpose({ hasPinned });
</script>
