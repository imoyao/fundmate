<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'create' ? '补录账外类现金流水' : '编辑账外类现金流水'"
    width="560px"
    @update:model-value="v => emit('update:visible', v)"
  >
    <el-alert type="info" :closable="false" show-icon class="mb-4">
      <template #title>口径说明</template>
      这些是<strong>账外流水</strong>，不建持仓行、不进持仓合计；金额已计入总资产。
      系统不批量回填交易日与代码，只有你在这里显式填写的值才会被写入。
    </el-alert>

    <el-form label-width="110px" @submit.prevent>
      <template v-if="mode === 'create'">
        <el-form-item label="资产类型" required>
          <el-select v-model="form.assetType" style="width: 100%">
            <el-option label="逆回购" value="reverse_repo" />
            <el-option label="货币基金" value="money_fund" />
          </el-select>
        </el-form-item>
        <el-form-item label="补录动作" required>
          <el-select v-model="form.kind" style="width: 100%">
            <el-option label="到期回款（本金 + 利息）" value="repayment" />
            <el-option label="买入 / 申购" value="buy" />
            <el-option label="赎回 / 卖出" value="sell" />
            <el-option label="取出" value="withdraw" />
            <el-option label="收益到账" value="dividend_cash" />
            <el-option label="代扣税" value="dividend_tax" />
          </el-select>
        </el-form-item>
      </template>
      <el-form-item v-else label="流水类型">
        <el-select v-model="form.txnType" style="width: 100%">
          <el-option
            v-for="t in EDIT_TYPES"
            :key="t.value"
            :label="t.label"
            :value="t.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item
        :label="form.kind === 'repayment' ? '回款本金(元)' : '金额(元)'"
        required
      >
        <el-input-number
          v-model="form.amount"
          :min="0"
          :precision="2"
          :step="100"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item
        v-if="mode === 'create' && form.kind === 'repayment'"
        label="到期利息(元)"
      >
        <el-input-number
          v-model="form.interest"
          :min="0"
          :precision="2"
          style="width: 100%"
        />
        <span class="form-hint"
          >利息进「收益桶」，不重复计本金；为 0 则不落收益流水</span
        >
      </el-form-item>

      <el-form-item label="确认日期" required>
        <el-date-picker
          v-model="form.confirmDate"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="用户显式录入"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item v-if="mode === 'edit'" label="交易日">
        <el-date-picker
          v-model="form.tradeDate"
          type="date"
          value-format="YYYY-MM-DD"
          clearable
          placeholder="留空 = 不修改"
          style="width: 100%"
        />
        <span class="form-hint"
          >只接受单笔显式手填；不做批量回填，也不从确认日推断</span
        >
      </el-form-item>

      <el-form-item label="产品名称">
        <el-input
          v-model="form.positionName"
          placeholder="如 GC001 / 银河水星现金添利"
        />
      </el-form-item>
      <el-form-item label="产品代码">
        <el-input v-model="form.symbol" placeholder="手填；或从下方持仓带入" />
      </el-form-item>
      <el-form-item label="从持仓带入">
        <el-select
          v-model="pickedTargetId"
          placeholder="选一个同账户持仓（代码会标注为「推断」）"
          filterable
          clearable
          style="width: 100%"
          @change="onPickTarget"
        >
          <el-option
            v-for="t in targets"
            :key="t.id"
            :label="`${t.name}（${t.symbol || '无代码'}）`"
            :value="t.id"
          />
        </el-select>
        <span v-if="form.symbolInferred" class="form-hint">
          当前代码标注为「从持仓推断」，不是原始导入事实
        </span>
      </el-form-item>

      <el-form-item label="来源">
        <el-select v-model="form.source" style="width: 100%" clearable>
          <el-option
            v-for="s in SOURCE_OPTIONS"
            :key="s.value"
            :label="s.label"
            :value="s.value"
          />
        </el-select>
        <span class="form-hint"
          >source 是系统元数据，可补；import_hash 去重键保持不变</span
        >
      </el-form-item>
      <el-form-item label="备注">
        <el-input
          v-model="form.notes"
          type="textarea"
          :rows="2"
          placeholder="可选，如「2025-09-29 GC001 到期」"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 账外类现金流水「补录 / 编辑」表单。
 *
 * 与持仓记账表单刻意分开：这里不建 Position、不填份额净值，
 * 且**不做任何批量元数据回填**（D99）。「到期回款」是逆回购专属动作：
 * 真库 4 笔逆回购全是 buy、没有一笔回款，净额因此恒为 +20.2 万的在途额。
 */
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type {
  CashLikeCreateInput,
  CashLikeFlow,
  CashLikeFlowKind,
  CashLikeTarget,
  CashLikeUpdateInput
} from "@/api/cashLike";

