<template>
  <div class="penetration-panel">
    <SectionHeader
      title="持仓穿透"
      :info="
        '你的钱最终压在哪些行业与个股上（' +
        (data?.scheme_label ?? '') +
        '口径）。穿透仅覆盖持仓，不含房产/现金等通用资产。'
      "
    >
      <template #action>
        <el-radio-group v-model="scheme" size="small" @change="load">
          <el-radio-button value="csrc">证监会门类</el-radio-button>
          <el-radio-button value="gics">GICS</el-radio-button>
        </el-radio-group>
      </template>
    </SectionHeader>

    <el-skeleton v-if="loading" :rows="4" animated />
    <el-alert
      v-else-if="error"
      type="warning"
      :closable="false"
      :title="error"
    />

    <template v-else-if="data">
      <!-- 覆盖率：已穿透 / 未穿透，两栏分开说，不给「穿透率」一个孤立数字 -->
      <MetricGrid>
        <MetricCard
          title="已穿透"
          :value="formatAmount(data.coverage.penetrated_cny)"
          :caption="`占持仓市值 ${percent(data.coverage.penetrated_ratio)}`"
          featured
        />
        <MetricCard
          title="未穿透"
          :value="formatAmount(data.coverage.unpenetrated_cny)"
          :caption="`占持仓市值 ${percent(1 - data.coverage.penetrated_ratio)}`"
        />
        <MetricCard
          title="现金等价物"
          :value="formatAmount(data.coverage.cash_equivalent_cny)"
          caption="货基/逆回购，本质无股票敞口（非缺口）"
        />
        <MetricCard
          title="非权益部分"
          :value="formatAmount(data.industry_non_equity_cny)"
          caption="行业内合计不足 100% 的差额＝债券/现金，不是缺失"
        />
      </MetricGrid>
      <!-- 行业分布：横向条，不用饼图（行业数多，饼图读不出量级差） -->
      <CardBlock class="mt-4">
        <h4 class="panel-subtitle">行业分布</h4>
        <p
          v-if="!data.industries.length"
          class="text-sm"
          :style="{ color: 'var(--text-secondary)' }"
        >
          暂无可用的行业配置数据。
        </p>
        <ul v-else class="bar-list">
          <li v-for="row in data.industries" :key="row.code" class="bar-row">
            <span
              class="bar-name"
              :title="`${row.name}（${row.code}）· ${row.fund_count} 只基金持有`"
            >
              {{ row.name }}
            </span>
            <span class="bar-track">
              <span
                class="bar-fill"
                :style="{ width: barWidth(row.ratio_of_penetrated) }"
              />
            </span>
            <span class="bar-value">{{ percent(row.ratio_of_total) }}</span>
          </li>
        </ul>
      </CardBlock>

      <!-- 个股层：季报只披露前十大，故标明口径强度 -->
      <CardBlock class="mt-4">
        <h4 class="panel-subtitle">
          个股层 Top {{ data.stocks.length }}
          <span
            v-if="Object.keys(data.stocks_coverage.fund_count_by_basis).length"
            class="panel-subtitle-note"
          >
            （{{ basisText }}）
          </span>
        </h4>
        <ul v-if="data.stocks.length" class="bar-list">
          <li v-for="row in data.stocks" :key="row.code" class="bar-row">
            <span
              class="bar-name"
              :title="
                row.holder_fund_count
                  ? `${row.holder_fund_count} 只基金持有`
                  : '其余个股合计'
              "
            >
              {{ row.name }}
            </span>
            <span class="bar-track">
              <span
                class="bar-fill bar-fill--alt"
                :style="{ width: barWidth(row.ratio_of_total) }"
              />
            </span>
            <span class="bar-value">{{ percent(row.ratio_of_total) }}</span>
          </li>
        </ul>
        <p v-else class="text-sm" :style="{ color: 'var(--text-secondary)' }">
          暂无可穿透的个股持仓。
        </p>
      </CardBlock>
      <!-- 未穿透清单：**逐条带 reason**，把「本质无股票敞口」与「待补真缺口」分开呈现。
           不做归一化、不摊到行业上——那会把 86% 仓位的基金显示成满仓。 -->
      <CardBlock class="mt-4">
        <h4 class="panel-subtitle">未穿透构成</h4>
        <p
          v-if="!data.unpenetrated.length"
          class="text-sm"
          :style="{ color: 'var(--text-secondary)' }"
        >
          全部持仓均已穿透。
        </p>
        <table v-else class="unpen-table">
          <thead>
            <tr>
              <th>标的</th>
              <th class="num">市值</th>
              <th class="num">占比</th>
              <th>原因</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in data.unpenetrated"
              :key="`${row.asset_type}-${row.symbol}`"
            >
              <td>{{ row.name }}</td>
              <td class="num" :style="{ color: 'var(--text-primary)' }">
                {{ formatAmount(row.value_cny) }}
              </td>
              <td class="num" :style="{ color: 'var(--text-secondary)' }">
                {{ percent(row.ratio_of_total) }}
              </td>
              <td>
                <span
                  class="reason-tag"
                  :class="{
                    'reason-tag--gap': row.reason !== 'cash_equivalent'
                  }"
                >
                  {{ row.reason_label }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </CardBlock>
      <!-- 非主口径：单列且**明写它不是另一套等价分类**（实测 GICS 只标注港股） -->
      <CardBlock
        v-for="(info, key) in data.other_schemes"
        :key="key"
        class="mt-4"
      >
        <h4 class="panel-subtitle">
          {{ info.label }}
          <span class="panel-subtitle-note">非主口径</span>
        </h4>
        <el-alert type="info" :closable="false" :title="info.note" />
        <p class="text-sm mt-2" :style="{ color: 'var(--text-secondary)' }">
          该体系仅覆盖参与基金市值的 {{ percent(info.covered_ratio_of_fund) }}，
          行业合计 {{ formatAmount(info.industry_total_cny) }}， 不可与
          {{ data.scheme_label }} 主口径并列或相加。
        </p>
      </CardBlock>

      <!-- 口径说明：后端写死的 notes，原样展示（前端不改写、不隐藏） -->
      <CardBlock class="mt-4">
        <h4 class="panel-subtitle">口径说明</h4>
        <ul class="notes-list">
          <li v-for="(note, i) in data.notes" :key="i">
            {{ note }}
          </li>
        </ul>
        <p class="text-sm mt-2" :style="{ color: 'var(--text-tertiary)' }">
          数据日期 {{ data.as_of }}
        </p>
      </CardBlock>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import { getPenetration, type PenetrationData } from "@/api/summary";
import { formatAmount } from "@/utils/currency";

const scheme = ref<"csrc" | "gics">("csrc");
const data = ref<PenetrationData | null>(null);
const loading = ref(false);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const res = await getPenetration(scheme.value);
    data.value = res?.data ?? null;
    if (!data.value) error.value = "穿透数据为空。";
  } catch {
    data.value = null;
    error.value = "穿透数据加载失败。";
  } finally {
    loading.value = false;
  }
}

