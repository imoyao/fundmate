<!--
  持仓结构面板（#2617）：资产类别占比 + 股基分列 Top N + 集中度。

  为什么股基不合并排名：股票与基金（含 ETF）的份额与价格不可比，合成一张
  「前 5 大持仓」榜单没有经济含义，还会让基金的集中度被拆成多条。故用
  SegmentedControl 切换两组，而不是并排堆两张饼图。

  数据全部来自后端 `position-structure`（占比、组内集中度、跨账户合并都在
  服务端算完），前端只做展示——与全站「同一份数据只算一次」的约束一致。
-->
<template>
  <div class="position-structure">
    <SectionHeader
      title="持仓结构"
      :info="
        '钱压在哪：按股票 / 基金 / 其他拆开看占比与前 5 集中度（' +
        scopeLabel +
        '口径）。股票与基金分开排名——份额与价格不可比，合并榜单没有意义。'
      "
    >
      <template #action>
        <SegmentedControl
          v-model="activeClass"
          :options="CLASS_OPTIONS"
          size="small"
          aria-label="资产类别"
        />
      </template>
    </SectionHeader>

    <el-skeleton v-if="loading" :rows="4" animated />
    <SoftBanner v-else-if="error" variant="warning" icon="ep:warning-filled">
      {{ error }}
    </SoftBanner>

    <template v-else-if="data">
      <MetricGrid>
        <MetricCard
          title="股票"
          :value="classAmount('stock')"
          :caption="`占组合 ${classRatio('stock')} · ${groupCount('stock')} 只`"
          featured
        />
        <MetricCard
          title="基金"
          :value="classAmount('fund')"
          :caption="`占组合 ${classRatio('fund')} · ${groupCount('fund')} 只`"
        />
        <MetricCard
          title="其他"
          :value="classAmount('other')"
          :caption="`占组合 ${classRatio('other')}（债 / 货基 / 逆回购）`"
        />
        <MetricCard
          title="前 5 集中度"
          :value="pct(data.concentration.top5_ratio_of_total)"
          caption="前 5 大持仓占组合（含债/货基，故常高于组内集中度）"
        />
      </MetricGrid>

      <CardBlock v-if="activeGroup" class="mt-4">
        <div class="group-head">
          <h4 class="group-title">
            {{ activeGroup.label }} Top {{ activeGroup.top.length }}
          </h4>
          <p class="group-meta">
            组内前 5 集中度 {{ pct(activeGroup.top5_ratio_of_group) }} · 占组合
            {{ pct(activeGroup.top5_ratio_of_total) }}
          </p>
        </div>

        <p v-if="activeGroup.count === 0" class="group-empty">
          该作用域没有{{ activeGroup.label }}持仓。
        </p>
        <table v-else class="detail-table">
          <thead>
            <tr>
              <th>标的</th>
              <th class="detail-table__num">市值</th>
              <th class="detail-table__num">占组合</th>
              <th class="detail-table__num">占{{ activeGroup.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in activeGroup.top" :key="row.symbol ?? row.name">
              <td>
                <span class="cell-name">{{ row.name || row.symbol }}</span>
                <span class="cell-symbol">{{ row.symbol }}</span>
                <span v-if="row.accounts > 1" class="cell-badge">
                  {{ row.accounts }} 个账户合并
                </span>
              </td>
              <td class="detail-table__num">
                {{ formatAmount(row.value_cny) }}
              </td>
              <td class="detail-table__num">{{ pct(row.ratio_of_total) }}</td>
              <td class="detail-table__num">{{ pct(row.ratio_of_group) }}</td>
            </tr>
          </tbody>
        </table>
      </CardBlock>

      <div class="structure-footnote">
        <span class="structure-footnote__label">口径说明</span>
        <ul class="notes-list">
          <li v-for="(note, i) in data.notes" :key="i">{{ note }}</li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import {
  getPositionStructure,
  type PositionStructureData
} from "@/api/summary";
import { formatAmount } from "@/utils/currency";

/**
 * 持仓结构面板（#2617）。
 *
 * 三级作用域由父页显式传：不传 = 家庭级；`portfolio-id` = 组合级；
 * `ledger-id` = 账户级（两者互斥，后端 400，父页保证）。
 */
const props = defineProps<{
  ledgerId?: number;
  portfolioId?: number;
}>();

const CLASS_OPTIONS = [
  { label: "股票", value: "stock" },
  { label: "基金", value: "fund" }
] as const;

const activeClass = ref<"stock" | "fund">("stock");
const data = ref<PositionStructureData | null>(null);
const loading = ref(false);
const error = ref("");

const scopeLabel = computed(() => {
  if (props.portfolioId != null) return "组合";
  if (props.ledgerId != null) return "账户";
  return "全家庭";
});

const activeGroup = computed(() => data.value?.groups?.[activeClass.value]);

function pct(value: number | null | undefined): string {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

function classAmount(key: string): string {
  const row = data.value?.by_asset_class.find(item => item.key === key);
  return formatAmount(row?.value_cny ?? 0);
}

function classRatio(key: string): string {
  const row = data.value?.by_asset_class.find(item => item.key === key);
  return pct(row?.ratio_of_total);
}

function groupCount(key: "stock" | "fund"): number {
  return data.value?.groups?.[key]?.count ?? 0;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const scope: { ledger_id?: number; portfolio_id?: number } = {};
    if (props.ledgerId != null) scope.ledger_id = props.ledgerId;
    if (props.portfolioId != null) scope.portfolio_id = props.portfolioId;
    const res = await getPositionStructure(scope);
    data.value = res?.data ?? null;
    if (!data.value) error.value = "持仓结构数据为空。";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "持仓结构加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => [props.ledgerId, props.portfolioId], load);
</script>

<style scoped>
.position-structure {
  display: flex;
  flex-direction: column;
}

.group-head {
  display: flex;
  gap: var(--space-standard);
  align-items: baseline;
  justify-content: space-between;
}

.group-title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.group-meta {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary);
}

.group-empty {
  margin: var(--space-standard) 0 0;
  font-size: var(--text-small);
  color: var(--text-tertiary);
}

.cell-name {
  color: var(--text-primary);
}

.cell-symbol {
  margin-left: var(--space-compact);
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.cell-badge {
  display: inline-block;
  padding: 1px var(--space-compact);
  margin-left: var(--space-compact);
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--bg-muted);
  border-radius: var(--radius-button);
}

.structure-footnote {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  margin-top: var(--space-standard);
  color: var(--text-tertiary);
}

.structure-footnote__label {
  font-size: var(--text-label);
  font-weight: 600;
}

.notes-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  padding-left: var(--space-standard);
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}
</style>
