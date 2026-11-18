<template>
  <section class="profile-card profile-card-enter">
    <SectionHeader
      title="家庭财务规划"
      subtitle="用于首页财务晴雨表的财务自由度 / 时间自由度"
    />

    <p class="finance-intro">
      填入家庭的预估年支出与年收入后，晴雨表会用「可投资资产 × 3% ÷
      年支出/年收入」算出两项自由度。不填则只显示可提取金额，不会用假数字。
    </p>

    <div class="finance-field">
      <label class="finance-field__label" for="annual-expense">
        预估年支出（元）
      </label>
      <div class="finance-field__row">
        <el-input-number
          id="annual-expense"
          v-model="expense"
          class="finance-field__input"
          :min="0"
          :max="1000000000"
          :precision="2"
          :controls="false"
          placeholder="未设置"
        />
        <span class="finance-field__unit">元 / 年</span>
      </div>
    </div>

    <div class="finance-field">
      <label class="finance-field__label" for="annual-income">
        预估年收入（元）
      </label>
      <div class="finance-field__row">
        <el-input-number
          id="annual-income"
          v-model="income"
          class="finance-field__input"
          :min="0"
          :max="1000000000"
          :precision="2"
          :controls="false"
          placeholder="未设置"
        />
        <span class="finance-field__unit">元 / 年</span>
      </div>
    </div>

    <div class="finance-actions">
      <span v-if="loadError" class="finance-hint finance-hint--warn">
        读取失败，请稍后重试
      </span>
      <span v-else-if="!dirty" class="finance-hint">
        {{ configured ? "已保存，修改后点保存生效" : "留空表示未配置" }}
      </span>
      <el-button
        type="primary"
        :disabled="!dirty || saving || loadError"
        :loading="saving"
        @click="onSave"
      >
        保存
      </el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getFinancialPlan, putFinancialPlan } from "@/api/financialPlan";

defineOptions({ name: "ProfileFinanceSection" });

const expense = ref<number | null>(null);
const income = ref<number | null>(null);
const savedExpense = ref<number | null>(null);
const savedIncome = ref<number | null>(null);
const saving = ref(false);
const loadError = ref(false);

// 归一 undefined（el-input-number 清空值）为 null，避免把「没动过」误判成 dirty
const dirty = computed(
  () =>
    (expense.value ?? null) !== (savedExpense.value ?? null) ||
    (income.value ?? null) !== (savedIncome.value ?? null)
);
const configured = computed(
  () => savedExpense.value != null || savedIncome.value != null
);

const load = async () => {
  loadError.value = false;
  try {
    const res = await getFinancialPlan();
    const data = res.data;
    expense.value = data?.estimated_annual_expense ?? null;
    income.value = data?.estimated_annual_income ?? null;
    savedExpense.value = expense.value;
    savedIncome.value = income.value;
  } catch {
    loadError.value = true;
  }
};

const onSave = async () => {
  if (!dirty.value || saving.value) return;
  saving.value = true;
  try {
    // el-input-number 清空时把 modelValue 置为 undefined，JSON 序列化会丢字段，
    // 服务端 model_fields_set 就收不到 → 用户无法清除已填值。显式归一为 null。
    const res = await putFinancialPlan({
      estimated_annual_expense: expense.value ?? null,
      estimated_annual_income: income.value ?? null
    });
    expense.value = res.data?.estimated_annual_expense ?? null;
    income.value = res.data?.estimated_annual_income ?? null;
    savedExpense.value = expense.value;
    savedIncome.value = income.value;
    ElMessage.success("已保存");
  } catch {
    ElMessage.error("保存失败，请稍后重试");
  } finally {
    saving.value = false;
  }
};

onMounted(load);
</script>

<style scoped>
.finance-intro {
  margin: 0 0 var(--space-standard);
  font-size: var(--text-small);
  line-height: 1.6;
  color: var(--text-secondary);
}

.finance-field {
  padding: var(--space-4) 0;
  border-top: 1px solid var(--border-subtle);
}

.finance-field__label {
  display: block;
  margin-bottom: var(--space-2);
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.finance-field__row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}

.finance-field__input {
  flex: 1;
  min-width: 120px;
}

.finance-field__unit {
  flex-shrink: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.finance-actions {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: flex-end;
  padding-top: var(--space-standard);
  border-top: 1px solid var(--border-subtle);
}

.finance-hint {
  margin-right: auto;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.finance-hint--warn {
  color: var(--color-warning-ink);
}
</style>
