<!--
  同类风险榜（#167 · 按指标横向筛的列表页）

  承接 CNB #167 的残留项 4：后端 `GET /api/products/fund-risk-ranking/` 与
  `GET /api/products/fund-risk-types/` 已就绪，但前端零调用方——能力已经上线，
  用户却看不到。

  ## 数据范围（2026-10-17 如实化）

  快照池 = **持仓 ∪ 自选**（`fund_risk_metrics_job` 默认目标池），不是全市场——
  本页回答的是「**你持有/关注的基金**在同类里风险收益比排第几」，即持仓风险体检。
  全市场同类榜是另一个形态（探市侧 + 净值回填扩容），已另立项，不在本页语义内。

  ## 这个页面在回答什么问题

  「同类里谁的风险收益比更好」——**限定在同一类内**。风险比跨类别不可比：
  债基年化波动 2%、股基 25%，而夏普把波动当风险 ⇒ 债基系统性偏高。所以本页
  **不提供「全市场榜」**，必须先选一个基金小类（后端 `fund_type_id` 也是必填）。

  ## 三条口径纪律（页面上必须让用户看得见）

  1. **类型选择器只列有榜的类**（`fund-risk-types/` 只交出有快照行的类型）——
     否则选中一个没算过的类会是空榜，用户分不清「这个类没有基金」与「我们没算」；
  2. **被剔除的条数必须显示**（`excluded_distorted`）——「榜上只有 3 只」与
     「同类只有 3 只有数据」是两回事，不显示就等于把后者说成前者；
  3. **不给「好/差」色**——榜单是同类内的相对排序，不是买入信号（合规红线：
     不荐股不跟单不预测）。数字与口径如实摆出，判断交给用户。
-->
<template>
  <div class="fund-ranking-page min-h-full">
    <PageHeaderBar
      title="同类风险榜"
      subtitle="对比范围：你持仓与自选的基金，在同一类内按风险收益指标排序——风险比跨类别不可比，故不做全市场榜"
    />

    <div class="ranking-shell">
      <PageSkeleton v-if="initialLoading" :cards="1" :table-rows="6" />

      <template v-else>
        <CardBlock>
          <SectionHeader
            title="筛选"
            info="榜单只在一个基金小类内排序；指标越小越好的（如波动率）会自动按升序排"
          />

          <div class="filter-row">
            <div class="filter-item">
              <label class="filter-item__label" for="fund-type">基金类型</label>
              <el-select
                id="fund-type"
                v-model="selectedTypeId"
                class="filter-item__control"
                placeholder="选择一个类型"
                filterable
                :loading="typesLoading"
                @change="onTypeChange"
              >
                <el-option
                  v-for="t in typeOptions"
                  :key="t.fund_type_id"
                  :value="t.fund_type_id"
                  :label="`${t.name}（${t.count}）`"
                />
              </el-select>
            </div>

            <div class="filter-item">
              <label class="filter-item__label">排序指标</label>
              <SegmentedControl
                v-model="metric"
                :options="metricOptions"
                aria-label="排序指标切换"
                @change="loadRanking"
              />
            </div>

            <div class="filter-item">
              <label class="filter-item__label">方向</label>
              <SegmentedControl
                v-model="order"
                :options="orderOptions"
                size="small"
                aria-label="排序方向切换"
                @change="loadRanking"
              />
            </div>
          </div>

          <!-- 诚实降级：没有可选类型时，说明的是「没人算过」而不是「没有基金」 -->
          <p v-if="!typeOptions.length" class="empty-hint">
            暂无风险指标快照。榜单需要先跑一次
            <code>pdm run sync --job fund_risk_metrics</code> 生成同类指标。
          </p>
        </CardBlock>

        <CardBlock v-if="selectedTypeId">
          <SectionHeader :title="rankingTitle" :info="rankingInfo" />

          <!-- 被剔除的条数：不显示的话「榜上只有 3 只」会被读成「同类只有 3 只有数据」 -->
          <div v-if="excludedDistorted > 0" class="excluded-bar">
            <IconifyIconOffline icon="ep:warning-filled" class="shrink-0" />
            <span>
              另有 {{ excludedDistorted }}
              只因口径可疑（净值跳变 /
              样本不足）被剔除，未进入本榜——它们算出来的值
              可能异常突出，但那是数据问题不是业绩。
            </span>
          </div>

          <div v-if="rankingLoading" class="table-loading">
            <el-skeleton :rows="5" animated />
          </div>

          <div v-else-if="!rows.length" class="empty-hint">
            {{ noRowHint }}
          </div>

          <div v-else class="overflow-x-auto">
            <table class="ranking-table w-full text-sm">
              <thead>
                <tr>
                  <th class="col-rank">#</th>
                  <th class="col-fund">基金</th>
                  <th
                    v-for="col in tableColumns"
                    :key="col.key"
                    :class="{ 'col-active': col.key === metric }"
                  >
                    <span class="th-with-tip">
                      <span>{{ col.label }}</span>
                      <el-tooltip :content="col.hint" placement="top">
                        <IconifyIconOffline
                          icon="ep:info-filled"
                          class="th-tip-icon"
                        />
                      </el-tooltip>
                    </span>
                  </th>
                  <th class="col-window">窗口</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in rows" :key="row.fund_code">
                  <td class="col-rank">{{ index + 1 }}</td>
                  <td class="col-fund">
                    <button
                      type="button"
                      class="fund-link"
                      :title="row.fund_name ? row.fund_code : undefined"
                      @click="goDetail(row.fund_code)"
                    >
                      <span class="fund-link__name">
                        {{ row.fund_name || row.fund_code }}
                      </span>
                      <!-- 名称与代码都显示：跳详情、复核数据都要代码；
                           funds 资料缺失时名称回退代码，此时不重复显示两遍 -->
                      <span v-if="row.fund_name" class="fund-link__code">{{
                        row.fund_code
                      }}</span>
                    </button>
                  </td>
                  <td
                    v-for="col in tableColumns"
                    :key="col.key"
                    :class="{ 'col-active': col.key === metric }"
                  >
                    {{ formatCell(row, col) }}
                  </td>
                  <td class="col-window">{{ row.window_label || "—" }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p class="footnote">
            指标口径：{{ rows[0]?.window_label || "—" }} · 样本数
            {{ sampleRange }} 个交易日 · 口径版本 {{ caliberVersion ?? "—" }}。
            榜单是同类内的相对排序，**不构成投资建议**。
          </p>
        </CardBlock>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  getFundRiskRanking,
  getFundRiskTypes,
  type FundRiskRankingRow,
  type FundRiskTypeOption
} from "@/api/products";

