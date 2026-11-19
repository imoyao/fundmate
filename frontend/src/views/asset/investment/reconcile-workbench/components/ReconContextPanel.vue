<template>
  <!--
    抽屉第 ① 段「来龙去脉」。
    信息归属（owner 截图去重，2026-11-12）：产品标识由抽屉头部说一次
    （reconAssetHeading，唯一契约），本卡只留它独有的东西——差异类型胶囊、
    数字格（账本 / 按流水算 / 账上记的 / 差多少 / 发现时间）、未归账本警告、
    接下来；差异类待办的「需要你对照…」判断句由头部副标题承载，卡内不再复述。
  -->
  <section v-if="target" class="recon-context">
    <div class="recon-context__head">
      <span class="recon-context__issue">{{ target.issue }}</span>
    </div>

    <p v-if="showLead" class="recon-context__lead">{{ item?.summary }}</p>

    <dl class="recon-context__grid">
      <div class="recon-context__cell">
        <dt>归属账本</dt>
        <dd>{{ ledgerName }}</dd>
      </div>
      <div v-if="hasNumbers" class="recon-context__cell">
        <dt>{{ DISC_COLUMN_LABELS.expected }}</dt>
        <dd>{{ reconQuantity(target.expected) }}</dd>
      </div>
      <div v-if="hasNumbers" class="recon-context__cell">
        <dt>{{ DISC_COLUMN_LABELS.actual }}</dt>
        <dd>{{ reconQuantity(target.actual) }}</dd>
      </div>
      <div v-if="hasNumbers" class="recon-context__cell">
        <dt>{{ DISC_COLUMN_LABELS.diff }}</dt>
        <dd :class="{ 'is-diff': target.diff !== 0 }">
          {{ reconQuantity(target.diff) }}
        </dd>
      </div>
      <div v-if="whenLabel" class="recon-context__cell">
        <dt>发现时间</dt>
        <dd>{{ whenLabel }}</dd>
      </div>
    </dl>

    <p v-if="showLedgerWarn" class="recon-context__warn">
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
import { discrepancyIssue, DISC_COLUMN_LABELS } from "../utils/reconLabels";
import { reconQuantity } from "../utils/reconDisplay";
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
  ledgerId: number | null;
  /** 后端已给出账本名、但没给 id 的场合（E账户归因结果 `attributed_to`）：直接用，不再查表 */
  ledgerName?: string | null;
  issue: string;
  expected: number | null;
  actual: number | null;
  diff: number | null;
  when: string | null;
}

/** 队列项只带展示字段 + 原始对象引用；这里按 kind 取回可对照的原始数值。
 *  关键修复：dangling 组本身带有 ledger_id（交易实际所在的账本），曾经在 else 分支
 *  被写死成 null，导致「来龙去脉」显示「未归账本」而「投资轨迹」却显示该账本名，
 *  两处矛盾（owner 第三轮截图 1）。这里按 kind 取真实 ledger_id，与轨迹保持一致。 */
const target = computed<ContextTarget | null>(() => {
  const item = props.item;
  if (!item) return null;
  const payload = item.payload;

  if (payload.kind === "discrepancy") {
    const row = payload.row;
    return {
      ledgerId: row.ledger_id ?? null,
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
      ledgerId: null,
      issue: "现金分红还没记扣税",
      expected: null,
      actual: null,
      diff: null,
      when: row.dividend_on
    };
  }
  if (payload.kind === "danglingStage") {
    const row = payload.groups[0];
    return {
      // 多组聚合没有单一账本可指认；单组执行区取该组的真实账本
      ledgerId: row?.ledger_id ?? null,
      issue: item.sourceLabel,
      expected: null,
      actual: null,
      diff: null,
      when: null
    };
  }
  if (payload.kind === "ghost" || payload.kind === "ghostIgnored") {
    return {
      // 无单一账本，账本名交给轨迹展示
      ledgerId: null,
      issue: item.sourceLabel,
      expected: null,
      actual: null,
      diff: null,
      when: null
    };
  }
  if (payload.kind === "eaccount") {
    const row = payload.row;
    return {
      // 影子记录的 ledger_id 按设计就是 NULL（它不落在任何账本里），真正有账本的是
      // 归因结果 attributed_to（后端只给名称、不给 id）。曾经与 import 一起被写死成
      // null，于是 93 条影子记录（85 条 attributed + 8 条 verified）全部显示「未归账本」，
      // 还要被建议「先归置账本，再回来核对」——对已核对项是彻底的错误引导。
      ledgerId: null,
      ledgerName: row.attributed_to,
      issue: item.sourceLabel,
      expected: null,
      actual: null,
      diff: null,
      when: null
    };
  }
  // import：入口动作，没有单条记录的账本可指认
  return {
    ledgerId: null,
    issue: item.sourceLabel,
    expected: null,
    actual: null,
    diff: null,
    when: null
  };
});

/** 差异类待办：issue 胶囊已说「哪里对不上」，判断句由头部副标题承载——
 *  卡内 lead 只会第三遍复述，不再渲染（design.md「对账抽屉信息层级」）。 */
const showLead = computed(() => props.item?.payload.kind !== "discrepancy");
const ledgerName = computed(
  () => target.value?.ledgerName || nameOf(target.value?.ledgerId ?? null)
);
/** 「先归置账本」是**未处理项**的下一步；已处理项（含 E账户 verified：份额差 ≤0.001，
 *  本来就不需要归置）不该再收到这条指令，否则同一张卡上「已经核对过了」与「先去归置」
 *  自相矛盾（owner 2026-11-15 截图）。 */
const showLedgerWarn = computed(
  () =>
    !!target.value &&
    target.value.ledgerId === null &&
    !target.value.ledgerName &&
    props.item?.state !== "done"
);
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
