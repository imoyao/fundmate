<!--
  账户现金录入 / 修改弹窗（#3031 / G5）

  账户现金 = `assets` 里 `ledger_id = 本账户` 且 `major_category='cash'` 的那条行
  （`ledger_service.py:375-381`）。现金类既不建持仓、也不进流水，此前页面上没有任何
  入口能把它录进来 —— 五笔钱的「活钱」因此恒为空态，这才是「数据空态」的真因，
  不是 UI 缺一个空态提示。

  两条写入路径，语义必须分开：

  - **本账户还没有 cash 行** ⇒ `createAsset`，填的是「余额」（绝对值）;
  - **已有行** ⇒ `updateAsset` 的 `delta` 语义，填的是「本次变动量」。提交绝对值会
    把补录历史退化成「覆盖当前值」并平移后续曲线（`asset-value-history-design.md` §8）。

  刻意**不传 `allocation`**：现金 ⇒ 活钱是系统规则（P0-4 在入参 schema 层推导）。
  显式传会被来源混入标成 `user`，等于把系统默认值伪装成用户配置，并让它脱离后续规则接管。
-->
<template>
  <el-dialog
    v-model="visible"
    :title="cashAssetId ? '修改账户现金' : '录入账户现金'"
    width="420px"
    destroy-on-close
    :before-close="onBeforeClose"
  >
    <el-form label-width="96px">
      <el-form-item :label="cashAssetId ? '本次变动量' : '现金余额'">
        <el-input-number
          v-model="form.amount"
          :precision="2"
          :step="1000"
          class="w-full"
        />
        <p class="entry-hint">
          {{
            cashAssetId
              ? "填增减金额，负数表示减少；填 0 表示不变动"
              : "当前账户里留存的现金（银行活期、账户余额等）"
          }}
        </p>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.note" maxlength="200" placeholder="选填" />
      </el-form-item>
    </el-form>
    <template #footer>
      <!-- 程序化 close 走 requestClose：before-close 只拦关闭按钮 / ESC / 点遮罩 -->
      <el-button @click="requestClose(() => (visible = false))">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { errorMessageOf } from "@/utils/errorMessage";
import { formatDate } from "@/utils/date";
import {
  createAsset,
  getAssets,
  updateAsset,
  type AssetCreateInput
} from "@/api/assets";
import { useUnsavedChangesGuard } from "@/composables/useUnsavedChangesGuard";

defineOptions({ name: "LedgerCashEntryDialog" });

const props = defineProps<{
  modelValue: boolean;
  /** 目标账户 id；缺失时不允许保存（现金行必须挂在账户上） */
  ledgerId?: number;
  /** 当前账户现金（元），用于「变动后不能为负」的前端校验 */
  accountCash: number;
}>();

const emit = defineEmits<{
  "update:modelValue": [visible: boolean];
  /** 已写入（调用方刷新账户概览） */
  saved: [];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value)
});

const saving = ref(false);
const form = ref({ amount: 0, note: "" });
/** 本账户已有 cash 行的 id；null = 还没有（走 createAsset） */
const cashAssetId = ref<number | null>(null);
/** 一次弹窗生命周期复用同一 token：失败重试不产生第二条值变动事件 */
let clientToken = "";

function newClientToken(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** 有录入即算脏；只在用户真填了东西时才拦关闭 */
const isDirty = computed(
  () => Number(form.value.amount || 0) !== 0 || form.value.note !== ""
);

const { onBeforeClose, requestClose } = useUnsavedChangesGuard(
  () => isDirty.value,
  { message: "账户现金还没保存，确定放弃吗？" }
);

watch(
  () => props.modelValue,
  async open => {
    if (!open) return;
    form.value = { amount: 0, note: "" };
    cashAssetId.value = null;
    clientToken = newClientToken();
    try {
      // 列表接口没有 ledger_id 过滤参数（`AssetListParams`），故取回 cash 大类后在
      // 前端按 ledger_id 命中——cash 行数量极少（一账户至多一条）。
      const res = await getAssets({ major_category: "cash", per_page: 100 });
      cashAssetId.value =
        res.data?.find(a => a.ledger_id === props.ledgerId)?.id ?? null;
    } catch (e) {
      // 拿不到「有没有已有行」就不能安全保存：按「新建」处理会让用户建出第二行、
      // 账户现金被重复计入。宁可关掉弹窗，也不静默猜。
      ElMessage.error(
        errorMessageOf(e) || "账户现金状态读取失败，请刷新后重试"
      );
      visible.value = false;
    }
  },
  { immediate: true }
);

async function save() {
  const ledgerId = props.ledgerId;
  if (!ledgerId || saving.value) return;
  const value = Number(form.value.amount || 0);
  const isCreate = cashAssetId.value == null;
  if (isCreate && !(value > 0)) {
    ElMessage.warning("请填写账户现金余额（大于 0）");
    return;
  }
  if (!isCreate && value === 0) {
    ElMessage.warning("本次变动量为 0，无需保存");
    return;
  }
  if (!isCreate && props.accountCash + value < 0) {
    ElMessage.warning("变动后账户现金不能为负");
    return;
  }
  saving.value = true;
  try {
    if (isCreate) {
      const payload: AssetCreateInput = {
        major_category: "cash",
        name: "账户现金",
        amount: value,
        ledger_id: ledgerId
      };
      if (form.value.note) payload.notes = form.value.note;
      await createAsset(payload);
    } else {
      await updateAsset(cashAssetId.value as number, {
        delta: value,
        effective_date: formatDate(new Date()),
        client_token: clientToken,
        ...(form.value.note ? { change_note: form.value.note } : {})
      });
    }
    ElMessage.success(isCreate ? "账户现金已录入" : "账户现金已更新");
    visible.value = false;
    emit("saved");
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "保存失败");
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.entry-hint {
  margin: 4px 0 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}
</style>
