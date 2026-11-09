<template>
  <!--
    正式补记弹窗，替换 ElMessageBox.prompt。
    旧弹窗只有一个输入框：不显示税前分红 / 账户 / 已记税额，句子还断在「填写 X 这笔
    分红的税额（元）」；placeholder 更用 10% 反推了一个「例如 4.60」，把猜数塞给用户
    抄进账本（同文件注释明明写了「刻意不给默认金额」）。这里全部改掉。
  -->
  <el-dialog
    :model-value="modelValue"
    title="补记这笔分红的扣税"
    width="520px"
    @update:model-value="close"
  >
    <template v-if="item">
      <dl class="tax-dialog__context">
        <div>
          <dt>标的</dt>
          <dd>{{ item.name || item.symbol }}</dd>
        </div>
        <div>
          <dt>标的代码</dt>
          <dd>{{ item.symbol }}</dd>
        </div>
        <div>
          <dt>分红日</dt>
          <dd>{{ formatDate(item.dividend_on) }}</dd>
        </div>
        <div>
          <dt>税前分红</dt>
          <dd>{{ reconMoney(centsToYuan(item.dividend_cents)) }}</dd>
        </div>
        <div>
          <dt>所属账户</dt>
          <dd>{{ item.account_name || "账户名未填" }}</dd>
        </div>
        <div>
          <dt>当前已记税额</dt>
          <dd>
            {{
              item.tax_cents > 0
                ? reconMoney(centsToYuan(item.tax_cents))
                : "还没有记录"
            }}
          </dd>
        </div>
      </dl>

      <p class="tax-dialog__why">
        这笔现金分红在券商交割单上被扣了税，账里还没有这笔支出。红利税按实际持股期计算，
        税率取决于买入批次，系统不推算税额。填交割单上「红利税」一栏的金额。
      </p>

      <div class="tax-dialog__form">
        <label class="tax-dialog__field">
          <span>实际扣税额</span>
          <span class="tax-dialog__input">
            <span class="tax-dialog__prefix">¥</span>
            <el-input-number
              v-model="amount"
              :min="0"
              :precision="2"
              :controls="false"
              :step="0.01"
              placeholder="以交割单金额为准"
            />
          </span>
        </label>
        <label class="tax-dialog__field">
          <span>扣税日期</span>
          <el-date-picker
            v-model="taxOn"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择扣税日期"
          />
        </label>
      </div>

      <p v-if="validationError" class="tax-dialog__error" role="alert">
        {{ validationError }}
      </p>

      <p class="tax-dialog__effect">
        确认后生成一笔扣税流水，可在交易流水中查看或撤销；同一标的同一天重复提交不会重复记账。
      </p>
    </template>

    <template #footer>
      <el-button @click="close(false)">取消</el-button>
      <el-button
        type="primary"
        :disabled="Boolean(validationError) || !item"
        :loading="submitting"
        @click="submit"
      >
        确认补记
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch } from "vue";
import { ElMessage } from "element-plus";
import { useNestedDialog } from "../composables/useNestedDialog";
import { formatDate } from "@/utils/date";
import { centsToYuan } from "@/utils/currency";
import { recordDividendTax } from "@/api/reconciliation";
import type { DividendTaxPendingItem } from "@/api/reconciliation";
import { reconMoney } from "../utils/reconDisplay";

defineOptions({ name: "RecordTaxDialog" });

const props = defineProps<{
  modelValue: boolean;
  item: DividendTaxPendingItem | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  recorded: [];
}>();

useNestedDialog(toRef(props, "modelValue"));

const amount = ref<number | null>(null);
const taxOn = ref<string>("");
const submitting = ref(false);

/** 每次打开都从空白表单开始；默认日期是分红日，可改成交割单上的实际扣税日 */
watch(
  () => props.modelValue,
  visible => {
    if (!visible) return;
    amount.value = null;
    taxOn.value = props.item?.dividend_on ?? "";
    submitting.value = false;
  }
);

const dividendYuan = computed(() =>
  centsToYuan(props.item?.dividend_cents ?? 0)
);

/** 校验即文案：描述问题 + 给出下一步，不用「请」 */
const validationError = computed(() => {
  if (!props.item) return "分红记录已不在列表中，关闭后重新检查。";
  const value = amount.value;
  if (value === null || !Number.isFinite(value) || value <= 0) {
    return "填写大于 0 的金额，以交割单上「红利税」一栏为准。";
  }
  if (value > dividendYuan.value * 0.2 + 0.001) {
    return `金额超过税前分红的 20%（最多 ${reconMoney(dividendYuan.value * 0.2)}）。核对是否记错品种或看错栏位。`;
  }
  if (!taxOn.value) return "选择扣税日期，默认用分红日。";
  return "";
});

function close(value: boolean): void {
  emit("update:modelValue", value);
}

async function submit(): Promise<void> {
  if (!props.item || validationError.value || amount.value === null) return;
  submitting.value = true;
  try {
    await recordDividendTax({
      symbol: props.item.symbol,
      amount: amount.value,
      tax_on: taxOn.value || undefined,
      account_name: props.item.account_name || undefined
    });
    ElMessage.success("已补记这笔扣税，正在刷新列表");
    emit("recorded");
    emit("update:modelValue", false);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err.response?.data?.message || "补记失败，检查后重试");
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.tax-dialog__context {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-2) var(--space-3);
  padding: var(--space-compact);
  margin: 0 0 var(--space-3);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.tax-dialog__context div {
  min-width: 0;
}

.tax-dialog__context dt {
  margin-bottom: 2px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.tax-dialog__context dd {
  margin: 0;
  font-size: var(--text-small);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.tax-dialog__why,
.tax-dialog__effect {
  margin: 0 0 var(--space-3);
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}

.tax-dialog__effect {
  padding-top: var(--space-2);
  margin-bottom: 0;
  color: var(--text-tertiary-ink);
  border-top: 1px solid var(--border-light);
}

.tax-dialog__form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.tax-dialog__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.tax-dialog__input {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.tax-dialog__prefix {
  font-size: var(--text-body);
  color: var(--text-primary);
}

.tax-dialog__error {
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-danger-ink);
}
</style>
