<template>
  <el-dialog
    :model-value="modelValue"
    :title="plan ? '编辑定投计划' : '新建定投计划'"
    width="560px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form label-width="88px" @submit.prevent>
      <el-form-item label="标的代码">
        <div class="flex gap-2 w-full">
          <el-input
            v-model="form.symbol"
            placeholder="如 110011"
            class="w-40"
          />
          <el-input v-model="form.position_name" placeholder="名称（可选）" />
        </div>
      </el-form-item>

      <el-form-item label="资产类型">
        <el-select
          v-model="form.asset_type"
          class="w-40"
          filterable
          allow-create
          default-first-option
        >
          <el-option
            v-for="opt in ASSET_TYPE_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="每期金额">
        <el-input v-model="form.amountYuan" class="w-40" placeholder="1000">
          <template #prefix>¥</template>
        </el-input>
        <span
          class="ml-2 text-xs"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          按金额定投；份额以实际成交为准
        </span>
      </el-form-item>

      <el-form-item label="扣款频率">
        <el-select
          v-model="form.frequency"
          class="w-32"
          @change="onFrequencyChange"
        >
          <el-option
            v-for="opt in FREQUENCY_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>

        <template v-if="form.frequency === 'monthly'">
          <span class="mx-2">每月</span>
          <el-input-number
            v-model="form.day_of_period"
            :min="1"
            :max="28"
            :controls="false"
            class="w-20"
          />
          <span class="ml-1">日</span>
        </template>

        <template v-else-if="form.frequency === 'weekly'">
          <span class="mx-2">每周</span>
          <el-select
            v-model="form.day_of_period"
            class="w-24"
            placeholder="周一"
          >
            <el-option
              v-for="(label, index) in WEEKDAY_LABELS"
              :key="label"
              :label="label"
              :value="index + 1"
            />
          </el-select>
        </template>
      </el-form-item>

      <el-form-item label="开始日期">
        <el-date-picker
          v-model="form.start_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="首次扣款日"
          class="w-40"
        />
        <span
          class="ml-2 text-xs"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          留空的扣款日按这一天推算
        </span>
      </el-form-item>

      <el-form-item label="结束日期">
        <el-date-picker
          v-model="form.end_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="长期有效"
          clearable
          class="w-40"
        />
      </el-form-item>

      <el-form-item label="关联账户">
        <el-select
          v-model="form.ledger_id"
          class="w-56"
          placeholder="不归属具体账户"
          clearable
          filterable
        >
          <el-option
            v-for="ledger in ledgers"
            :key="ledger.id"
            :label="ledger.name"
            :value="ledger.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="备注">
        <el-input
          v-model="form.note"
          type="textarea"
          :rows="2"
          maxlength="500"
          show-word-limit
          placeholder="如：工资到账后自动买（本页只做计划，不自动扣款）"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type { RecurringPlan, RecurringPlanPayload } from "@/api/recurring";
import { createRecurringPlan, updateRecurringPlan } from "@/api/recurring";
import {
  EMPTY_PLAN_FORM,
  FREQUENCY_OPTIONS,
  WEEKDAY_LABELS,
  planToForm,
  validatePlanForm,
  yuanToCents,
  type PlanForm
} from "../recurringModel";

const props = defineProps<{
  modelValue: boolean;
  /** null = 新建；否则为被编辑的计划 */
  plan: RecurringPlan | null;
  ledgers: { id: number; name: string }[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const ASSET_TYPE_OPTIONS = [
  { value: "fund", label: "场外基金" },
  { value: "etf", label: "ETF" },
  { value: "stock", label: "股票" },
  { value: "bond", label: "债券/可转债" },
  { value: "cash", label: "现金/货基" }
];

const form = ref<PlanForm>({ ...EMPTY_PLAN_FORM });
const saving = ref(false);

watch(
  () => [props.modelValue, props.plan] as const,
  () => {
    if (!props.modelValue) return;
    form.value = props.plan ? planToForm(props.plan) : { ...EMPTY_PLAN_FORM };
  },
  { immediate: true }
);

/** 切频率时清理不合法的扣款日：从「每月 15 日」切到「每两周」不该留下 15 */
const onFrequencyChange = () => {
  if (form.value.frequency === "biweekly") {
    form.value.day_of_period = null;
  } else if (
    form.value.frequency === "weekly" &&
    (form.value.day_of_period ?? 0) > 7
  ) {
    form.value.day_of_period = 1;
  }
};

const handleSave = async () => {
  const error = validatePlanForm(form.value);
  if (error) {
    ElMessage.warning(error);
    return;
  }
  const cents = yuanToCents(form.value.amountYuan);
  if (cents === null) {
    ElMessage.warning("每期金额需为正数");
    return;
  }
  const payload: RecurringPlanPayload = {
    symbol: form.value.symbol.trim(),
    position_name: form.value.position_name.trim() || null,
    asset_type: form.value.asset_type || null,
    amount: cents,
    frequency: form.value.frequency,
    day_of_period: form.value.day_of_period ?? null,
    start_date: form.value.start_date,
    end_date: form.value.end_date || null,
    ledger_id: form.value.ledger_id ?? null,
    note: form.value.note.trim() || null
  };

  saving.value = true;
  try {
    if (props.plan) {
      await updateRecurringPlan(props.plan.id, payload);
      ElMessage.success("计划已更新");
    } else {
      await createRecurringPlan(payload);
      ElMessage.success("计划已创建");
    }
    emit("update:modelValue", false);
    emit("saved");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
};
</script>
