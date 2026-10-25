<template>
  <div class="penetration-panel">
    <SectionHeader
      title="持仓穿透"
      :info="
        '你的钱最终压在哪些行业与个股上（' +
        (data?.scheme_label ?? '') +
        '口径' +
        scopeSuffix +
        '）。穿透仅覆盖持仓，不含房产/现金等通用资产。'
      "
    >
      <template #action>
        <SegmentedControl
          v-model="scheme"
          :options="SCHEME_OPTIONS"
          size="small"
          aria-label="穿透口径"
          @change="load"
        />
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
      <!-- 行业分布：横向条，不用饼图（行业数多，饼图读不出量级差）。
           #2617：两档口径必须分开看——「直接持有」基金整块不拆底层，
           「穿透后」基金与直持合并。合并成一张图会得出「基金是制造业」的假结论。 -->
      <CardBlock class="mt-4">
        <div class="panel-head">
          <h4 class="panel-subtitle">行业分布</h4>
          <SegmentedControl
            v-model="industryView"
            :options="VIEW_OPTIONS"
            size="small"
            aria-label="行业口径"
          />
        </div>
        <p class="panel-view-hint">{{ viewHint }}</p>
        <!-- #2617 诚实降级：主口径没有「个股→行业」映射时直持图必然为空，
             把后端给的成因原样透出，避免用户把空图读成计算缺陷 -->
        <el-alert
          v-if="directMappingHint"
          class="mb-2"
          type="info"
          :closable="false"
          :title="directMappingHint"
        />
        <p
          v-if="!activeIndustryRows.length"
          class="text-sm"
          :style="{ color: 'var(--text-secondary)' }"
        >
          暂无可用的行业配置数据。
        </p>
        <PenetrationBarList v-else :rows="activeIndustryRows" />
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
        <PenetrationBarList v-if="data.stocks.length" :rows="stockRows" />
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
        <!-- #2617：直持腿在该体系下的分布（后端 #1981 早已返回、此前未展示）。
             主口径无直持映射时，这里就是用户唯一能看到「直持压在哪些行业」的地方。 -->
        <div v-if="info.direct_industries.length" class="other-direct">
          <p class="other-direct__title">
            直持行业（本体系有「个股→行业」映射）
          </p>
          <div class="other-direct__tags">
            <span
              v-for="row in info.direct_industries"
              :key="row.code"
              class="other-direct__tag"
            >
              {{ row.name }}
              <em>{{ percent(row.ratio_of_total) }}</em>
            </span>
          </div>
        </div>
      </CardBlock>

      <!-- 口径说明：后端写死的 notes，原样展示（前端不改写、不隐藏）。
           2026-10-25 由独立 CardBlock 降为区块尾注：口径是元信息不是内容，
           单独成卡会与「行业分布 / 个股层 / 未穿透」抢同一层视觉层级，
           还把正文往下顶；降权小字 + 无卡片壳，可见性不变。 -->
      <div class="penetration-footnote mt-4">
        <span class="penetration-footnote__label">口径说明</span>
        <ul class="notes-list">
          <li v-for="(note, i) in data.notes" :key="i">
            {{ note }}
          </li>
        </ul>
        <p class="penetration-footnote__meta">数据日期 {{ data.as_of }}</p>
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
import PenetrationBarList from "./PenetrationBarList.vue";
import { getPenetration, type PenetrationData } from "@/api/summary";
import { formatAmount } from "@/utils/currency";

/**
 * 持仓穿透面板（#870 B2；#2595 三级口径化）。
 *
 * 从 `views/asset/portfolio/` 上移到共享组件：穿透是三级口径（家庭 / 账户 /
 * 组合）都能消费的面板，而非组合详情页私产。原实现在组合详情页**不传 scope**，
 * 实际展示的是家庭级数据（口径错位，#2595 修复）——现在由父页显式传：
 *
 * - 不传 props：家庭级（既有行为，向后兼容）；
 * - `portfolio-id`：组合级（组合详情页应传这个）；
 * - `ledger-id`：账户级；两者互斥（后端 400），父页自行保证。
 */
const props = defineProps<{
  /** 账户级口径；与 portfolioId 互斥 */
  ledgerId?: number;
  /** 组合级口径；与 ledgerId 互斥 */
  portfolioId?: number;
}>();

/** 穿透口径档位（#2339：字符串维度的「多选一」，走 SegmentedControl 而非实底 radio） */
const SCHEME_OPTIONS = [
  { label: "证监会门类", value: "csrc" },
  { label: "GICS", value: "gics" }
] as const;

const scheme = ref<"csrc" | "gics">("csrc");

/** #2617 行业口径两档：直接持有（基金整块）/ 穿透后（基金并入行业）。
 *  默认穿透后 = 既有行为，不改变旧用户的阅读习惯。 */
const VIEW_OPTIONS = [
  { label: "直接持有", value: "direct" },
  { label: "穿透后", value: "penetrated" }
] as const;

const industryView = ref<"direct" | "penetrated">("penetrated");
const data = ref<PenetrationData | null>(null);
const loading = ref(false);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const scope: { ledger_id?: number; portfolio_id?: number } = {};
    if (props.ledgerId != null) scope.ledger_id = props.ledgerId;
    if (props.portfolioId != null) scope.portfolio_id = props.portfolioId;
    const res = await getPenetration(scheme.value, scope);
    data.value = res?.data ?? null;
    if (!data.value) error.value = "穿透数据为空。";
  } catch {
    data.value = null;
    error.value = "穿透数据加载失败。";
  } finally {
    loading.value = false;
  }
}

