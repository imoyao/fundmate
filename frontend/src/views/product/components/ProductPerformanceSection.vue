<script setup lang="ts">
import { ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getFundPerformance, type FundPerformanceResult } from "@/api/products";

/**
 * 详情页「业绩与风险」区块（#2029 卡 B · 设计卡 §4.1 #3）。
 *
 * 取数一次到位：`GET /api/products/fund-performance/` 把区间收益切面、最大回撤、年化波动率
 * 打包返回（后端基于 daily_worth.acc_nav 现算，与自选域同源）。
 *
 * 口径与降级（设计 §6 诚实降级，不编造占位值）：
 * - `fund_kind: "money"`：货币基金没有日涨跌 / 回撤口径，后端改返万份收益 + 七日年化，
 *   本区块只显这两项，不显净值型指标（避免误读「货币也跌了」）；
 * - `applicable: false` / 字段 null：逐项降级为「—」；
 * - 区间收益是**涨跌**，走 RiseFallText（涨红跌绿，与全站一致）；最大回撤 / 波动率
 *   是风险幅度而非方向性涨跌，用中性色，不把「绿」误读成「好」。
 */
const props = defineProps<{
  symbol: string;
}>();

const loading = ref(false);
const perf = ref<FundPerformanceResult | null>(null);
const failed = ref(false);

const DASH = "—";

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getFundPerformance(props.symbol);
    perf.value = res.data;
  } catch {
    // 非基金代码 / 未收录 / 网络异常：统一降级为空态，不影响详情页其余区块
    perf.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <CardBlock class="performance-section">
    <SectionHeader title="业绩与风险" />

    <p v-if="loading" class="performance-section__hint">正在读取业绩与风险…</p>

    <p
      v-else-if="failed || !perf || !perf.applicable"
      class="performance-section__hint"
    >
      暂无可展示的业绩数据
    </p>

    <!-- 货币基金：万份收益 + 七日年化（无回撤口径） -->
    <template v-else-if="perf.fund_kind === 'money'">
      <dl class="performance-section__kpi">
        <div class="performance-section__kpi-item">
          <dt class="performance-section__label">七日年化</dt>
          <dd class="performance-section__value">
            {{
              perf.annual_return_7d != null
                ? perf.annual_return_7d.toFixed(2) + "%"
                : DASH
            }}
          </dd>
        </div>
        <div class="performance-section__kpi-item">
          <dt class="performance-section__label">万份收益</dt>
          <dd class="performance-section__value">
            {{
              perf.nav_per_10k != null
                ? perf.nav_per_10k.toFixed(4) + " 元"
                : DASH
            }}
          </dd>
        </div>
      </dl>
      <p class="performance-section__footnote">
        数据来源：{{ perf.source
        }}<template v-if="perf.as_of"> · 截至 {{ perf.as_of }}</template>
        · 货币基金（万份收益 / 七日年化，无回撤口径）
      </p>
    </template>

    <!-- 场外基金：区间收益 + 风险指标 -->
    <template v-else>
      <div class="performance-section__block-label">区间收益</div>
      <dl class="performance-section__facts">
        <div
          v-for="iv in perf.intervals"
          :key="iv.key"
          class="performance-section__fact"
        >
          <dt class="performance-section__label">{{ iv.label }}</dt>
          <dd class="performance-section__value">
            <RiseFallText v-if="iv.value != null" :value="iv.value" />
            <span v-else>{{ DASH }}</span>
          </dd>
        </div>
      </dl>

      <div class="performance-section__block-label">风险</div>
      <dl class="performance-section__facts">
        <div class="performance-section__fact">
          <dt class="performance-section__label">
            最大回撤（{{ perf.max_drawdown_window || "近3年" }}）
          </dt>
          <dd class="performance-section__value">
            {{
              perf.max_drawdown != null
                ? perf.max_drawdown.toFixed(2) + "%"
                : DASH
            }}
          </dd>
        </div>
        <div class="performance-section__fact">
          <dt class="performance-section__label">年化波动率（近1年）</dt>
          <dd class="performance-section__value">
            {{
              perf.volatility_1y != null
                ? perf.volatility_1y.toFixed(2) + "%"
                : DASH
            }}
          </dd>
        </div>
      </dl>

      <p class="performance-section__footnote">
        数据来源：{{ perf.source
        }}<template v-if="perf.as_of"> · 截至 {{ perf.as_of }}</template>
        <template v-if="perf.acc_nav_caveat">
          · {{ perf.acc_nav_caveat }}</template
        >
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
.performance-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.performance-section__hint,
.performance-section__footnote {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

/* 令牌口径：`--text-secondary` 在 colors.css:33 有定义（`--text-secondary-ink` 未定义，
   写了会让整条 color 声明静默失效 → 回落浏览器默认色，暗色端直接失控）。 */
.performance-section__block-label {
  margin: var(--space-3) 0 var(--space-1);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.performance-section__label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.performance-section__value {
  margin: 0;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 区间收益 / 风险：与基金资料卡同款 facts 网格（#1969 P0，严禁 minmax(0,1fr) 塌轨） */
.performance-section__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3) var(--space-6);
  margin: 0;
}

.performance-section__fact {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

/* 货基 KPI：两枚大数字横排 */
.performance-section__kpi {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: 0;
}

.performance-section__kpi-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
</style>
