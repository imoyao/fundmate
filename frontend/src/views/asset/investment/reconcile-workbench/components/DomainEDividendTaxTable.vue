<template>
  <div class="domain-e-body">
    <el-empty
      v-if="!loading && items.length === 0"
      description="没有待补记的分红扣税"
      :image-size="80"
    />
    <div v-else v-loading="loading" class="tax-list">
      <!-- 口径说明：用户最容易误读的是「为什么系统不直接替我算」。
           这句话必须出现在列表之前，不能藏在文档里；语气按 design.md 禁「请」。 -->
      <p class="tax-note">
        A
        股红利税按<strong>实际持股期</strong>在卖出时补扣，税率取决于买入批次，
        系统只有聚合持仓，不推算税额。下面分两类：现金分红没有配上扣税流水（该补记），
        以及扣税金额超过红利税上限 20%（该核对）。两类都只需对照交割单看一眼。
      </p>

      <article
        v-for="it in items"
        :key="`${it.symbol}-${it.dividend_on}`"
        class="tax-item"
      >
        <header class="tax-item__head">
          <span class="tax-item__symbol">{{ it.name || it.symbol }}</span>
          <span class="tax-item__code">{{ it.symbol }}</span>
          <span
            class="tax-item__state"
            :class="it.status === '未扣' ? 'is-pending' : 'is-abnormal'"
          >
            {{ it.status === "未扣" ? "待补记" : "金额待核对" }}
          </span>
        </header>
        <p class="tax-item__meta">
          {{ formatDate(it.dividend_on) }} 分红
          <span class="tax-item__amount">{{ money(it.dividend_cents) }}</span>
          <template v-if="it.tax_cents > 0">
            · 已记税 {{ money(it.tax_cents) }}（{{ it.ratio_pct }}%）
          </template>
          <template v-if="it.account_name"> · {{ it.account_name }}</template>
        </p>
        <div class="tax-item__actions">
          <el-button
            v-if="it.status === '未扣'"
            size="small"
            type="primary"
            plain
            @click="openDialog(it)"
          >
            补记这笔税
          </el-button>
          <span v-else class="tax-item__hint">
            红利税不会超过税前分红的
            20%，这笔更像别的品种的费用，对照交割单核对是否记错品种。
          </span>
        </div>
      </article>

      <p v-if="totalCents > 0" class="tax-total">
        合计 {{ pendingCount }} 笔待补记，税前分红 {{ money(totalCents) }}
      </p>
    </div>

    <!-- 正式补记弹窗：上下文、校验、后果说明都在弹窗内，不再用单输入框 prompt -->
    <RecordTaxDialog
      v-model="dialogVisible"
      :item="activeItem"
      @recorded="emit('recorded')"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { formatDate } from "@/utils/date";
import { centsToYuan } from "@/utils/currency";
import type { DividendTaxPendingItem } from "@/api/reconciliation";
import { reconMoney } from "../utils/reconDisplay";
import RecordTaxDialog from "./RecordTaxDialog.vue";

/**
 * 域 E：分红未记扣税（#541）。
 *
 * WHY 不复用 `DomainBDiscTable`：域 B 的行是「应然 vs 实然，算出差额」——
 * 本域没有应然值可算（不推算税率），硬套会造出一列假的「应有税额」。
 * 这里只陈述账内已有事实，把「该扣多少」留给用户从交割单读回来。
 */
defineProps<{
  items: DividendTaxPendingItem[];
  totalCents: number;
  pendingCount: number;
  loading: boolean;
}>();

const emit = defineEmits<{ recorded: [] }>();

const dialogVisible = ref(false);
const activeItem = ref<DividendTaxPendingItem | null>(null);

function openDialog(item: DividendTaxPendingItem): void {
  activeItem.value = item;
  dialogVisible.value = true;
}

/** 后端金额一律整数分；换算只走 centsToYuan，不再各处散写 /100 */
function money(cents: number): string {
  return reconMoney(centsToYuan(cents));
}
</script>

<style scoped>
.domain-e-body {
  padding: 4px 0;
}

.tax-note {
  padding: 10px 12px;
  margin: 0 0 12px;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.tax-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-light);
}

.tax-item:last-of-type {
  border-bottom: none;
}

.tax-item__head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.tax-item__symbol {
  font-weight: 600;
  color: var(--text-primary);
}

.tax-item__code {
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.tax-item__state {
  padding: 2px 8px;
  font-size: var(--text-label);
  border-radius: var(--radius-pill);
}

.tax-item__state.is-pending {
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
}

.tax-item__state.is-abnormal {
  color: var(--color-danger-ink);
  background: var(--color-danger-10);
}

.tax-item__meta {
  margin: 6px 0 0;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}

.tax-item__amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.tax-item__actions {
  margin-top: 8px;
}

.tax-item__hint {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.tax-total {
  margin: 12px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
