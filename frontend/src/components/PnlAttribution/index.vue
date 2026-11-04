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

  #980 拆分（纯搬运，零视觉/行为变更）：
    · 区间预设、行构造、贡献条归一、空态文案 → `attributionModel.ts`（纯函数）
    · 明细列表（含贡献条样式）→ `PnlAttributionRows.vue`
  本文件只留取数、工具条、空态与无价降级。
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
        {{ emptyText }}
      </div>
      <PnlAttributionRows v-else :rows="rows" />

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
import PnlAttributionRows from "./PnlAttributionRows.vue";
import {
  DIMENSION_OPTIONS,
  RANGE_OPTIONS,
  buildRows,
  emptyTextFor,
  presetRange,
  sectionInfoFor,
  type Dimension,
  type RangeKey
} from "./attributionModel";
import { getPnlAttribution, type PnlAttributionPayload } from "@/api/summary";
import { useEnumLabels } from "@/composables/useEnumLabels";

defineOptions({ name: "PnlAttribution" });

const props = defineProps<{
  /**账户级：传该账户 ledger_id；与 portfolioId 互斥（后端 400） */
  ledgerId?: number;
  /**组合级：传组合 id；两者都不传 = 家庭级 */
  portfolioId?: number;
}>();

const rangeKey = ref<RangeKey>("1m");
const dimension = ref<Dimension>("position");
const data = ref<PnlAttributionPayload | null>(null);
const loading = ref(false);
const error = ref("");

const { assetTypeLabel } = useEnumLabels();

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

/** 视图行的构造（含两种维度各自的文案差异）见 `attributionModel.buildRows` */
const rows = computed(() =>
  buildRows(data.value, dimension.value, assetTypeLabel)
);

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
