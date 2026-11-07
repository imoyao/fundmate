<template>
  <!--
    抽屉第 ① 段「来龙去脉」。
    用户点开一条待办时，第一屏必须能回答：改的是哪个产品、在哪本账、
    哪里对不上、差多少、现在要我做什么。旧补充弹窗只有一张表单，
    这些一个字都没有（owner 第二轮截图 2）。
  -->
  <section v-if="target" class="recon-context">
    <div class="recon-context__head">
      <h3 class="recon-context__title">{{ heading }}</h3>
      <span class="recon-context__issue">{{ target.issue }}</span>
    </div>

    <p class="recon-context__lead">{{ item?.summary }}</p>

    <dl class="recon-context__grid">
      <div class="recon-context__cell">
        <dt>归属账本</dt>
        <dd>{{ ledgerName }}</dd>
      </div>
      <div v-if="hasNumbers" class="recon-context__cell">
        <dt>按流水算</dt>
        <dd>{{ reconQuantity(target.expected) }}</dd>
      </div>
      <div v-if="hasNumbers" class="recon-context__cell">
        <dt>账上记的</dt>
        <dd>{{ reconQuantity(target.actual) }}</dd>
      </div>
      <div v-if="hasNumbers" class="recon-context__cell">
        <dt>差多少</dt>
        <dd :class="{ 'is-diff': target.diff !== 0 }">
          {{ reconQuantity(target.diff) }}
        </dd>
      </div>
      <div v-if="whenLabel" class="recon-context__cell">
        <dt>发现时间</dt>
        <dd>{{ whenLabel }}</dd>
      </div>
    </dl>

    <p v-if="target.ledgerId === null" class="recon-context__warn">
      这条记录还没归到任何账本，账本详情页里看不到它。先归置账本，再回来核对。
    </p>
    <p v-if="item?.actionLabel" class="recon-context__next">
      接下来：{{ item.actionLabel }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { formatDate } from "@/utils/date";
import { useReconLedger } from "../composables/useReconLedger";
import { discrepancyIssue } from "../utils/reconLabels";
import { reconAssetHeading, reconQuantity } from "../utils/reconDisplay";
import type { ReconQueueItem } from "../utils/reconQueue";

defineOptions({ name: "ReconContextPanel" });

const props = defineProps<{
  item: ReconQueueItem | null;
}>();

const { ensure, nameOf } = useReconLedger();
onMounted(() => {
  void ensure();
});

interface ContextTarget {
  symbol: string;
  name: string | null;
  ledgerId: number | null;
  issue: string;
  expected: number | null;
  actual: number | null;
  diff: number | null;
  when: string | null;
}

/** 队列项只带展示字段 + 原始对象引用；这里按 kind 取回可对照的原始数值 */
const target = computed<ContextTarget | null>(() => {
  const item = props.item;
  if (!item) return null;
  const payload = item.payload;

  if (payload.kind === "discrepancy") {
    const row = payload.row;
    return {
      symbol: row.symbol,
      name: row.display_name ?? null,
      ledgerId: row.ledger_id,
      issue: discrepancyIssue(row.discrepancy_type),
      expected: row.expected_value,
      actual: row.actual_value,
      diff: row.diff,
      when: row.first_detected_at
    };
  }
  if (payload.kind === "tax") {
    const row = payload.row;
    return {
      symbol: row.symbol,
      name: row.name || null,
      ledgerId: null,
      issue: "现金分红还没记扣税",
      expected: null,
      actual: null,
      diff: null,
      when: row.dividend_on
    };
  }
  return {
    symbol: item.title,
    name: null,
    ledgerId: null,
    issue: item.sourceLabel,
    expected: null,
    actual: null,
    diff: null,
    when: null
  };
});

const heading = computed(() =>
  target.value ? reconAssetHeading(target.value.symbol, target.value.name) : ""
);
const ledgerName = computed(() => nameOf(target.value?.ledgerId ?? null));
const hasNumbers = computed(
  () =>
    target.value?.expected !== null &&
    target.value?.expected !== undefined &&
    target.value?.actual !== null &&
    target.value?.actual !== undefined
);
const whenLabel = computed(() => {
  const raw = target.value?.when;
  if (!raw) return "";
  const value = formatDate(raw);
  return value === "--" ? "" : value;
});
</script>

<style scoped>
.recon-context {
  padding: var(--space-standard);
  margin-bottom: var(--space-standard);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.recon-context__head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
}

.recon-context__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.recon-context__issue {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--brand-ink);
  background: var(--brand-100);
  border-radius: var(--radius-pill);
}

.recon-context__lead {
  margin: 8px 0 12px;
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
}

.recon-context__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-2);
  margin: 0;
}

.recon-context__cell {
  min-width: 0;
  padding: 8px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.recon-context__cell dt {
  margin-bottom: 4px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.recon-context__cell dd {
  margin: 0;
  font-size: var(--text-small);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.recon-context__cell dd.is-diff {
  color: var(--color-danger);
}

.recon-context__warn {
  margin: 12px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
}

.recon-context__next {
  margin: 12px 0 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}
</style>
