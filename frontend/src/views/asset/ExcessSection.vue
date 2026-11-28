<template>
  <!-- 区间表现 vs 基准（#2134 原在持仓分析页，2026-11-28 随页面合并迁入复盘页）。
       四卡口径全部来自后端，前端不二次计算（`utils/benchmarkExcess` 只做文案与配色）。 -->
  <section id="nav-excess" class="excess-section">
    <SectionHeader title="区间表现" :info="sectionInfo" />

    <MetricGrid>
      <MetricCard
        title="区间收益"
        :value="rangeRateText"
        unit="%"
        :caption="`${RANGE_LABEL} · ${excess?.start_date ?? ''} ~ ${excess?.end_date ?? ''}`"
        :value-color="rangeRateColor"
        featured
      />
      <MetricCard
        title="区间盈亏"
        :value="rangePnlValue"
        :caption="RANGE_LABEL"
      />
      <MetricCard
        title="基准同期"
        :value="benchmarkValue"
        unit="%"
        :caption="benchmarkCaption"
      />
      <MetricCard
        title="超额收益"
        :value="excessValue"
        unit="%"
        :caption="excessCaption"
        :value-color="excessColor"
      />
    </MetricGrid>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import { getBenchmarkExcess, type BenchmarkExcessResult } from "@/api/summary";
import {
  benchmarkCaptionOf,
  excessCaptionOf,
  excessColorOf,
  excessValueText,
  excessDateRange,
  EXCESS_RANGE_DAYS
} from "@/utils/benchmarkExcess";
import { formatAmount } from "@/utils/currency";

/** 账户 / 组合级口径；都不传 = 家庭级（与同页其余区块一致） */
const props = defineProps<{
  ledgerId?: number;
  portfolioId?: number;
}>();

defineOptions({ name: "AnalysisExcessSection" });

/** 区间口径与组合详情页同一个 util 出口（近 N 天），不在这里另设常量 */
const RANGE_LABEL = `近 ${EXCESS_RANGE_DAYS} 天`;

/** 口径说明：说清「比的是谁、比的是哪一段」，避免在卡面上再写一遍 */
const sectionInfo = `${RANGE_LABEL}收益率与宽基指数同期表现的差额；区间由后端按自然日推算，前端不传起止日`;

const excess = ref<BenchmarkExcessResult | null>(null);

const load = async () => {
  try {
    const params: {
      start_date: string;
      end_date: string;
      ledger_id?: number;
      portfolio_id?: number;
    } = { ...excessDateRange() };
    if (props.ledgerId != null) params.ledger_id = props.ledgerId;
    if (props.portfolioId != null) params.portfolio_id = props.portfolioId;
    const res = await getBenchmarkExcess(params);
    excess.value = res.data;
  } catch {
    // 诚实降级：整组「--」，不打断页面主体（与组合详情页同款约定）
    excess.value = null;
  }
};

onMounted(load);

// 切档：先清空再取。留着家庭级的四张卡配「只看某账户」的标签，是静默错口径
watch(
  () => [props.ledgerId, props.portfolioId],
  () => {
    excess.value = null;
    void load();
  }
);

const rangeRateText = computed(() =>
  excess.value?.range_rate == null ? null : excess.value.range_rate.toFixed(2)
);
const rangeRateColor = computed(() => {
  const v = excess.value?.range_rate;
  if (v == null || v === 0) return "";
  return v > 0 ? "var(--color-rise)" : "var(--color-fall)";
});
const rangePnlValue = computed(() =>
  excess.value?.range_pnl == null ? null : formatAmount(excess.value.range_pnl)
);
const benchmarkValue = computed(() =>
  excess.value?.benchmark?.range_return == null
    ? null
    : excess.value.benchmark.range_return.toFixed(2)
);
const benchmarkCaption = computed(() =>
  benchmarkCaptionOf(excess.value, RANGE_LABEL)
);
const excessValue = computed(() => excessValueText(excess.value));
const excessCaption = computed(() =>
  excessCaptionOf(excess.value, RANGE_LABEL)
);
const excessColor = computed(() => excessColorOf(excess.value));

/** 父页「刷新数据」：真刷新，不摆样子 */
defineExpose({ refresh: load });
</script>

<style lang="scss" scoped>
/* 合并后内容区约 900px（复盘页有右侧目录 rail，原持仓分析页没有，那边是 ~1150px）。
   四卡 + featured 共 5 份宽度（400 + 200×3）加 gap ≈ 1024px，窄容器里放不下一行，
   于是第 4 张「超额收益」掉到第二行、被 flex-grow 拉满成 902px 的孤卡——内容靠左，
   右侧一大片空，而上方三张只有 218px。旧页一行 435+218+218+218 是好的，缩容器后坏掉。
   改成 2×2：行数不变（本来就两行），但每行都填满、不再有孤卡，主卡仍是最大的那张。
   控制手段按 MetricGrid 头部注释的指引做外层变量覆盖（它已删掉 `columns` 假 API）。 */
.excess-section :deep(.metric-grid) {
  --metric-basis: 280px;
}
</style>
