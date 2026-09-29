<template>
  <el-dialog
    :model-value="modelValue"
    :title="`就地补充 · ${target?.symbol || ''}`"
    width="520px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form label-width="80px" size="default">
      <el-form-item label="补充方式">
        <el-radio-group v-model="supplementForm.kind">
          <el-radio-button value="increment">补一笔交易</el-radio-button>
          <el-radio-button value="set">设定持仓</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <template v-if="supplementForm.kind === 'increment'">
        <el-form-item label="操作类型">
          <el-select v-model="supplementForm.op_type" style="width: 100%">
            <el-option label="买入" value="buy" />
            <el-option label="卖出" value="sell" />
            <el-option label="存入" value="deposit" />
            <el-option label="取出" value="withdraw" />
          </el-select>
        </el-form-item>
      </template>

      <el-form-item label="数量">
        <el-input-number
          v-model="supplementForm.quantity"
          :min="0"
          :precision="4"
          style="width: 100%"
          placeholder="份额/数量"
        />
      </el-form-item>
      <el-form-item label="价格">
        <el-input-number
          v-model="supplementForm.avg_price"
          :min="0"
          :precision="4"
          style="width: 100%"
          placeholder="净值/单价"
        />
      </el-form-item>
      <el-form-item
        :label="supplementForm.kind === 'increment' ? '确认日期' : '快照日期'"
      >
        <el-date-picker
          v-model="supplementForm.confirm_date"
          type="date"
          value-format="YYYY-MM-DD"
          style="width: 100%"
          placeholder="选择日期"
        />
      </el-form-item>
      <el-form-item label="原因">
        <el-input
          v-model="supplementForm.reason"
          type="textarea"
          :rows="2"
          placeholder="补充说明（选填）"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="supplementing"
        @click="submitSupplement"
      >
        确认补充
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  applyAdjustment,
  type DiscrepancyItem,
  type AdjustmentPayload
} from "@/api/reconciliation";

/** 就地补充弹窗（§6.4，#980 拆分自 index.vue，零行为变更）：
 *  工作台内直接补录（调 apply_decision），绝不跳「记一笔」。
 *  表单状态与提交逻辑内聚在弹窗内，打开时重置（等价拆分前 openSupplement 的逐字段重置）。 */
const props = defineProps<{
  modelValue: boolean;
  target: DiscrepancyItem | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const supplementForm = reactive({
  kind: "increment" as "increment" | "set",
  op_type: "buy",
  quantity: undefined as number | undefined,
  avg_price: undefined as number | undefined,
  confirm_date: "",
  reason: ""
});
const supplementing = ref(false);

/** 每次打开弹窗时重置表单（对应原 openSupplement 的重置语义） */
watch(
  () => props.modelValue,
  open => {
    if (!open) return;
    supplementForm.kind = "increment";
    supplementForm.op_type = "buy";
    supplementForm.quantity = undefined;
    supplementForm.avg_price = undefined;
    supplementForm.confirm_date = "";
    supplementForm.reason = "";
  }
);

/** 提交就地补充（调 apply_decision，不跳「记一笔」） */
async function submitSupplement(): Promise<void> {
  const target = props.target;
  if (!target) return;
  if (!supplementForm.quantity || !supplementForm.avg_price) {
    ElMessage.warning("请填写数量与价格");
    return;
  }
  supplementing.value = true;
  try {
    const payload: AdjustmentPayload = {
      kind: supplementForm.kind,
      discrepancy_id: target.id,
      symbol: target.symbol,
      ledger_id: target.ledger_id,
      quantity: supplementForm.quantity,
      avg_price: supplementForm.avg_price,
      reason: supplementForm.reason || undefined
    };
    if (supplementForm.kind === "increment") {
      payload.op_type = supplementForm.op_type;
      payload.confirm_date = supplementForm.confirm_date || undefined;
    } else {
      payload.snapshot_date = supplementForm.confirm_date || undefined;
    }
    await applyAdjustment(payload);
    ElMessage.success("补充完成");
    emit("update:modelValue", false);
    emit("submitted");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "补充失败");
  } finally {
    supplementing.value = false;
  }
}
</script>