watch(() => [props.ledgerId, props.portfolioId], load);

/** 口径后缀：家庭级不缀词，账户 / 组合级明示作用域（与出参 scope 字段同源） */
const scopeSuffix = computed(() => {
  const s = data.value?.scope;
  if (s === "ledger") return "·账户级";
  if (s === "portfolio") return "·组合级";
  return "";
});

/** 比率一律按后端给的 0~1 值格式化；分母口径由后端决定，前端不重算 */
function percent(ratio: number) {
  return `${((ratio ?? 0) * 100).toFixed(1)}%`;
}

/** 条形宽度：以「已穿透比例」为分母（行业行），否则条形会随口径跳变 */
function barWidth(ratio: number) {
  const r = Math.max(0, Math.min(1, ratio ?? 0));
  return `${(r * 100).toFixed(2)}%`;
}

/** 行业行：条形以「已穿透」为分母，右侧数值仍按总市值占比（两个分母不同，别混） */
const industryRows = computed(() =>
  (data.value?.industries ?? []).map(row => ({
    key: row.code,
    name: row.name,
    title: `${row.name}（${row.code}）· ${row.fund_count} 只基金持有`,
    width: barWidth(row.ratio_of_penetrated),
    value: percent(row.ratio_of_total)
  }))
);

/**
 * #2617 直接持有口径：直持行业 + 基金整块 + 未映射直持。
 * 三项合计 = 持仓总市值；比率与金额都由后端算好（含 `fund_ratio` / `unmapped_ratio`），
 * 前端不做除法——否则与「穿透后」图的口径会各算各的。
 */
const directRows = computed(() => {
  const dv = data.value?.direct_view;
  if (!dv) return [];
  const rows = dv.industries.map(row => ({
    key: row.code,
    name: row.name,
    title: `直持 ${row.name}（${row.code}）`,
    width: barWidth(row.ratio_of_total),
    value: percent(row.ratio_of_total)
  }));
  if (dv.fund_cny > 0) {
    rows.push({
      key: "__fund__",
      name: "基金（未拆底层）",
      title: "基金整块市值；其底层行业敞口见「穿透后」口径",
      width: barWidth(dv.fund_ratio),
      value: percent(dv.fund_ratio)
    });
  }
  if (dv.unmapped_cny > 0) {
    rows.push({
      key: "__unmapped__",
      name: "未映射直持",
      title: "没有行业映射的直持证券（不凭空补 0 值行业）",
      width: barWidth(dv.unmapped_ratio),
      value: percent(dv.unmapped_ratio)
    });
  }
  // 现金等价物单列：与「未映射」不是一回事（无股票敞口 ≠ 数据缺口）
  if (dv.cash_equivalent_cny > 0) {
    rows.push({
      key: "__cash__",
      name: "现金等价物",
      title: "货基/逆回购，本质无股票敞口（非缺口）",
      width: barWidth(dv.cash_equivalent_ratio),
      value: percent(dv.cash_equivalent_ratio)
    });
  }
  return rows;
});

/** 直持视图缺映射时的成因提示；无缺口或不在直持视图时为空 */
const directMappingHint = computed(() => {
  const dv = data.value?.direct_view;
  if (!dv || industryView.value !== "direct") return "";
  if (dv.mapping_available) return "";
  return dv.unmapped_reason ?? "";
});

const activeIndustryRows = computed(() =>
  industryView.value === "direct" ? directRows.value : industryRows.value
);

const viewHint = computed(() =>
  industryView.value === "direct"
    ? "直接持有：基金整块显示为「基金」不拆底层——这张图回答「我自己直接买了什么」。"
    : "穿透后：基金按底层持仓并入行业——这张图回答「我的钱最终押在哪些行业」。"
);

/** 个股行：季报只披露前十大、故用第二色与行业层区分；条形与数值同用总市值占比 */
const stockRows = computed(() =>
  (data.value?.stocks ?? []).map(row => ({
    key: row.code,
    name: row.name,
    title: row.holder_fund_count
      ? `${row.holder_fund_count} 只基金持有`
      : "其余个股合计",
    width: barWidth(row.ratio_of_total),
    value: percent(row.ratio_of_total),
    alt: true
  }))
);

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

/* #2617 行业口径切换：标题与分段控件同一行，提示语单独一行降权 */
.panel-head {
  display: flex;
  gap: var(--space-standard);
  align-items: center;
  justify-content: space-between;
}

.panel-view-hint {
  margin: 0 0 var(--space-compact);
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* #2617 非主口径里的直持行业：标签流，不画条——它只是「另一块敞口」，
   不是可与主口径比较的量级，画条会被误读成两套并列分类 */
.other-direct {
  margin-top: var(--space-compact);
}

.other-direct__title {
  margin: 0 0 var(--space-1);
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.other-direct__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.other-direct__tag {
  display: inline-flex;
  gap: var(--space-1);
  align-items: baseline;
  padding: 2px var(--space-2);
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);

  em {
    font-style: normal;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }
}

.panel-subtitle-note {
  margin-left: var(--space-compact);
  font-size: var(--text-small);
  font-weight: 400;
  color: var(--text-tertiary);
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

/* 口径说明尾注：与产品详情页「口径脚注」同款降权——小字 + 次级墨色，
   不再用卡片壳与 h4（否则与内容区块同级，元信息抢内容的层级）。 */
.penetration-footnote {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  color: var(--text-tertiary);
}

.penetration-footnote__label {
  font-size: var(--text-label);
  font-weight: 600;
}

.penetration-footnote__meta {
  margin: 0;
  font-size: var(--text-label);
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