/** 比率一律按后端给的 0~1 值格式化；分母口径由后端决定，前端不重算 */
function percent(ratio: number) {
  return `${((ratio ?? 0) * 100).toFixed(1)}%`;
}

/** 条形宽度：以「已穿透比例」为分母（行业行），否则条形会随口径跳变 */
function barWidth(ratio: number) {
  const r = Math.max(0, Math.min(1, ratio ?? 0));
  return `${(r * 100).toFixed(2)}%`;
}

/** 个股口径强度：季报只披露前十大，半年报是全量，两者不可混看 */
const basisText = computed(() => {
  const byBasis = data.value?.stocks_coverage.fund_count_by_basis;
  if (!byBasis) return "";
  const names: Record<string, string> = {
    full: "半年报全量",
    top10: "季报前十大"
  };
  const parts = Object.entries(byBasis).map(
    ([basis, count]) => `${names[basis] ?? basis} ${count} 只`
  );
  return parts.length ? `口径：${parts.join(" / ")}` : "";
});

onMounted(load);
</script>
<style scoped lang="scss">
.penetration-panel {
  width: 100%;
}

.panel-subtitle {
  margin: 0 0 var(--space-compact);
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.panel-subtitle-note {
  margin-left: var(--space-compact);
  font-size: var(--text-small);
  font-weight: 400;
  color: var(--text-tertiary);
}

.bar-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  padding: 0;
  margin: 0;
  list-style: none;
}

.bar-row {
  display: grid;
  grid-template-columns: minmax(96px, 168px) 1fr 56px;
  gap: var(--space-compact);
  align-items: center;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.bar-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track {
  height: 8px;
  overflow: hidden;
  background: var(--bg-muted);
  border-radius: 4px;
}

.bar-fill {
  display: block;
  height: 100%;
  background: var(--color-primary);
  border-radius: 4px;
}

.bar-fill--alt {
  background: var(--color-info);
}

.bar-value {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.unpen-table {
  width: 100%;
  font-size: var(--text-small);
  border-collapse: collapse;
}

.unpen-table th,
.unpen-table td {
  padding: var(--space-compact) 0;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
}

.unpen-table th {
  font-weight: 500;
  color: var(--text-tertiary);
}

.unpen-table .num {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.reason-tag {
  display: inline-block;
  padding: 1px var(--space-compact);
  color: var(--text-secondary);
  background: var(--bg-muted);
  border-radius: var(--radius-button);
}

.reason-tag--gap {
  color: var(--color-warning, var(--text-secondary));
  background: var(--color-warning-20, var(--bg-muted));
}

.notes-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  padding-left: var(--space-standard);
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
}
</style>
