<!--
  LedgerReverseRepoSettleDialog · 账户详情页的逆回购「到期回款」弹窗

  背景：#3087 / D114 的回款端点只在「全面盘点」页（CashLikeTable）接了按钮，
  账户详情页虽然能看到这些孤儿流水，却没有任何办法把它们结清——用户看到的是
  「一堆只有买入、永远卖不掉的逆回购」。本组件把同一条受限写入口接到账户详情页：
  不新建通用流水接口，只调 `POST /api/ledgers/<id>/cash-like/reverse-repo/settle/`。

  口径与盘点页保持一字不差（D114）：整笔结清（金额恒等于在途本金，不可拆分）、
  利息单独成行、重复提交由后端「没有在途本金」拒绝。产品由调用方按
  `asset_type === 'reverse_repo' && net_amount > 0 && symbol` 先筛过，这里不再猜。
-->
<template>
  <el-dialog
    v-model="visible"
    title="逆回购到期回款"
    width="440px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <el-form label-width="86px">
      <el-form-item label="产品">
        <el-select
          v-if="rows.length > 1"
          v-model="selectedSymbol"
          placeholder="选择要结清的逆回购"
        >
          <el-option
            v-for="row in rows"
            :key="row.symbol || ''"
            :label="`${row.name}（${row.symbol}）`"
            :value="row.symbol || ''"
          />
        </el-select>
        <span v-else>
          {{ selectedRow?.name }}（{{ selectedRow?.symbol }}）
        </span>
      </el-form-item>
      <el-form-item label="结清本金">
        <span>{{ formatAmount(selectedRow?.net_amount ?? 0) }}</span>
        <p class="settle-hint">
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
        <p class="settle-hint">到期利息单独记一笔收益（不是本金），留空即无</p>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!selectedRow"
        @click="submit"
      >
        登记回款
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { errorMessageOf } from "@/utils/errorMessage";
import { settleReverseRepo } from "@/api/ledger";
import { formatAmount } from "@/utils/currency";
import type { CashLikeBreakdownRow } from "@/composables/ledger/types";

defineOptions({ name: "LedgerReverseRepoSettleDialog" });

const props = defineProps<{
  modelValue: boolean;
  /** 目标账户 id；缺失时不允许提交（回款行必须挂在账户上） */
  ledgerId?: number;
  /** 可结清的逆回购明细行（调用方已按 D114 判据筛过） */
  rows: CashLikeBreakdownRow[];
  /** 从明细行点进来时预选的产品代码 */
  initialSymbol?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [visible: boolean];
  /** 已写入（调用方刷新账户概览，否则页面数字停在旧值） */
  settled: [];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value)
});

const selectedSymbol = ref("");
const settleDate = ref("");
const interest = ref<number | undefined>(undefined);
const submitting = ref(false);

const selectedRow = computed(
  () =>
    props.rows.find(row => row.symbol === selectedSymbol.value) ??
    props.rows[0] ??
    null
);

function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

// 每次打开都重置表单：上一轮的日期 / 利息不能带进下一笔回款。
watch(
  () => props.modelValue,
  opened => {
    if (!opened) return;
    selectedSymbol.value = props.initialSymbol || props.rows[0]?.symbol || "";
    settleDate.value = todayIso();
    interest.value = undefined;
  }
);

async function submit() {
  const row = selectedRow.value;
  if (!row?.symbol || props.ledgerId == null) {
    ElMessage.error("该行缺少账户或标的代码，无法登记回款");
    return;
  }
  if (!settleDate.value) {
    ElMessage.error("请选择回款日");
    return;
  }
  submitting.value = true;
  try {
    const res = await settleReverseRepo(props.ledgerId, {
      symbol: row.symbol,
      settle_date: settleDate.value,
      interest: interest.value ?? 0
    });
    ElMessage.success(res.message || "已登记回款");
    visible.value = false;
    emit("settled");
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "登记回款失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped lang="scss">
.settle-hint {
  margin: 2px 0 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}
</style>
