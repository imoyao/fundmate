<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑交易"
    width="460px"
    @update:model-value="val => emit('update:modelValue', val)"
    @open="initForm"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="84px"
      :disabled="saving"
    >
      <!-- 数量：基金按份额(支持小数)，股票/可转债按股|张(整数) -->
      <el-form-item label="数量" prop="quantity">
        <el-input-number
          v-model="form.quantity"
          class="w-full"
          style="width: 100%"
          :controls="false"
          :min="0"
          :precision="quantityPrecision"
          :step="quantityStep"
        >
          <template #suffix>{{ unitLabel }}</template>
        </el-input-number>
        <div class="text-xs mt-1" style="color: var(--text-tertiary)">
          <template v-if="isFund"
            >基金份额支持小数，精确到 0.0001 份</template
          >
          <template v-else>股票 / 可转债数量为整数（股 / 张）</template>
        </div>
      </el-form-item>

      <!-- 单价：支持 4 位小数 -->
      <el-form-item label="单价(元)">
        <el-input-number
          v-model="form.price"
          class="w-full"
          style="width: 100%"
          :controls="false"
          :min="0"
          :precision="4"
          :step="0.0001"
          placeholder="0.0000"
        />
      </el-form-item>

      <!-- 金额：支持 4 位小数 -->
      <el-form-item label="金额(元)">
        <el-input-number
          v-model="form.amount"
          class="w-full"
          style="width: 100%"
          :controls="false"
          :min="0"
          :precision="4"
          :step="0.01"
          placeholder="0.0000"
        />
      </el-form-item>

      <!-- 手续费：支持 4 位小数 -->
      <el-form-item label="手续费(元)">
        <el-input-number
          v-model="form.fee"
          class="w-full"
          style="width: 100%"
          :controls="false"
          :min="0"
          :precision="4"
          :step="0.01"
          placeholder="0.0000"
        />
      </el-form-item>

      <!-- 交易日期：可为空 -->
      <el-form-item label="交易日期">
        <el-date-picker
          v-model="form.trade_date"
          type="date"
          class="w-full"
          style="width: 100%"
          value-format="YYYY-MM-DD"
          placeholder="可为空"
          clearable
        />
      </el-form-item>

      <!-- 确认日期：必填 -->
      <el-form-item label="确认日期" prop="confirm_date">
        <el-date-picker
          v-model="form.confirm_date"
          type="date"
          class="w-full"
          style="width: 100%"
          value-format="YYYY-MM-DD"
          placeholder="请选择确认日期"
          clearable
        />
      </el-form-item>

      <!-- 备注 -->
      <el-form-item label="备注">
        <el-input
          v-model="form.notes"
          type="textarea"
          :rows="2"
          style="width: 100%"
          placeholder="选填"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="saving" @click="emit('update:modelValue', false)"
        >取消</el-button
      >
      <el-button type="primary" :loading="saving" @click="handleSave"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { updateLedgerTransaction } from "@/api/ledger";
import { ElMessage } from "element-plus";

const props = defineProps<{
  modelValue: boolean;
  transaction: any;
  assetType?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [data: any];
}>();

const saving = ref(false);
const formRef = ref();
const form = ref<any>({});

// 资产类型：优先用传入的 assetType，否则取交易记录里的 asset_type
const assetType = computed(
  () => props.assetType || props.transaction?.asset_type
);

// 仅基金按份额(小数)处理；其余按股/张(整数)
const isFund = computed(() => assetType.value === "fund");

const unitLabel = computed(() => {
  if (isFund.value) return "份";
  if (assetType.value === "bond") return "张";
  return "股/张";
});

const quantityPrecision = computed(() => (isFund.value ? 4 : 0));
const quantityStep = computed(() => (isFund.value ? 0.0001 : 1));

// 确认日期必填，交易日期可选
const rules = {
  confirm_date: [
    { required: true, message: "请选择确认日期", trigger: "change" }
  ]
};

function initForm() {
  const t = props.transaction || {};
  form.value = {
    quantity: t.quantity,
    price: t.price,
    amount: t.amount,
    fee: t.fee,
    trade_date: t.trade_date || null,
    confirm_date: t.confirm_date || null,
    notes: t.notes ?? ""
  };
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  const t = props.transaction;
  if (!t?.ledger_id || !t?.id) {
    ElMessage.error("缺少账户或交易信息，无法保存");
    return;
  }
  saving.value = true;
  try {
    const payload: any = {
      quantity: form.value.quantity,
      price: form.value.price,
      amount: form.value.amount,
      fee: form.value.fee,
      trade_date: form.value.trade_date || null,
      confirm_date: form.value.confirm_date || null,
      notes: form.value.notes
    };
    const res: any = await updateLedgerTransaction(t.ledger_id, t.id, payload);
    const data = res?.data ?? res;
    emit("saved", data);
    emit("update:modelValue", false);
    ElMessage.success("保存成功");
    // 手工编辑会清空 import_hash，提示用户后续重新导入需对账
    if (data && data.import_hash == null) {
      ElMessage.warning("该记录已手工编辑，重新导入时需按新内容对账");
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}

/* 输入框统一样式（高度、圆角、边框颜色、聚焦阴影）——对齐 BuyForm / SellForm 规范 */
:deep(.el-input__wrapper),
:deep(.el-input-number) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  height: 40px;
  border-radius: var(--radius-sm);
}

:deep(.el-input-number) {
  width: 100%;
}

/* 日期选择器同样占满整行，保证跨度一致 */
:deep(.el-date-editor.el-input) {
  width: 100%;
}

/* 避免校验错误过渡闪烁 */
:deep(.el-form-item__error) {
  transition: none;
}
</style>
