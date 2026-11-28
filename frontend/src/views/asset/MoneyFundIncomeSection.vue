<!--
  货币基金收益（#947）—— 复盘页的补充解释项

  口径：万份收益 nav_per_10k × 持有份额。整数分算完后转元，**由后端算好**，
  前端只做展示、不做二次运算（正负号也用后端给的 today_income 语义）。

  与同页 XIRR 的关系：XIRR 衡量交易现金流的时间价值，本项是对持仓市值的估算，
  两者**不可相加**；本项已计入总资产。口径说明写在 SectionHeader 的 info 里，
  不再在页面上重复一段话。

  无货基时接口返回 null ⇒ 整块不渲染（`v-if`），而不是显示「¥0」——
  0 的语义是「查过了，一分没赚」，与「没有这类持仓」是两件事。

  2026-11 自 IntelligentAnalysis.vue 拆出：该页为 IA 重排补注释后逼近
  check_vue_size.mjs 的 400 行门禁，按守卫建议优先拆子组件（#980 既定做法，
  与 ReturnOverviewSection 同款：自含取数 + defineExpose refresh）。
-->
<template>
  <section v-if="income" id="nav-money-fund">
    <SectionHeader
      title="货币基金收益"
      info="按「万份收益 × 持有份额」估算，与收益概览的 XIRR 口径不同（XIRR 衡量交易现金流的时间价值），两者不可相加；本项已计入总资产"
    />
    <MetricGrid>
      <MetricCard
        title="今日收益"
        :value="todayLabel"
        value-color="var(--brand-ink)"
        :caption="todayCaption"
        featured
      />
      <MetricCard
        title="累计收益"
        :value="totalLabel"
        value-color="var(--brand-ink)"
        caption="持有期累计（万份收益 × 份额）"
      />
    </MetricGrid>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import {
  getMoneyFundIncome,
  type MoneyFundIncomeData
} from "@/api/performance";
import { formatAmount } from "@/utils/currency";

/** 账户 / 组合级口径（2026-11-28，复盘页口径切换器）：都不传 = 家庭级 */
const props = defineProps<{
  ledgerId?: number;
  portfolioId?: number;
}>();

const income = ref<MoneyFundIncomeData | null>(null);

const formatYuan = (n: number, p = 0) => `¥${formatAmount(n || 0, p)}`;
const formatSignedYuan = (n: number) =>
  `${n >= 0 ? "+" : "-"}${formatYuan(Math.abs(n || 0))}`;

const todayLabel = computed(() =>
  income.value ? formatSignedYuan(income.value.today_income) : null
);
const totalLabel = computed(() =>
  income.value ? formatSignedYuan(income.value.total_income) : null
);
const todayCaption = computed(() => {
  const d = income.value;
  if (!d) return "";
  const days = d.daily_series?.length ?? 0;
  return days > 0 ? `近${days}天有收益记录` : "暂无收益记录";
});

/** 接口异常时置 null ⇒ 隐藏整块，而不是显示 0（口径见文件头） */
const load = async () => {
  try {
    // 三档一一对应后端的 scope 枚举，不靠「没传 id 就当家庭」的推断
    const res = await getMoneyFundIncome(
      props.portfolioId != null
        ? { scope: "portfolio", portfolio_id: props.portfolioId }
        : props.ledgerId == null
          ? { scope: "family" }
          : { scope: "ledger", ledger_id: props.ledgerId }
    );
    income.value = res?.data ?? null;
  } catch {
    income.value = null;
  }
};

onMounted(load);

// 切档：清空再取——留着家庭级的收益配「本账户」标签，是静默错口径
watch(
  () => [props.ledgerId, props.portfolioId],
  () => {
    income.value = null;
    void load();
  }
);

/** 父页「刷新数据」：真刷新，不摆样子 */
defineExpose({ refresh: load });
</script>
