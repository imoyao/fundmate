<!--
  复盘页「资产净值走势」区块（2026-11-28，从 IntelligentAnalysis.vue 拆出）。

  为什么拆：口径切换器要进页面，而父页已顶在 `check_vue_size.mjs` 的 400 行闸门上
  （拆前 399）。此前这段与 `useNetWorthTrend` 强内聚，搬进来后父页只管「它在第几位」
  与锚点，区块自含取数、绘图、切档重取。

  口径：`ledgerId` / `portfolioId` 都不传 = 家庭级（存量行为）；传了 = 该账户（#1181）
  / 该组合（D135）的快照序列，两者互斥。
  ⚠️ 账户档的快照天数**短于**家庭级（真库 82 天 vs 单账户 68 天），组合档更短——
  组合维度 2026-11-28 才落库，且 D62 禁止回填，故**只能从启用日起累积**。
  这不是丢数据（卡头 info 已写明「未打卡则无曲线」），但一个点是画不出走势的，
  所以组合档点数不足时在图上写一句，别让用户以为是曲线坏了。
-->
<template>
  <section id="nav-net-worth">
    <SectionHeader
      title="资产净值走势"
      info="来自每日资产快照记录，未打卡则无曲线"
    >
      <!-- 区间涨跌贴着标题走（#badge 槽）：它是这张图的「结论」，
           不该塞进右侧操作槽和控件抢位置。悬停补齐起止日期与绝对额——
           只报百分比时用户没法判断「涨了 3% 是多少钱」。 -->
      <template #badge>
        <span v-if="rangeChange" class="net-range" :title="rangeTip">
          <span>区间</span>
          <span class="net-range__value" :style="{ color: rangeColor }">
            {{ rangeLabel }}
          </span>
        </span>
      </template>
    </SectionHeader>
    <CardBlock>
      <div class="relative h-72">
        <!-- 容器必须是**普通 div**：echarts.init 读的是 el.clientWidth/clientHeight，
           `<canvas>` 未设 CSS 尺寸时按 HTML 默认 300×150 报尺寸 ⇒ 图被画成左上角
           一小块（2026-11-02 复盘页实测）。宽高交给外层 h-72 + 满宽。 -->
        <div ref="chartRef" class="h-full w-full" />
        <p
          v-if="!loading && !series.length"
          class="absolute inset-0 flex items-center justify-center text-sm"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          暂无资产快照数据
        </p>
        <!-- 组合档的历史是「从启用日起长出来」的（D62 禁止回填）：只有一个点时
             图上就是一颗点，画不出走势也不算坏数据。写明比留白诚实。 -->
        <p
          v-else-if="portfolioId != null && series.length < 2"
          class="net-accumulating"
        >
          组合快照自启用日起每日累积，目前仅
          {{ series.length }} 条，暂不足以画出走势
        </p>
      </div>
    </CardBlock>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, watch } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import { formatAmount } from "@/utils/currency";
import { useNetWorthTrend } from "./composables/useNetWorthTrend";

defineOptions({ name: "NetWorthTrendSection" });

const props = defineProps<{
  /** 账户级口径（复盘页口径切换器）；与 `portfolioId` 互斥，都不传 = 家庭级 */
  ledgerId?: number;
  /** 组合级口径（D135）；组合行只含持仓市值，历史从启用日起累积 */
  portfolioId?: number;
}>();

/** 页头「更新时间」：拆走后父页拿不到 latestSnapshot，改用事件上报 */
const emit = defineEmits<{ "latest-date": [value: string] }>();

const {
  chartRef,
  series,
  loading,
  latestSnapshot,
  rangeChange,
  load,
  renderChart
} = useNetWorthTrend(() => ({
  ledgerId: props.ledgerId,
  portfolioId: props.portfolioId
}));

/** 区间涨跌幅（首末快照之差）。涨红跌绿沿用中国市场惯例，文字用 -ink 档达 AA */
const rangeLabel = computed(() => {
  const r = rangeChange.value;
  if (!r || r.pct == null) return "";
  return `${r.pct >= 0 ? "+" : ""}${r.pct.toFixed(2)}%`;
});
const rangeColor = computed(() =>
  rangeChange.value && rangeChange.value.abs < 0
    ? "var(--color-fall-ink)"
    : "var(--color-rise-ink)"
);
/** 百分比之外补绝对额与起止日期：只说「涨 3%」，用户没法判断那是多少钱 */
const rangeTip = computed(() => {
  const r = rangeChange.value;
  if (!r) return "";
  const sign = r.abs >= 0 ? "+" : "-";
  return `${r.from} → ${r.to}，净资产 ${sign}¥${formatAmount(Math.abs(r.abs), 0)}`;
});

watch(latestSnapshot, s => emit("latest-date", s?.snapshot_date ?? ""), {
  immediate: true
});

/** 取数 → 等 DOM → 绘图。图表实例由 composable 的 useEchartsLifecycle 管理 */
const reload = async () => {
  await load();
  await nextTick();
  renderChart();
};

onMounted(reload);

// 切档：清空后重取重绘。留着上一条口径的曲线配新标题，是本次改造要消灭的静默错口径
watch(
  () => [props.ledgerId, props.portfolioId],
  async () => {
    series.value = [];
    latestSnapshot.value = null;
    await reload();
  }
);

/** 父页「刷新数据」：真刷新，不摆样子 */
defineExpose({ refresh: reload });
</script>

<style scoped lang="scss">
/* 组合档的累积提示：贴在图上而不是塞进卡头——卡头 info 是常驻口径说明，
   而这句只在「点数不足」时出现，两件事不该抢同一个位置。 */
.net-accumulating {
  position: absolute;
  right: 8px;
  bottom: 6px;
  max-width: 80%;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: right;
}

/* 区间胶囊：6px 内间隙是「标签 / 数值」的语义间距，不是布局栅格，故不走 space 令牌 */
.net-range {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  padding: 2px 8px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
  cursor: help;
  background: var(--bg-soft);
  border-radius: 999px;

  &__value {
    font-family: var(--font-mono);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
}
</style>