// 与路由 `router/modules/asset.ts` 的 name 一致，保证 keep-alive 命中
defineOptions({ name: "AssetFundRanking" });

const router = useRouter();

const DASH = "—";

/** 排序指标白名单 —— 与后端 `fund_risk_ranking.SORTABLE_METRICS` 逐项对齐。
 *  这里只放**用户读得懂且有意义**的 6 个；`annual_return` / `annual_volatility`
 *  等仍可传（后端支持），但不进分段控制器（选项 6 个是 SegmentedControl 的上限）。 */
const METRICS = [
  { label: "夏普", value: "sharpe" },
  { label: "卡玛", value: "calmar" },
  { label: "索提诺", value: "sortino" },
  { label: "UI", value: "ulcer_index" },
  { label: "波回比", value: "return_drawdown_ratio" },
  { label: "最大回撤", value: "max_drawdown" }
] as const;

const metricOptions = METRICS.map(m => ({ label: m.label, value: m.value }));
const orderOptions = [
  { label: "从优到劣", value: "desc" },
  { label: "从劣到优", value: "asc" }
] as const;

/** 表格列（固定一套，当前排序指标高亮——避免每次切指标换一套列，用户要重新找列）。
 *  hint：面向普通用户的指标解释（2026-10-17 表头 tooltip）——夏普/卡玛这类术语
 *  只摆数字不解释，多数用户读不懂「这个数高好还是低好」。 */
const tableColumns = [
  {
    key: "sharpe",
    label: "夏普",
    hint: "每承担 1 份年化波动，获得多少超出无风险利率的回报。大于 1 尚可、大于 2 较好；只在同类内可比"
  },
  {
    key: "calmar",
    label: "卡玛",
    hint: "年化收益 ÷ 最大回撤——赚的比最深一摔多多少。越高说明收益越抗跌"
  },
  {
    key: "ulcer_index",
    label: "UI(%)",
    hint: "溃疡指数：回撤的深度与持续时间合成的值。数字越大，持有过程越煎熬"
  },
  {
    key: "return_drawdown_ratio",
    label: "波回比",
    hint: "年化收益 ÷（波动率 × 最大回撤）——同时考虑日常颠簸与最深一摔"
  },
  {
    key: "max_drawdown",
    label: "最大回撤(%)",
    hint: "区间内从高点到低点最多亏多少。负值越浅越好"
  },
  {
    key: "annual_return",
    label: "年化收益(%)",
    hint: "区间收益折算成的年平均值"
  }
] as const;

const initialLoading = ref(true);
const typesLoading = ref(false);
const rankingLoading = ref(false);
const typeOptions = ref<FundRiskTypeOption[]>([]);
const selectedTypeId = ref<number | null>(null);
const metric = ref<string>("sharpe");
const order = ref<string>("desc");
const rows = ref<FundRiskRankingRow[]>([]);
const excludedDistorted = ref(0);
const caliberVersion = ref<number | null>(null);

