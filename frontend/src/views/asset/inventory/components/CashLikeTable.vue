<template>
  <CardBlock>
    <el-table
      v-loading="loading"
      :data="items"
      style="width: 100%"
      :header-cell-style="INVENTORY_TABLE_HEADER_STYLE"
      :cell-style="INVENTORY_TABLE_CELL_STYLE"
    >
      <el-table-column label="产品信息" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name"
            :symbol="row.symbol || ''"
            :type-label="row.asset_type_label"
          />
        </template>
      </el-table-column>
      <el-table-column
        prop="ledger_name"
        label="归属账户"
        width="130"
        show-overflow-tooltip
      />
      <el-table-column label="本金" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay :value="row.net_amount" :show-sign="false" size="sm" />
        </template>
      </el-table-column>
      <el-table-column label="累计收益" width="120" align="right">
        <template #default="{ row }">
          <MoneyDisplay :value="row.income_amount" size="sm" />
        </template>
      </el-table-column>
      <el-table-column label="合计" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.total_amount"
            :show-sign="false"
            size="sm"
          />
        </template>
      </el-table-column>
      <!-- 逆回购只有「买入」被导入时，在途本金会只增不减（#3087）：到期回款是它唯一的
           出口。货基没有到期，赎回本就该走申购/赎回流水，故这里不给它任何按钮。 -->
      <el-table-column label="操作" width="110" align="center">
        <template #default="{ row }">
          <el-button
            v-if="canSettle(row as CashLikeItem)"
            link
            type="primary"
            @click="openSettle(row as CashLikeItem)"
          >
            到期回款
          </el-button>
          <span v-else class="cash-like-noop">--</span>
        </template>
      </el-table-column>

      <template #append>
        <div class="cash-like-footer">
          <span class="cash-like-footer__label">类现金合计</span>
          <span class="cash-like-footer__value">
            <MoneyDisplay :value="total" :show-sign="false" />
          </span>
          <span class="cash-like-footer__hint">
            按流水净额记账（不折算份额），金额已计入总资产，此处不重复加总
          </span>
        </div>
      </template>
    </el-table>
  </CardBlock>

  <el-dialog
    v-model="settleVisible"
    title="逆回购到期回款"
    width="440px"
    :close-on-click-modal="false"
  >
    <el-form label-width="86px">
      <el-form-item label="产品">
        <span>{{ settleRow?.name }}（{{ settleRow?.symbol }}）</span>
      </el-form-item>
      <el-form-item label="结清本金">
        <span>{{ formatAmount(settleRow?.net_amount ?? 0) }}</span>
        <p class="cash-like-dialog-hint">
          逆回购到期一次性还本，金额恒等于当前在途本金，不可拆分
        </p>
      </el-form-item>
      <el-form-item label="回款日">
        <el-date-picker
          v-model="settleDate"
          type="date"
          value-format="YYYY-MM-DD"
          :clearable="false"
          placeholder="选择到账日"
        />
      </el-form-item>
      <el-form-item label="利息">
        <el-input-number
          v-model="interest"
          :min="0"
          :precision="2"
          :controls="false"
          placeholder="0.00"
        />
        <p class="cash-like-dialog-hint">
          到期利息单独记一笔收益（不是本金），留空即无
        </p>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="settleVisible = false">取消</el-button>
      <el-button type="primary" :loading="settling" @click="submitSettle">
        登记回款
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 投资理财 · 「类现金」分组（2026-10-17）。
 *
 * 货基 / 逆回购在本仓**不建持仓行**（`position_id IS NULL` 的孤儿流水，
 * 口径见 `summary_service.orphan_money_fund_totals_by_ledger`），因此不会出现在
 * 上面的持仓明细表里，但它们是真实资产、已计入总资产。
 *
 * 这张表只回答「这些钱分别躺在哪个账户的哪个产品上」：
 * ① 只展示、不参与持仓盈亏与占比；② 金额不得再加进页面任何合计（双计）。
 *
 * 数据源 `GET /api/summary/cash-like/`（家庭级，按「账户 + 产品」归组）。
 *
 * 唯一写操作是逆回购「到期回款」（#3087）：导入只带来买入那一半，没有回款入口时
 * 在途本金只增不减。服务端整笔结清 + 利息单独成行，见 `api/ledger.ts::settleReverseRepo`。
 */
import { ref } from "vue";
import { ElMessage } from "element-plus";
import CardBlock from "@/components/CardBlock/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import type { CashLikeItem } from "@/api/summary";
import { settleReverseRepo } from "@/api/ledger";
import { formatAmount } from "@/utils/currency";
import { getErrorMessage } from "../helpers";
import {
  INVENTORY_TABLE_CELL_STYLE,
  INVENTORY_TABLE_HEADER_STYLE
} from "../constants";

defineProps<{
  /** 类现金明细（调用方保证非空才渲染本组件） */
  items: CashLikeItem[];
  /** 合计（本金 + 收益，元） */
  total: number;
  loading?: boolean;
}>();

const emit = defineEmits<{
  /** 登记成功后由页面重新取数（本组件不持有数据源） */
  (e: "settled"): void;
}>();

const settleVisible = ref(false);
const settling = ref(false);
const settleRow = ref<CashLikeItem | null>(null);
const settleDate = ref("");
const interest = ref<number | undefined>(undefined);

/**
 * 只有「逆回购 + 仍有在途本金」才可回款。
 * 货基没有到期（赎回走申购/赎回流水），本金已归零的逆回购再点也只会被后端拒。
 */
function canSettle(row: CashLikeItem): boolean {
  return row.asset_type === "reverse_repo" && row.net_amount > 0;
}

function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function openSettle(row: CashLikeItem) {
  settleRow.value = row;
  settleDate.value = todayIso();
  interest.value = undefined;
  settleVisible.value = true;
}

async function submitSettle() {
  const row = settleRow.value;
  if (!row || row.ledger_id === null || !row.symbol) {
    ElMessage.error("该行缺少账户或标的代码，无法登记回款");
    return;
  }
  if (!settleDate.value) {
    ElMessage.error("请选择回款日");
    return;
  }
  settling.value = true;
  try {
    const res = await settleReverseRepo(row.ledger_id, {
      symbol: row.symbol,
      settle_date: settleDate.value,
      interest: interest.value ?? 0
    });
    ElMessage.success(res.message || "已登记回款");
    settleVisible.value = false;
    emit("settled");
  } catch (e) {
    ElMessage.error(getErrorMessage(e, "登记回款失败"));
  } finally {
    settling.value = false;
  }
}
</script>

<style scoped lang="scss">
.cash-like-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  padding: 10px 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.cash-like-footer__label {
  font-weight: 600;
  color: var(--text-primary);
}

.cash-like-footer__value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.cash-like-footer__hint {
  color: var(--text-tertiary-ink);
}

.cash-like-noop {
  color: var(--text-tertiary-ink);
}

.cash-like-dialog-hint {
  margin: 4px 0 0;
  font-size: var(--text-label);
  line-height: 1.4;
  color: var(--text-tertiary-ink);
}
</style>
