<!--
  PnlAttribution · 区间收益归因（#2135）

  卡面要求：区间收益按品种 / 大类拆解贡献，入口在账本 / 组合的分析区块；
  复用 pnl 引擎唯一盈亏口径（同一次现算、同一条基准推进），前端**只展示、不计算**。

  三处口径约定（改前先读 services/pnl_calendar.py 的 compute_range_attribution）：
  - `Σ positions[].pnl ≡ 同窗 pnl-calendar 的 month_total`（后端构造保证，前端不做对账）；
  - `total_pnl === null` = 整窗无可算日，显示「—」而不是 0——0 会被读成「没赚没赔」；
  - `unpriced_positions` 持有但整窗无价，不进合计，折叠提示列出（诚实降级，卡面验收②）。

  区间档位由 `ChartRangeTabs` 提供（九档，与组合页超额走势 / 资金流动同一份
  `utils/chartRange.ts`，#3107），换算成 start_date / end_date 后传后端；
  品种 ⇄ 大类是纯前端切换（同一次响应里两组数据都有）。

  #980 拆分（纯搬运，零视觉/行为变更）：
    · 区间预设、行构造、贡献条归一、空态文案 → `attributionModel.ts`（纯函数）
    · 明细列表（含贡献条样式）→ `PnlAttributionRows.vue`
  本文件只留取数、工具条、空态与无价降级。

  列表形态（后续调整）：原来是一条按 |pnl| 混排的长列表，赚亏交替、几十个持仓能占
  整屏。现在按符号拆成「盈利 / 亏损 / 持平」三列并排（空组不渲染），每组默认只露
  前 `PREVIEW_SIZE`(=10) 条，超出才出「展开全部 N 个」。贡献条分母由本文件传给子组件
  （全量行的最大 |pnl|），保证两列可比、展开收起时条宽不跳。
-->
<template>
  <template v-if="visible">
    <SectionHeader title="收益归因" :info="sectionInfo" />
    <CardBlock class="mb-6 pnl-attribution">
      <div class="pnl-attribution__toolbar">
        <div class="pnl-attribution__total">
          <span class="pnl-attribution__total-label">区间合计</span>
          <MoneyDisplay
            v-if="data && data.total_pnl !== null"
            :value="data.total_pnl"
            size="md"
          />
          <span v-else class="pnl-attribution__total-none">—</span>
          <span
            v-if="data && !loading && !error && !data.has_any_computable"
            class="pnl-attribution__hint"
            >数据不足，无法计算区间贡献</span
          >
        </div>
        <div class="pnl-attribution__controls">
          <ChartRangeTabs v-model="rangeKey" aria-label="归因区间" />
          <SegmentedControl
            v-model="dimension"
            size="small"
            :options="DIMENSION_OPTIONS"
            aria-label="归因维度"
          />
        </div>
      </div>

      <div v-if="loading" class="pnl-attribution__placeholder">加载中…</div>
      <div v-else-if="error" class="pnl-attribution__placeholder">
        {{ error }}
      </div>
      <div v-else-if="!groups.length" class="pnl-attribution__placeholder">
        {{ emptyText }}
      </div>
      <!-- 赚的与亏的分两列并排：一眼看出方向，行数也减半（原来是一条混排长列表） -->
      <div v-else class="pnl-attribution__groups">
        <section
          v-for="group in groups"
          :key="group.key"
          class="pnl-attribution__group"
          :aria-label="`${group.label} ${group.rows.length} 个`"
        >
          <header class="pnl-attribution__group-head">
            <span
              class="pnl-attribution__group-label"
              :class="`is-${group.key}`"
              >{{ group.label }}</span
            >
          </header>
          <PnlAttributionRows :rows="visibleRowsOf(group)" :max-abs="maxAbs" />
          <button
            v-if="group.rows.length > PREVIEW_SIZE"
            type="button"
            class="pnl-attribution__more"
            :aria-expanded="expanded[group.key] === true"
            @click="toggleGroup(group.key)"
          >
            {{
              expanded[group.key] ? "收起" : `展开全部 ${group.rows.length} 个`
            }}
          </button>
        </section>
      </div>

      <!-- 无价降级：不进合计，折叠列出（卡面验收「依赖数据不足时诚实降级」） -->
      <details
        v-if="data && data.unpriced_positions.length"
        class="pnl-attribution__unpriced"
      >
        <summary>
          另有
          {{ data.unpriced_positions.length }} 个持仓因缺少价格数据未纳入归因
        </summary>
        <ul>
          <li
            v-for="u in data.unpriced_positions"
            :key="u.position_id"
            class="pnl-attribution__unpriced-item"
          >
            {{ u.name || u.symbol }}（{{ u.symbol }}）
          </li>
        </ul>
      </details>
    </CardBlock>
  </template>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import ChartRangeTabs from "@/components/ChartRangeTabs/index.vue";