const selectedTypeName = computed(
  () =>
    typeOptions.value.find(t => t.fund_type_id === selectedTypeId.value)
      ?.name ?? ""
);
const rankingTitle = computed(() =>
  selectedTypeName.value ? `${selectedTypeName.value} · 同类榜` : "同类榜"
);
const rankingInfo = computed(
  () =>
    `按「${METRICS.find(m => m.value === metric.value)?.label ?? metric.value}」排序`
);
const noRowHint = computed(() =>
  excludedDistorted.value > 0
    ? "该类型下所有基金的指标都因口径可疑被剔除——数据问题，不是没有基金。"
    : "该类型下暂时没有可上榜的数据。"
);
const sampleRange = computed(() => {
  if (!rows.value.length) return DASH;
  const values = rows.value.map(r => r.sample_points).filter(v => v != null);
  if (!values.length) return DASH;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return min === max ? `${min}` : `${min}~${max}`;
});

/** 数值格式化：null 一律降级「—」（诚实降级，不编造 0）。 */
function formatValue(v: number | null | undefined, digits = 2): string {
  return v == null ? DASH : v.toFixed(digits);
}

function formatCell(row: FundRiskRankingRow, col: { key: string }): string {
  return formatValue(row[col.key as keyof FundRiskRankingRow] as number | null);
}

async function loadTypes() {
  typesLoading.value = true;
  try {
    const res = await getFundRiskTypes();
    typeOptions.value = res?.data?.types ?? [];
    // 默认选中只数最多的那一类（typeOptions 已按 count 降序）
    if (typeOptions.value.length && selectedTypeId.value == null) {
      selectedTypeId.value = typeOptions.value[0].fund_type_id;
    }
  } catch {
    typeOptions.value = [];
  } finally {
    typesLoading.value = false;
  }
}

async function loadRanking() {
  if (selectedTypeId.value == null) return;
  rankingLoading.value = true;
  try {
    const res = await getFundRiskRanking({
      fund_type_id: selectedTypeId.value,
      metric: metric.value,
      order: order.value as "asc" | "desc"
    });
    const data = res?.data;
    rows.value = data?.rows ?? [];
    excludedDistorted.value = data?.excluded_distorted ?? 0;
    caliberVersion.value = data?.caliber_version ?? null;
  } catch {
    rows.value = [];
    excludedDistorted.value = 0;
  } finally {
    rankingLoading.value = false;
  }
}

function onTypeChange() {
  loadRanking();
}

function goDetail(code: string) {
  router.push(`/fund/${code}`);
}

onMounted(async () => {
  try {
    await loadTypes();
    await loadRanking();
  } finally {
    initialLoading.value = false;
  }
});
</script>

<style lang="scss" scoped>
.fund-ranking-page {
  background: var(--bg-page);
}

.ranking-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding-top: var(--space-4);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
  align-items: flex-end;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);

  &__label {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  &__control {
    min-width: 240px;
  }
}

.excluded-bar {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--bg-subtle, var(--bg-page));
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

.empty-hint {
  padding: var(--space-5) 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;

  code {
    padding: 0 4px;
    font-family: var(--font-mono, monospace);
    background: var(--bg-subtle, var(--bg-page));
    border-radius: var(--radius-xs);
  }
}

.ranking-table {
  border-collapse: collapse;

  th,
  td {
    padding: var(--space-3) var(--space-4);
    text-align: right;
    white-space: nowrap;
    border-bottom: 1px solid var(--border-subtle, var(--border-light));
  }

  th {
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-tertiary-ink);
  }

  td {
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
  }

  .col-rank,
  .col-fund,
  .col-window {
    text-align: left;
  }

  .col-rank {
    width: 48px;
    color: var(--text-tertiary-ink);
  }

  /* 当前排序指标高亮：让用户一眼看到「这个榜是按哪列排的」。
     刻意不用涨红跌绿——榜单是同类内的相对排序，不是买入信号。 */
  .col-active {
    font-weight: 600;
    color: var(--brand-700);
  }
}

/* 基金列：名称主显示、代码次要小字（只显 6 位代码用户认不出产品，2026-10-17）。
   整块可点击跳详情；名称缺失时回退代码，此时不重复显示。 */
.fund-link {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-start;
  max-width: 220px;
  overflow: hidden;
  text-align: left;
  cursor: pointer;
  background: none;
  border: none;

  &:hover .fund-link__name {
    color: var(--brand-700);
    text-decoration: underline;
  }

  &__name {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-label);
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__code {
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary-ink);
  }
}

/* 表头指标解释图标（el-tooltip 锚点）：跟随表头文字色，hover 才醒目 */
.th-with-tip {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.th-tip-icon {
  font-size: 13px;
  color: var(--text-tertiary-ink);
  cursor: help;
}

.table-loading {
  padding: var(--space-4) 0;
}

.footnote {
  margin-top: var(--space-4);
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}
</style>