defineOptions({ name: "CashLikeFlowForm" });

const props = defineProps<{
  visible: boolean;
  mode: "create" | "edit";
  flow: CashLikeFlow | null;
  ledgerId: number | null;
  targets: CashLikeTarget[];
  submitting: boolean;
}>();

const emit = defineEmits<{
  (e: "update:visible", v: boolean): void;
  (e: "submit-create", data: Omit<CashLikeCreateInput, "client_token">): void;
  (e: "submit-edit", id: number, data: CashLikeUpdateInput): void;
}>();

const EDIT_TYPES: Array<{
  value: Exclude<CashLikeFlowKind, "repayment">;
  label: string;
}> = [
  { value: "buy", label: "买入 / 申购" },
  { value: "sell", label: "卖出 / 赎回" },
  { value: "withdraw", label: "取出" },
  { value: "dividend_cash", label: "收益到账" },
  { value: "dividend_tax", label: "代扣税" }
];

const SOURCE_OPTIONS = [
  { value: "manual", label: "手动录入" },
  { value: "reconciliation_adjustment", label: "对账补录" },
  { value: "ths_stock", label: "同花顺导入" },
  { value: "standard_template", label: "通用模板导入" }
];

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

const form = reactive({
  assetType: "reverse_repo" as "money_fund" | "reverse_repo",
  kind: "repayment" as CashLikeFlowKind,
  txnType: "buy" as Exclude<CashLikeFlowKind, "repayment">,
  amount: 0,
  interest: 0,
  confirmDate: today(),
  tradeDate: "",
  positionName: "",
  symbol: "",
  symbolInferred: false,
  source: "manual",
  notes: ""
});

watch(
  () => props.visible,
  shown => {
    if (!shown) return;
    const flow = props.flow;
    form.assetType =
      (flow?.asset_type as "money_fund" | "reverse_repo") || "reverse_repo";
    form.kind = "repayment";
    form.txnType =
      (flow?.txn_type as Exclude<CashLikeFlowKind, "repayment">) || "buy";
    form.amount = flow?.amount ?? 0;
    form.interest = 0;
    form.confirmDate = flow?.confirm_date || today();
    form.tradeDate = flow?.trade_date || "";
    form.positionName = flow?.position_name || "";
    form.symbol = flow?.symbol || "";
    form.symbolInferred = flow?.symbol_inferred || false;
    form.source = flow?.source || "manual";
    form.notes = flow?.notes || "";
  }
);

const pickedTargetId = ref<number | "">("");

function onPickTarget(id: number | "" | undefined) {
  if (!id) return;
  const target = props.targets.find(t => t.id === id);
  if (!target) return;
  form.symbol = target.symbol;
  if (!form.positionName) form.positionName = target.name;
  form.symbolInferred = Boolean(target.symbol);
  pickedTargetId.value = "";
}

function handleSubmit() {
  if (!form.confirmDate) {
    ElMessage.warning("请填写确认日期");
    return;
  }
  if (!form.amount || form.amount <= 0) {
    ElMessage.warning("金额必须大于 0");
    return;
  }
  if (!props.ledgerId) {
    ElMessage.warning("缺少账户信息，请从账户详情页进入");
    return;
  }
  if (props.mode === "create") {
    emit("submit-create", {
      ledger_id: props.ledgerId,
      asset_type: form.assetType,
      confirm_date: form.confirmDate,
      kind: form.kind,
      amount: form.amount,
      interest: form.kind === "repayment" ? form.interest : undefined,
      position_name: form.positionName,
      symbol: form.symbol,
      symbol_inferred: form.symbolInferred,
      source: form.source,
      notes: form.notes
    });
    return;
  }
  if (!props.flow) return;
  emit("submit-edit", props.flow.id, {
    amount: form.amount,
    confirm_date: form.confirmDate,
    trade_date: form.tradeDate,
    position_name: form.positionName,
    symbol: form.symbol,
    symbol_inferred: form.symbolInferred,
    source: form.source,
    notes: form.notes,
    txn_type: form.txnType
  });
}
</script>

<style scoped lang="scss">
.form-hint {
  display: block;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}
</style>
