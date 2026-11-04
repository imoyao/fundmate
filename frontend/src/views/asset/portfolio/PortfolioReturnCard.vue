<template>
  <!-- 组合收益（#871：XIRR / TWR / Modified Dietz 三口径可切，默认 XIRR） -->
  <CardBlock class="mb-6">
    <SectionHeader :title="sectionTitle" :info="RETURN_METHOD_TIP">
      <template #action>
        <SegmentedControl
          v-model="returnMethod"
          :options="returnMethodOptions"
          size="small"
          aria-label="收益率口径"
          @change="fetchXirr"
        />
        <IncludeCashSwitch
          v-model="includeCashEquivalents"
          @change="fetchXirr"
        />
        <el-button size="small" :loading="xirrLoading" @click="fetchXirr">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
        </el-button>
      </template>
    </SectionHeader>
    <div v-if="xirrData" class="xirr-grid">
      <div class="xirr-item">
        <span class="xirr-label">{{ rateLabel }}</span>
        <div class="xirr-value--lg">
          <RiseFallText v-if="primaryRate !== null" :value="primaryRate" />
          <span v-else>—</span>
        </div>
      </div>
      <div class="xirr-item xirr-item--ml">
        <span class="xirr-label">当前市值</span>
        <div class="xirr-value">
          <MoneyDisplay :value="xirrData.current_value" :show-sign="false" />
        </div>
      </div>
      <div class="xirr-item">
        <span class="xirr-label">净投入</span>
        <div class="xirr-value">
          <MoneyDisplay :value="netInvested" :show-sign="false" />
        </div>
      </div>
      <div class="xirr-item">
        <span class="xirr-label">累计收益</span>
        <div class="xirr-value">
          <MoneyDisplay :value="xirrData.total_return" />
        </div>
      </div>
    </div>
    <div v-else-if="!xirrLoading" class="xirr-empty">点击刷新获取收益数据</div>
    <div v-else class="xirr-empty">计算中...</div>
    <!-- 口径小字：把「资金流水」和「盈亏」分开讲清，避免用户把累计买入毛额当成投入本金 -->
    <div v-if="metricsNote" class="xirr-note">{{ metricsNote }}</div>
    <!-- #871：TWR 口径下部分持仓无历史价格序列时的诚实提示（不缺数据画成 0） -->
    <div v-if="unvaluedHint" class="xirr-note">{{ unvaluedHint }}</div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { getPortfolioXirr, type XirrData } from "@/api/performance";
import { formatAmount } from "@/utils/currency";
import {
  RETURN_METHOD_TIP,
  useReturnMethod
} from "@/composables/useReturnMethod";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import IncludeCashSwitch from "@/components/IncludeCashSwitch/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";

/**
 * 组合收益卡（#871 从 portfolio/detail.vue 拆出，#980 上帝页面拆分）：
 * 自含「取数 + 口径切换 + 展示」，父页只传 portfolioId。
 * 网格样式（.xirr-grid 等）与组合货基卡共用，留在父页 scoped 样式里
 * 以 :deep() 下发（welcome/index.vue 同款约定）；.xirr-note 仅本卡用，随卡走。
 */
const props = defineProps<{ portfolioId: number }>();

const xirrData = ref<XirrData | null>(null);
const xirrLoading = ref(false);
// #1354：年化收益是否纳入现金等价物；默认 false=仅主动投资，反映真实投资水准
const includeCashEquivalents = ref(false);

const {
  returnMethod,
  returnMethodOptions,
  methodName,
  rateLabel,
  primaryRate,
  daysSkipped
} = useReturnMethod(xirrData);

// 注意 `methodName` 是 computed ref：在模板里会自动解包，但在 script 的模板字符串里
// 不解包 —— 少写 `.value` 会把 ref 对象拼成 `[object Object]`（曾上线为
// 「组合收益（[object Object]）」）。
const sectionTitle = computed(() => `组合收益（${methodName.value}）`);

/**
 * 净投入 = 累计买入 − 累计卖出/分红（后端 `net_invested`）。
 *
 * 为什么不展示 `total_invested`（累计买入毛额）：同一笔钱反复买卖会被重复累加，
 * 一个本金十几万的账户交易几年后可显示成上亿，用户会误以为「投了这么多钱」。
 * 旧响应没有该字段时按同一定义兜底，保持不显示错数。
 */
const netInvested = computed(() => {
  const d = xirrData.value;
  if (!d) return 0;
  return d.net_invested ?? d.total_invested - d.total_withdrawn;
});

/** 口径小字：把资金流水与盈亏分开讲清楚（用户反馈「描述不清晰」） */
const metricsNote = computed(() => {
  const d = xirrData.value;
  if (!d || d.cashflow_count <= 0) return "";
  const fmt = (n: number) => `¥${formatAmount(n || 0, 2)}`;
  return (
    `净投入 = 累计买入 ${fmt(d.total_invested)} − 累计卖出/分红 ${fmt(d.total_withdrawn)}；` +
    "累计收益 = 当前市值 − 净投入（已实现 + 未实现一起算）"
  );
});

/** TWR 口径下缺数据跳过天数的提示（诚实降级，不缺数据画成 0） */
const unvaluedHint = computed(() =>
  daysSkipped.value > 0
    ? `有 ${daysSkipped.value} 天数据缺失，未计入时间加权收益`
    : ""
);

async function fetchXirr() {
  xirrLoading.value = true;
  try {
    const res = await getPortfolioXirr(
      "portfolio",
      props.portfolioId,
      includeCashEquivalents.value,
      returnMethod.value
    );
    xirrData.value = res.data;
  } catch {
    ElMessage.error("获取收益率失败");
  } finally {
    xirrLoading.value = false;
  }
}

// 挂载条件由父页 v-if="portfolio" 把关（复刻拆出前「组合存在才拉收益率」）；
// 这里的 watch 管路由参数变化（切到别的组合 id 重取）与无效 id 防护。
watch(
  () => props.portfolioId,
  id => {
    if (Number.isFinite(id) && id > 0) void fetchXirr();
  },
  { immediate: true }
);
</script>

<style scoped>
/* #871：口径降级提示（如 TWR 下部分持仓无历史价格）——弱化小字，不抢主数字 */
.xirr-note {
  margin-top: var(--space-compact);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
