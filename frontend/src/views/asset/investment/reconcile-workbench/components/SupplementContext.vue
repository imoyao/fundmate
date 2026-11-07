<template>
  <!--
    补录弹窗第 ① 段「补的是哪一条」。
    单独成组件只为守住 `check_vue_size.mjs` 的 400 行门禁：
    SupplementDialog 放不进「上下文 + 两档表单 + 二次确认」全部内容。
  -->
  <section v-if="target" class="recon-supplement-context">
    <div class="recon-supplement-context__heading">
      <h3>{{ heading }}</h3>
      <span class="recon-supplement-context__issue">{{ issue }}</span>
    </div>
    <p v-if="isCash" class="recon-supplement-context__note">
      {{ CASH_SYMBOL_HINT }}
    </p>
    <dl class="recon-supplement-context__facts">
      <div>
        <dt>归属账本</dt>
        <dd>{{ ledgerName }}</dd>
      </div>
      <div>
        <dt>按流水算</dt>
        <dd>{{ reconQuantity(target.expected_value) }}</dd>
      </div>
      <div>
        <dt>账上记的</dt>
        <dd>{{ reconQuantity(target.actual_value) }}</dd>
      </div>
      <div>
        <dt>差多少</dt>
        <dd>{{ reconQuantity(target.diff) }}</dd>
      </div>
    </dl>
    <p class="recon-supplement-context__trail">
      这个产品的买卖记录在右侧抽屉「这个产品的投资轨迹」里，填之前先对照缺的那一笔。
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import type { DiscrepancyItem } from "@/api/reconciliation";
import { useReconLedger } from "../composables/useReconLedger";
import { reconAssetHeading, reconQuantity } from "../utils/reconDisplay";
import {
  CASH_SYMBOL_HINT,
  discrepancyIssue,
  specialSymbolLabel
} from "../utils/reconLabels";

defineOptions({ name: "SupplementContext" });

const props = defineProps<{
  target: DiscrepancyItem | null;
}>();

const { ensure, nameOf } = useReconLedger();
onMounted(() => {
  void ensure();
});

const heading = computed(() =>
  props.target
    ? reconAssetHeading(props.target.symbol, props.target.display_name)
    : ""
);
const issue = computed(() =>
  props.target ? discrepancyIssue(props.target.discrepancy_type) : ""
);
const isCash = computed(
  () => specialSymbolLabel(props.target?.symbol) !== null
);
const ledgerName = computed(() => nameOf(props.target?.ledger_id));
</script>

<style scoped>
.recon-supplement-context {
  padding: var(--space-compact);
  margin-bottom: var(--space-standard);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.recon-supplement-context__heading {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
}

.recon-supplement-context__heading h3 {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.recon-supplement-context__issue {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--brand-ink);
  background: var(--brand-100);
  border-radius: var(--radius-pill);
}

.recon-supplement-context__note {
  margin: 8px 0 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.recon-supplement-context__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
  gap: var(--space-2);
  margin: 12px 0 0;
}

.recon-supplement-context__facts div {
  min-width: 0;
  padding: 8px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.recon-supplement-context__facts dt {
  margin-bottom: 4px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.recon-supplement-context__facts dd {
  margin: 0;
  font-size: var(--text-small);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.recon-supplement-context__trail {
  margin: 12px 0 0;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}
</style>
