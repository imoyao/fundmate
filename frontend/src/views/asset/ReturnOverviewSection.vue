<template>
  <!-- 收益概览（真实 XIRR，无预测） -->
  <section>
    <SectionHeader title="收益概览" :info="xirrScopeInfo">
      <!-- #2153：口径开关与投资概览（首页）逐字同款——同一时刻两页绑定的
           参数一致，数值天然一致；口径说明挂在 info（tooltip），随开关联动 -->
      <template #action>
        <!-- #871：收益率口径切换（年化/时间加权/区间），默认 XIRR。
             与组合详情页同选项同语义；切换即重新取数 -->
        <SegmentedControl
          v-model="returnMethod"
          :options="returnMethodOptions"
          size="small"
          aria-label="收益率口径"
          @change="loadXirr"
        />
        <IncludeCashSwitch
          v-model="includeCashEquivalents"
          @change="loadXirr"
        />
      </template>
    </SectionHeader>
    <MetricGrid>
      <!-- value-color：本页主数字统一走品牌文字色 `--brand-ink`
           （WCAG AA：白底 5.86:1）。默认 `--text-primary` 是中性暖黑 #2d2a24，
           作为「这一页的主角数字」缺少品牌识别，看不出是可交互的分析结论区。
           ⚠️ 不要用 `--brand-700`：它作文字仅 3.73:1，不达标。 -->
      <MetricCard
        :title="rateCardTitle"
        :value="xirrRateLabel"
        unit="%"
        featured
        value-color="var(--brand-ink)"
        :caption="xirrCaption"
      />
      <MetricCard
        title="累计收益"
        :value="xirrReturnLabel"
        value-color="var(--brand-ink)"
        caption="当前市值 − 净投入（含已实现）"
      />
      <MetricCard
        title="当前市值"
        :value="xirrCurrentValueLabel"
        value-color="var(--brand-ink)"
        caption="在投本金的当前价值"
      />
      <MetricCard
        title="净投入"
        :value="xirrNetInvestedLabel"
        value-color="var(--brand-ink)"
        caption="累计买入 − 累计卖出/分红"
      />
    </MetricGrid>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getPortfolioXirr, type XirrData } from "@/api/performance";
import { formatAmount } from "@/utils/currency";
import { useReturnMethod } from "@/composables/useReturnMethod";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import IncludeCashSwitch from "@/components/IncludeCashSwitch/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";

/**
 * 智能分析页「收益概览」区块（#871 从 IntelligentAnalysis.vue 拆出，#980）：
 * 自含取数（家庭维度 portfolio scope）+ 口径切换 + 四张指标卡；
 * 父页经 defineExpose 的 refresh() 在「刷新数据」时一并刷新。
 *
 * 口径状态与降级规则（切换后旧数据未回来不显示、TWR 部分持仓无价格诚实提示）
 * 与组合详情 PortfolioReturnCard 共用 useReturnMethod——两页同选项同语义。
 */
const xirr = ref<XirrData | null>(null);
// #2153：XIRR「是否含现金等价物」口径——与投资概览（welcome）同语义、同默认值
// （false=剔除现金，与后端 include_cash_equivalents 默认值一致）。两页各自持本地
// 状态（issue 方案 1「切换后本地生效」），但开关与口径文案逐字一致，任一处可见、语义相同。
const includeCashEquivalents = ref(false);

const {
  returnMethod,
  returnMethodOptions,
  methodName,
  rateLabel,
  primaryRate,
  daysSkipped
} = useReturnMethod(xirr);

const rateCardTitle = computed(
  () => `${rateLabel.value} (${methodName.value})`
);
// cashflow_count=0 视为无数据，不显示假 0%；宁缺勿错口径（useReturnMethod 已判）
const xirrRateLabel = computed(() =>
  primaryRate.value == null ? null : primaryRate.value.toFixed(2)
);
const formatYuan = (n: number, p = 0) => `¥${formatAmount(n || 0, p)}`;
const formatSignedYuan = (n: number) =>
  `${n >= 0 ? "+" : "-"}${formatYuan(Math.abs(n || 0))}`;
const xirrReturnLabel = computed(() => {
  const d = xirr.value;
  return d && d.cashflow_count > 0 ? formatSignedYuan(d.total_return) : null;
});
const xirrCurrentValueLabel = computed(() => {
  const d = xirr.value;
  return d && d.cashflow_count > 0 ? formatYuan(d.current_value) : null;
});
// 展示「净投入」而不是「累计买入毛额」：同一笔钱反复买卖会重复累加，
// 毛额会把十几万本金的账户显示成上百万甚至上亿（用户会误读为投入规模）。
const xirrNetInvestedLabel = computed(() => {
  const d = xirr.value;
  if (!d || d.cashflow_count <= 0) return null;
  return formatYuan(d.net_invested ?? d.total_invested - d.total_withdrawn);
});
const xirrCaption = computed(() => {
  const d = xirr.value;
  if (!d || d.cashflow_count <= 0) return "录入交易流水后自动计算";
  const base = `基于 ${d.cashflow_count} 笔交易现金流`;
  // #871：TWR 口径下缺数据的天被引擎跳过（不当 0），跳过 >0 即如实说明
  if (daysSkipped.value > 0) {
    return `${base}；有 ${daysSkipped.value} 天数据缺失未计入`;
  }
  return base;
});

/** #2153：收益概览口径说明——沿用首段说明 + 当前口径，后半句与首页
 *  WelcomeXirrTemperature 的口径小字逐字一致（验收「语义一致」）。
 *  #871：口径说明随 method 联动，三种方法各一句自己的话。 */
const xirrScopeInfo = computed(() => {
  // #871：TWR 走日净资产序列（pnl_calendar 口径），天然含全部 active 持仓——
  // 现金等价物开关对它不生效，故 twr 下 scopeText 固定为总资产口径，
  // 不随开关显示「含/不含」（那会是误导：开关动了，数字不会动）。
  const scopeText =
    returnMethod.value === "twr"
      ? "当前口径：总资产（日净资产序列天然含货币基金等现金等价物，不受左侧开关影响）"
      : includeCashEquivalents.value
        ? "当前口径：含货币基金/逆回购/现金，反映账户总收益"
        : "当前口径：基于主动投资交易，不含货币基金等现金等价物";
  const methodText =
    returnMethod.value === "twr"
      ? "时间加权（TWR）：剔除申赎时点影响，跨账户/跨人可比"
      : returnMethod.value === "dietz"
        ? "Modified Dietz：区间线性近似，不年化，看这一段贡献多少"
        : "XIRR：资金加权年化，反映个人持有体验，受申赎时点影响";
  return `由已录入的交易现金流真实计算，录入交易后自动生成；本页不做收益预测。${scopeText}。${methodText}。`;
});

// #2153：请求序号——快速切换口径时丢弃过期响应，防止旧口径数据覆盖新口径
// （否则会出现「开关显示剔除现金、数字却是含现金」的显示与开关失步）。
let xirrReqSeq = 0;
const loadXirr = async () => {
  const seq = ++xirrReqSeq;
  try {
    const res = await getPortfolioXirr(
      "portfolio",
      undefined,
      includeCashEquivalents.value,
      returnMethod.value
    );
    if (seq !== xirrReqSeq) return;
    xirr.value = res?.data ?? null;
  } catch {
    if (seq === xirrReqSeq) xirr.value = null;
  }
};

onMounted(() => {
  void loadXirr();
});

/** 父页「刷新数据」：真刷新，不摆样子 */
defineExpose({ refresh: loadXirr });
</script>