import PnlAttributionRows from "./PnlAttributionRows.vue";
import {
  DIMENSION_OPTIONS,
  PREVIEW_SIZE,
  buildRows,
  computeMaxAbs,
  emptyTextFor,
  sectionInfoFor,
  splitByPnl,
  type Dimension,
  type PnlGroup
} from "./attributionModel";
import { chartRangeParams, type ChartRangeKey } from "@/utils/chartRange";
import { getPnlAttribution, type PnlAttributionPayload } from "@/api/summary";
import { useEnumLabels } from "@/composables/useEnumLabels";

defineOptions({ name: "PnlAttribution" });

const props = defineProps<{
  /**账户级：传该账户 ledger_id；与 portfolioId 互斥（后端 400） */
  ledgerId?: number;
  /**组合级：传组合 id；两者都不传 = 家庭级 */
  portfolioId?: number;
}>();

const rangeKey = ref<ChartRangeKey>("1m");
const dimension = ref<Dimension>("position");
const data = ref<PnlAttributionPayload | null>(null);
const loading = ref(false);
const error = ref("");
/** 每组的展开态；缺省 = 折叠（只露 PREVIEW_SIZE 条） */
const expanded = ref<Record<string, boolean>>({});

const { assetTypeLabel } = useEnumLabels();

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const range = chartRangeParams(rangeKey.value);
    const params: Record<string, number | string> = {
      start_date: range.start_date,
      end_date: range.end_date
    };
    if (props.ledgerId) params.ledger_id = props.ledgerId;
    if (props.portfolioId) params.portfolio_id = props.portfolioId;
    const res = await getPnlAttribution(params);
    data.value = res.data;
    // 换区间 / 换范围后重新折回「前 10」：新数据不该继承旧数据的展开态
    expanded.value = {};
  } catch (e) {
    data.value = null;
    error.value =
      e instanceof Error && e.message ? e.message : "收益归因加载失败";
  } finally {
    loading.value = false;
  }
}

watch(rangeKey, load);
watch(() => [props.ledgerId, props.portfolioId], load, { immediate: true });

/** 视图行的构造（含两种维度各自的文案差异）见 `attributionModel.buildRows` */
const rows = computed(() =>
  buildRows(data.value, dimension.value, assetTypeLabel)
);

/**
 * 明细按「盈利 / 亏损 / 持平」分组成列（#980 后续）。
 *
 * 原来是一条按 |pnl| 混排的长列表：赚的和亏的交替出现，用户得自己看符号，
 * 而且几十个持仓时这一块能占掉整屏。分组后两列并排，页高减半。
 */
const groups = computed(() => splitByPnl(rows.value));

/**
 * 贡献条分母取**全量行**（不是可见行）：
 * 展开 / 收起时条宽不跳；盈利与亏损两列也只有共用同一个分母才可比
 * ——各列各自归一的话，100 元盈利与 50 元亏损都会画成满格。
 */
const maxAbs = computed(() => computeMaxAbs(rows.value));

function visibleRowsOf(group: PnlGroup) {
  return expanded.value[group.key]
    ? group.rows
    : group.rows.slice(0, PREVIEW_SIZE);
}

function toggleGroup(key: string) {
  expanded.value = { ...expanded.value, [key]: !expanded.value[key] };
}

// 品种 ⇄ 大类是纯前端切换，行数与量级都变了，展开态必须复位
watch(dimension, () => {
  expanded.value = {};
});

const emptyText = computed(() => emptyTextFor(data.value));

const visible = computed(() => true);

const sectionInfo = computed(() => sectionInfoFor(data.value));
</script>

<style lang="scss" scoped>
.pnl-attribution__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.pnl-attribution__total {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.pnl-attribution__total-label {
  font-size: var(--text-label, 13px);
  color: var(--text-secondary);
}

.pnl-attribution__total-none {
  font-size: var(--text-num-strong, 18px);
  color: var(--text-tertiary-ink);
}

.pnl-attribution__hint {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pnl-attribution__controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.pnl-attribution__groups {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px 20px;
  align-items: start;
}

.pnl-attribution__group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.pnl-attribution__group-head {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: var(--text-label, 13px);
}

.pnl-attribution__group-label {
  font-weight: 600;
}

.pnl-attribution__group-label.is-gain {
  color: var(--color-rise-ink);
}

.pnl-attribution__group-label.is-loss {
  color: var(--color-fall-ink);
}

.pnl-attribution__group-label.is-flat {
  color: var(--text-tertiary-ink);
}

.pnl-attribution__more {
  align-self: flex-start;
  padding: 0;
  font-size: var(--text-label);
  color: var(--brand-700, var(--brand-500));
  cursor: pointer;
  background: none;
  border: none;
}

.pnl-attribution__more:hover {
  text-decoration: underline;
}

.pnl-attribution__more:focus-visible {
  outline: 2px solid var(--brand-500);
  outline-offset: 2px;
  border-radius: var(--radius-sm, 4px);
}

.pnl-attribution__placeholder {
  padding: 32px 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
}

.pnl-attribution__unpriced {
  margin-top: 12px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pnl-attribution__unpriced summary {
  cursor: pointer;
}

.pnl-attribution__unpriced ul {
  padding-left: 18px;
  margin: 6px 0 0;
}

.pnl-attribution__unpriced-item {
  line-height: 20px;
}
</style>
