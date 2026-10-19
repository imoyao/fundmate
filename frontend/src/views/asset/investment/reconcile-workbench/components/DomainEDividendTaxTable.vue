<template>
  <div class="domain-e-body">
    <el-empty
      v-if="!loading && items.length === 0"
      description="没有待补记的分红扣税"
      :image-size="80"
    />
    <div v-else v-loading="loading" class="tax-list">
      <!-- 口径说明：用户最容易误读的是「为什么系统不直接替我算」。
           这句话必须出现在列表之前，而不是藏在文档里。 -->
      <p class="tax-note">
        A
        股红利税按<strong>实际持股期</strong>在卖出时补扣，税率取决于买入批次，
        本系统只有聚合持仓，因此不自动推算。下列为「某笔现金分红没有配上扣税流水」
        （该补记）与「扣税金额超过红利税上限
        20%」（该核对）两类——都只需看一眼交割单。
      </p>

      <article
        v-for="it in items"
        :key="`${it.symbol}-${it.dividend_on}`"
        class="tax-item"
      >
        <header class="tax-item__head">
          <span class="tax-item__symbol">{{ it.symbol }}</span>
          <span class="tax-item__name">{{ it.name || "—" }}</span>
          <el-tag
            size="small"
            :type="it.status === '未扣' ? 'warning' : 'danger'"
            effect="light"
          >
            {{ it.status }}
          </el-tag>
        </header>
        <p class="tax-item__meta">
          {{ formatDate(it.dividend_on) }} 分红
          <span class="tax-item__amount">{{ yuan(it.dividend_cents) }} 元</span>
          <template v-if="it.tax_cents > 0">
            · 已记税 {{ yuan(it.tax_cents) }} 元（{{ it.ratio_pct }}%）
          </template>
          <template v-if="it.account_name"> · {{ it.account_name }}</template>
        </p>
        <div class="tax-item__actions">
          <el-button
            v-if="it.status === '未扣'"
            size="small"
            type="primary"
            plain
            :loading="recordingSymbol === it.symbol"
            @click="askRecord(it)"
          >
            补记这笔税
          </el-button>
          <span v-else class="tax-item__hint">
            红利税不会超过 20%，这笔更像别的品种的费用，请核对是否记错品种。
          </span>
        </div>
      </article>

      <p v-if="totalCents > 0" class="tax-total">
        合计 {{ pendingCount }} 笔待补记，分红
        {{ yuan(totalCents) }} 元（均为税前）
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { formatDate } from "@/utils/date";
import { recordDividendTax } from "@/api/reconciliation";
import type { DividendTaxPendingItem } from "@/api/reconciliation";

/**
 * 域 E：红利税待办（#541）。
 *
 * WHY 不复用 `DomainBDiscTable`：域 B 的行是「应然 vs 实然，算出差额」——
 * 本域**没有应然值可算**（我们不推算税率），硬套会造出一列假的「应有税额」，
 * 那正是这次刻意不做的事。所以这里只陈述账内已有事实（哪天分了多少、配到多少税），
 * 把「该扣多少」留给用户从交割单读回来。
 *
 * WHY 有「补记」按钮：提醒只写消息的版本实测过——用户看到了，但要为此打开记账表单
 * 填六个字段，于是没人真去记。**没被做的提醒等于没提醒。** 不给默认税额（那是猜），
 * 只给一个入口，让用户把交割单上那笔数字抄进来。
 */
const props = defineProps<{
  items: DividendTaxPendingItem[];
  totalCents: number;
  pendingCount: number;
  loading: boolean;
}>();

const emit = defineEmits<{ recorded: [] }>();

const recordingSymbol = ref<string | null>(null);

/** 分 → 元（保留两位）。后端金额一律整数分，前端不做二次运算以外的加工。 */
function yuan(cents: number): string {
  return (cents / 100).toFixed(2);
}

/** 弹框问税额与扣税日，然后 POST 补记。
 *
 * **刻意不给默认金额**：推算出来的税额是猜的（见后端模块 docstring），
 * 给默认值等于诱导用户把猜数抄进账本。这里只留一个空输入等他去交割单抄。 */
async function askRecord(item: DividendTaxPendingItem): Promise<void> {
  const label = item.name || item.symbol;
  let raw: string;
  try {
    const result = await ElMessageBox.prompt(
      `请对照券商交割单，填写 ${label} ${formatDate(item.dividend_on)} 这笔分红的实际扣税额（元）。`,
      "补记红利税",
      {
        inputPlaceholder: `例如 ${((item.dividend_cents * 0.1) / 100).toFixed(2)}`,
        inputPattern: /^\d+(\.\d{1,2})?$/,
        inputErrorMessage: "请填写正数金额，最多两位小数",
        confirmButtonText: "记一笔",
        cancelButtonText: "取消"
      }
    );
    raw = result.value;
  } catch {
    return; // 用户取消（ElMessageBox 以 reject 表示取消，不是错误）
  }
  const amount = Number(raw);
  if (!Number.isFinite(amount) || amount <= 0) {
    ElMessage.error("税额必须大于 0");
    return;
  }
  recordingSymbol.value = item.symbol;
  try {
    await recordDividendTax({
      symbol: item.symbol,
      amount,
      tax_on: item.dividend_on ?? undefined,
      account_name: item.account_name || undefined
    });
    ElMessage.success("已补记，正在刷新列表");
    emit("recorded");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err.response?.data?.message || "补记失败");
  } finally {
    recordingSymbol.value = null;
  }
}

// props 中有 totalCents 供模板直接用；保持解构默认值以免 eslint 报未使用
void props;
</script>

<style scoped>
.domain-e-body {
  padding: 4px 0;
}

.tax-note {
  padding: 10px 12px;
  margin: 0 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.tax-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.tax-item:last-of-type {
  border-bottom: none;
}

.tax-item__head {
  display: flex;
  gap: 8px;
  align-items: center;
}

.tax-item__symbol {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.tax-item__name {
  color: var(--el-text-color-regular);
}

.tax-item__meta {
  margin: 6px 0 0;
  font-size: var(--text-label);
  color: var(--el-text-color-regular);
}

.tax-item__amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--el-color-warning);
}

.tax-item__actions {
  margin-top: 8px;
}

.tax-item__hint {
  font-size: var(--text-label);
  color: var(--el-text-color-secondary);
}

.tax-total {
  margin: 12px 0 0;
  font-size: var(--text-label);
  color: var(--el-text-color-secondary);
}
</style>
