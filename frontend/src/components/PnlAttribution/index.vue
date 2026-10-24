<!--
  PnlAttribution · 区间收益归因（#2135）

  卡面要求：区间收益按品种 / 大类拆解贡献，入口在账本 / 组合的分析区块；
  复用 pnl 引擎唯一盈亏口径（同一次现算、同一条基准推进），前端**只展示、不计算**。

  三处口径约定（改前先读 services/pnl_calendar.py 的 compute_range_attribution）：
  - `Σ positions[].pnl ≡ 同窗 pnl-calendar 的 month_total`（后端构造保证，前端不做对账）；
  - `total_pnl === null` = 整窗无可算日，显示「—」而不是 0——0 会被读成「没赚没赔」；
  - `unpriced_positions` 持有但整窗无价，不进合计，折叠提示列出（诚实降级，卡面验收②）。

  区间预设由前端算（近1月 / 近3月 / 今年 / 近1年），传 start_date / end_date 给后端；
  品种 ⇄ 大类是纯前端切换（同一次响应里两组数据都有）。
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
          <SegmentedControl
            v-model="rangeKey"
            size="small"
            :options="RANGE_OPTIONS"
            aria-label="归因区间"
          />
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
      <div v-else-if="!rows.length" class="pnl-attribution__placeholder">
        {{
          data && !data.has_any_computable
            ? "数据不足，无法计算区间贡献"
            : "区间内没有可归因的持仓"
        }}
      </div>
      <ul v-else class="pnl-attribution__list">
        <li v-for="row in rows" :key="row.key" class="pnl-attribution__row">
          <div class="pnl-attribution__identity">
            <span class="pnl-attribution__name" :title="row.name">{{
              row.name
            }}</span>
            <span class="pnl-attribution__sub">{{ row.sub }}</span>
          </div>
          <div class="pnl-attribution__bar-wrap" aria-hidden="true">
            <span
              class="pnl-attribution__bar"
              :class="
                row.pnl > 0 ? 'is-rise' : row.pnl < 0 ? 'is-fall' : 'is-zero'
              "
              :style="{ width: barWidth(row) }"
            />
          </div>
          <div class="pnl-attribution__figures">
            <MoneyDisplay :value="row.pnl" size="sm" />
            <span class="pnl-attribution__pct">
              <template v-if="row.pct !== null"
                >{{ row.pct > 0 ? "+" : "" }}{{ row.pct.toFixed(2) }}%</template
              >
              <template v-else>—</template>
            </span>
          </div>
        </li>
      </ul>

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
import { getPnlAttribution, type PnlAttributionPayload } from "@/api/summary";
import { useEnumLabels } from "@/composables/useEnumLabels";

defineOptions({ name: "PnlAttribution" });

const props = defineProps<{
  /**账户级：传该账户 ledger_id；与 portfolioId 互斥（后端 400） */
  ledgerId?: number;
  /**组合级：传组合 id；两者都不传 = 家庭级 */
  portfolioId?: number;
}>();

type RangeKey = "1m" | "3m" | "ytd" | "1y";
const RANGE_OPTIONS: ReadonlyArray<{ label: string; value: RangeKey }> = [
  { label: "近1月", value: "1m" },
  { label: "近3月", value: "3m" },
  { label: "今年", value: "ytd" },
  { label: "近1年", value: "1y" }
];

type Dimension = "position" | "category";
const DIMENSION_OPTIONS: ReadonlyArray<{ label: string; value: Dimension }> = [
  { label: "品种", value: "position" },
  { label: "大类", value: "category" }
];

const rangeKey = ref<RangeKey>("1m");
const dimension = ref<Dimension>("position");
const data = ref<PnlAttributionPayload | null>(null);
const loading = ref(false);
const error = ref("");

const { assetTypeLabel } = useEnumLabels();

function fmtDate(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

/**区间预设 → 闭区间（end=今日；今年=1月1日起；其余按月回退） */
function presetRange(key: RangeKey): { start_date: string; end_date: string } {
  const end = new Date();
  const start = new Date();
  if (key === "ytd") {
    start.setMonth(0, 1);
  } else {
    const months = key === "1m" ? 1 : key === "3m" ? 3 : 12;
    start.setMonth(start.getMonth() - months);
  }
  return { start_date: fmtDate(start), end_date: fmtDate(end) };
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const range = presetRange(rangeKey.value);
    const params: Record<string, number | string> = {
      start_date: range.start_date,
      end_date: range.end_date
    };
    if (props.ledgerId) params.ledger_id = props.ledgerId;
    if (props.portfolioId) params.portfolio_id = props.portfolioId;
    const res = await getPnlAttribution(params);
    data.value = res.data;
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

type ViewRow = {
  key: string;
  name: string;
  sub: string;
  pnl: number;
  pct: number | null;
};

const rows = computed<ViewRow[]>(() => {
  if (!data.value) return [];
  if (dimension.value === "category") {
    return data.value.categories.map(c => ({
      key: c.asset_type,
      name: assetTypeLabel(c.asset_type),
      sub: `${c.positions_count} 只`,
      pnl: c.pnl,
      pct: c.pct
    }));
  }
  return data.value.positions.map(r => ({
    key: String(r.position_id),
    name: r.name || r.symbol,
    sub: r.asset_type
      ? `${r.symbol} · ${assetTypeLabel(r.asset_type)}`
      : r.symbol,
    pnl: r.pnl,
    pct: r.pct
  }));
});

/**贡献条：按当前视图最大 |pnl| 归一（纯视觉，不影响数值展示） */
const maxAbs = computed(() =>
  rows.value.reduce((m, r) => Math.max(m, Math.abs(r.pnl)), 0)
);

function barWidth(row: ViewRow): string {
  if (maxAbs.value <= 0) return "0%";
  return `${(Math.abs(row.pnl) / maxAbs.value) * 100}%`;
}

const visible = computed(() => true);

const sectionInfo = computed(
  () =>
    `选定区间内各持仓对总盈亏的贡献拆解${
      data.value ? `（${data.value.start_date} ~ ${data.value.end_date}）` : ""
    }；逐品种贡献之和与区间合计一致，已实现盈亏含在对应品种内。`
);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

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

.pnl-attribution__placeholder {
  padding: 32px 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
}

.pnl-attribution__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.pnl-attribution__row {
  display: grid;
  grid-template-columns: minmax(120px, 2fr) minmax(80px, 3fr) minmax(
      120px,
      1fr
    );
  gap: 12px;
  align-items: center;
}

.pnl-attribution__identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.pnl-attribution__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label, 13px);
  color: var(--text-primary);
  white-space: nowrap;
}

.pnl-attribution__sub {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.pnl-attribution__bar-wrap {
  position: relative;
  height: 8px;
  overflow: hidden;
  background: var(--bg-soft);
  border-radius: 4px;
}

.pnl-attribution__bar {
  display: block;
  height: 100%;
  border-radius: 4px;
  transition: width 0.25s ease;
}

.pnl-attribution__bar.is-rise {
  background: var(--color-rise);
}

.pnl-attribution__bar.is-fall {
  background: var(--color-fall);
}

.pnl-attribution__bar.is-zero {
  background: var(--el-border-color);
}

.pnl-attribution__figures {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: flex-end;
}

.pnl-attribution__pct {
  min-width: 56px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
  text-align: right;
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

@include bp.below("sm") {
  .pnl-attribution__row {
    grid-template-columns: minmax(0, 1fr) minmax(80px, 1.5fr) auto;
  }
}
</style>
