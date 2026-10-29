<!--
  持仓结构面板（#2617）：资产类别占比 + 股基分列 Top N + 集中度。

  为什么股基不合并排名：股票与基金（含 ETF）的份额与价格不可比，合成一张
  「前 5 大持仓」榜单没有经济含义，还会让基金的集中度被拆成多条。故用
  SegmentedControl 切换两组，而不是并排堆两张饼图。

  #2739：视角由**账户类型**决定，不再让用户切。
  账户级作用域（`ledger-id`）下后端返回 `view`（stock/fund）——
  证券账户只看股票、基金/银行账户只看基金，此时**不渲染切换控件**。
  组合级 / 家庭级跨类型账户混合，`view` 为 null ⇒ 保留切换。

  数据全部来自后端 `position-structure`（占比、组内集中度、跨账户合并都在
  服务端算完），前端只做展示——与全站「同一份数据只算一次」的约束一致。
-->
<template>
  <div class="position-structure">
    <SectionHeader title="持仓结构" :info="panelInfo">
      <template #action>
        <SegmentedControl
          v-if="showSwitcher"
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
          :caption="`占${scopeUnit} ${classRatio('stock')} · ${groupCount('stock')} 只`"
          featured
        />
        <MetricCard
          title="基金"
          :value="classAmount('fund')"
          :caption="`占${scopeUnit} ${classRatio('fund')} · ${groupCount('fund')} 只`"
        />
        <MetricCard
          title="其他"
          :value="classAmount('other')"
          :caption="`占${scopeUnit} ${classRatio('other')}（债 / 货基 / 逆回购）`"
        />
        <MetricCard
          title="前 5 集中度"
          :value="pct(data.concentration.top5_ratio_of_total)"
          :caption="`前 5 大持仓占${scopeUnit}（含债/货基，故常高于组内集中度）`"
        />
      </MetricGrid>

      <CardBlock v-if="activeGroup" class="mt-4">
        <div class="group-head">
          <h4 class="group-title">
            {{ activeGroup.label }} Top {{ activeGroup.top.length }}
          </h4>
          <p class="group-meta">
            组内前 5 集中度 {{ pct(activeGroup.top5_ratio_of_group) }} · 占{{
              scopeUnit
            }}
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
              <th class="detail-table__num">占{{ scopeUnit }}</th>
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
          <!-- 账户级排除了走类现金的货基 ⇒ 占比分母是「持仓总额」而非账户总资产，
               必须显式说明，否则三类占比之和对不上用户心里的账户总额，像数据丢了。 -->
          <li v-if="hasCashLike">
            另有类现金
            {{ formatAmount(data.cash_like_cny) }}（货币基金等现金等价物）
            未计入上述持仓，故各类占比之和为 100% 的持仓口径，不含这部分现金。
          </li>
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
 *
 * #2739：账户级下视角由后端按账户类型判定（`data.view`），本组件**不提供切换**；
 * 组合/家庭级 `data.view` 为 null ⇒ 保留股基切换。
 */
const props = defineProps<{
  ledgerId?: number;
  portfolioId?: number;
}>();

const CLASS_OPTIONS = [
  { label: "股票", value: "stock" },
  { label: "基金", value: "fund" }
] as const;

type ClassKey = "stock" | "fund";

const activeClass = ref<ClassKey>("stock");
const data = ref<PositionStructureData | null>(null);
const loading = ref(false);
const error = ref("");

const scopeLabel = computed(() => {
  if (props.portfolioId != null) return "组合";
  if (props.ledgerId != null) return "账户";
  return "全家庭";
});

/**
 * 占比分母的称呼（账户页写「占组合」是错的：账户页的口径是本账户）。
 */
const scopeUnit = computed(() => {
  if (props.portfolioId != null) return "组合";
  if (props.ledgerId != null) return "账户";
  return "全家庭";
});

/**
 * 账户级固定视角（后端按 `ledger_type` 判定）：证券账户 → 股票，
 * 基金/银行账户 → 基金。为 null（组合/家庭级）时保留切换控件。
 */
const fixedView = computed<ClassKey | null>(() => data.value?.view ?? null);

/** 是否显示股基切换控件：仅组合/家庭级（跨类型账户混合，切换才有意义）。 */
const showSwitcher = computed(() => fixedView.value === null);

/** 账户级下走类现金的金额（货基等）——需如实告知，否则占比看着像丢了钱。 */
const hasCashLike = computed(() => (data.value?.cash_like_cny ?? 0) > 0);

const activeGroup = computed(
  () => data.value?.groups?.[fixedView.value ?? activeClass.value]
);

const panelInfo = computed(() => {
  const base =
    "钱压在哪：按股票 / 基金 / 其他拆开看占比与前 5 集中度（" +
    scopeLabel.value +
    "口径）。股票与基金分开排名——份额与价格不可比，合并榜单没有意义。";
  if (fixedView.value === null) return base;
  return (
    base +
    "本账户是" +
    (fixedView.value === "stock" ? "证券" : "基金") +
    "账户，视角已按账户类型固定，不需切换。"
  );
});

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

function groupCount(key: ClassKey): number {
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
