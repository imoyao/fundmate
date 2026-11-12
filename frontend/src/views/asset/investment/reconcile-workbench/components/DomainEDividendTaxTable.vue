<template>
  <div class="domain-e-body">
    <el-empty
      v-if="!loading && items.length === 0 && !deferredNote"
      description="没有需要核对的扣税项"
      :image-size="80"
    />
    <div v-else v-loading="loading" class="tax-list">
      <!-- 口径说明：用户最容易误读的是「为什么派息时账上没有税」。
           这句话必须出现在列表之前，不能藏在文档里；语气按 design.md 禁「请」。 -->
      <p class="tax-note">
        A
        股红利税按<strong>实际持股期</strong>在<strong>卖出时</strong>结算：持股超
        1 年免税，1 个月到 1 年 10%，1 个月以内
        20%。派息时一律暂不扣缴，所以「持有中、
        账上没有扣税」是正常状态。下面只列真正要你确认的两种情况：卖出后没配上扣税流水
        （对照交割单看一眼），以及扣税金额超过分红 20%（核对是否记错了品种）。
      </p>

      <article
        v-for="it in items"
        :key="`${it.symbol}-${it.dividend_on}`"
        class="tax-item"
      >
        <header class="tax-item__head">
          <span class="tax-item__symbol">{{
            reconGroupTitle(it.symbol, it.name)
          }}</span>
          <span class="tax-item__code">{{ reconSymbolCode(it.symbol) }}</span>
          <span
            class="tax-item__state"
            :class="it.status === '待核对' ? 'is-pending' : 'is-abnormal'"
          >
            {{ it.status === "待核对" ? "待核对" : "金额待核对" }}
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
          <template v-if="it.status === '待核对'">
            <el-button
              size="small"
              type="primary"
              plain
              @click="openDialog(it)"
            >
              补记这笔税
            </el-button>
            <el-button
              size="small"
              text
              :loading="ackingKey === `${it.symbol}-${it.dividend_on}`"
              @click="ackItem(it)"
            >
              确认无需记账
            </el-button>
          </template>
          <span v-else class="tax-item__hint">
            红利税不会超过税前分红的
            20%，这笔更像别的品种的费用，对照交割单核对是否记错品种。
          </span>
        </div>
      </article>

      <p v-if="totalCents > 0" class="tax-total">
        合计 {{ pendingCount }} 笔待核对，税前分红 {{ money(totalCents) }}
      </p>

      <!-- 折叠说明而非静默隐藏：让用户看到「系统认过了，只是按制度此刻不用处理」，
           否则收过分红却什么都看不到，会怀疑系统漏了。 -->
      <p v-if="deferredNote" class="tax-note tax-note--settled">
        {{ deferredNote }}
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
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { formatDate } from "@/utils/date";
import { centsToYuan } from "@/utils/currency";
import {
  ackDividendTax,
  type DividendTaxPendingItem
} from "@/api/reconciliation";
import {
  reconGroupTitle,
  reconMoney,
  reconSymbolCode
} from "../utils/reconDisplay";
import RecordTaxDialog from "./RecordTaxDialog.vue";

/**
 * 域 E：红利税待办（#541；2026-11-08 改为按「是否已卖出」分诊）。
 *
 * WHY 不再把「派息时没有扣税流水」当成待办：财税〔2015〕101 号规定派息时一律
 * 暂不扣缴、个人转让股票时才结算。所以「持有中、账上没税」是规定动作，不是漏记；
 * 只有「已卖出、持股 ≤1 年、却仍没配上税」才需要用户对照交割单。
 *
 * WHY 不复用 `DomainBDiscTable`：域 B 的行是「应然 vs 实然，算出差额」——
 * 本域没有应然值可算（不推算税率），硬套会造出一列假的「应有税额」。
 */
const props = defineProps<{
  items: DividendTaxPendingItem[];
  totalCents: number;
  pendingCount: number;
  /** 按制度暂不扣税（未卖出）的笔数 */
  deferredCount: number;
  /** 依法免税（已卖出且持股满一年）的笔数 */
  exemptCount: number;
  loading: boolean;
}>();

const emit = defineEmits<{ recorded: [] }>();

const dialogVisible = ref(false);
const activeItem = ref<DividendTaxPendingItem | null>(null);
/** 正在确认的项（按 `symbol-分红日` 定位），只让那一行转圈，不整列表一起 loading */
const ackingKey = ref<string | null>(null);

/** 底部说明：把「暂不扣税」的两种情况讲清楚，而不是让它们悄悄消失 */
const deferredNote = computed<string>(() => {
  const parts: string[] = [];
  if (props.deferredCount > 0) {
    parts.push(`${props.deferredCount} 笔仍持有（卖出时再按持有期结算）`);
  }
  if (props.exemptCount > 0) {
    parts.push(`${props.exemptCount} 笔持股已满一年（依法免税）`);
  }
  if (parts.length === 0) return "";
  return `另有 ${parts.join("、")}。派息时暂不扣缴是规定动作，不是漏记。`;
});

function openDialog(item: DividendTaxPendingItem): void {
  activeItem.value = item;
  dialogVisible.value = true;
}

/**
 * 确认「这笔确实没有税」：不记 0 元流水，只存一条确认事实（后端幂等）。
 *
 * 0 元在税法上不是「交了 0 元税」，而是「无需纳税」。记 0 元流水会虚构一次现金
 * 流出，将来真卖出被扣税时还会抢走配对额度。`account_name` 必须回传——它是这笔
 * 分红的身份之一，缺了就匹配不到（后端按 symbol + 账户 + 分红日定位）。
 */
async function ackItem(item: DividendTaxPendingItem): Promise<void> {
  if (!item.dividend_on) return;
  ackingKey.value = `${item.symbol}-${item.dividend_on}`;
  try {
    await ackDividendTax({
      symbol: item.symbol,
      account_name: item.account_name,
      dividend_on: item.dividend_on,
      reason: "确认无需记账"
    });
    ElMessage.success("已确认这笔无需记账");
    emit("recorded");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "确认失败，请稍后重试");
  } finally {
    ackingKey.value = null;
  }
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

.tax-note--settled {
  margin: 12px 0 0;
  color: var(--text-tertiary-ink);
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
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
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
