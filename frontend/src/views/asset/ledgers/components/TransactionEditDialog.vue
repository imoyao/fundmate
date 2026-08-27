<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑交易"
    width="460px"
    @update:model-value="val => emit('update:modelValue', val)"
    @open="initForm"
  >
    <el-form :model="form" label-width="84px" :disabled="saving">
      <el-form-item label="数量">
        <el-input
          v-model.number="form.quantity"
          type="number"
          :placeholder="`单位：${unitLabel}`"
        >
          <template #append>{{ unitLabel }}</template>
        </el-input>
      </el-form-item>
      <el-form-item label="单价(元)">
        <el-input v-model.number="form.price" type="number" />
      </el-form-item>
      <el-form-item label="金额(元)">
        <el-input v-model.number="form.amount" type="number" />
      </el-form-item>
      <el-form-item label="手续费(元)">
        <el-input v-model.number="form.fee" type="number" />
      </el-form-item>
      <el-form-item label="交易日期">
        <el-date-picker
          v-model="form.trade_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          class="w-full"
        />
      </el-form-item>
      <el-form-item label="确认日期">
        <el-date-picker
          v-model="form.confirm_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="可为空"
          clearable
          class="w-full"
        />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.notes" type="textarea" :rows="2" />
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
const form = ref<any>({});

const unitLabel = computed(() => {
  const t = props.assetType || props.transaction?.asset_type;
  return t === "fund" ? "份" : "股/张";
});

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
