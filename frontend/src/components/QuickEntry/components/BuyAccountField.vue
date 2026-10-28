<template>
  <!-- 账户选择（可被外部隐藏）：下拉按「最近使用」置顶 + 行内极简新建账户。
       #980 拆分自 BuyForm.vue，新建账户状态全部留在本组件内，父层只收 ledger_id。 -->
  <el-form-item label="选择账户" prop="ledger_id">
    <div class="flex gap-2 w-full">
      <el-select
        v-model="ledgerModel"
        class="flex-1"
        style="width: 100%"
        placeholder="选择交易账户"
        filterable
        :disabled="showQuickAdd"
        @change="onAccountSelected"
      >
        <el-option
          v-for="ledger in selectableLedgers"
          :key="ledger.id"
          :label="ledger.name"
          :value="ledger.id"
        >
          <div class="flex items-center justify-between w-full">
            <span>{{ ledger.name }}</span>
            <AssetTypeBadge
              :channel-category="ledger.channel_category"
              variant="tag"
            />
          </div>
        </el-option>
      </el-select>
      <el-button
        v-if="!showQuickAdd"
        aria-label="新建账户"
        type="primary"
        class="account-create-btn"
        @click="showQuickAdd = true"
      >
        <IconifyIconOffline icon="ep:plus" />
      </el-button>
    </div>

    <div
      v-if="selectableLedgers.length === 0 && !showQuickAdd"
      class="text-xs mt-1"
      style="color: var(--text-tertiary-ink)"
    >
      暂无账户，点击右侧 + 按钮快速创建
    </div>

    <!-- 极简创建账户 -->
    <div
      v-if="showQuickAdd"
      class="quick-add-account mt-3 p-3 border rounded-lg bg-gray-50"
      style="border-color: var(--border-default)"
    >
      <el-input
        v-model="newAccountName"
        placeholder="输入账户名称"
        size="small"
        @keyup.enter="quickCreateAccount"
      />
      <el-select
        v-model="newAccountType"
        class="w-full mt-2"
        size="small"
        placeholder="选择账户类型"
      >
        <el-option
          v-for="opt in quickAddTypeOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <div class="flex justify-end gap-2 mt-2">
        <el-button size="small" @click="resetQuickAdd">取消</el-button>
        <el-button
          size="small"
          type="primary"
          :loading="creatingAccount"
          :disabled="!newAccountName.trim() || !newAccountType"
          @click="quickCreateAccount"
        >
          创建并选择
        </el-button>
      </div>
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { createLedger as createLedgerApi, type LedgerItem } from "@/api/ledger";
import { IconifyIconOffline } from "@/components/ReIcon";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { LEDGER_TYPE_OPTIONS } from "@/constants";
import {
  loadRecentLedgerIds,
  sortByRecentUsage
} from "@/components/QuickEntry/buyRecentLedgers";

const props = defineProps<{
  ledgers: LedgerItem[];
  /** 选中的账户 id */
  modelValue: number | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: number | null];
  /** 账户切换：父层据此重算手续费预设 */
  change: [];
  /** 新建账户成功：父层需重新拉账户列表 */
  "accounts-changed": [];
}>();

const ledgerModel = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

// 最近使用账户置顶（#2305）：列表只在 setup 读一次（历史行为，改动会让提交后的
// 排序在同一挂载周期里突然跳变）
const recentLedgerIds = loadRecentLedgerIds();
const selectableLedgers = computed(() =>
  sortByRecentUsage(
    props.ledgers.filter(l => l.ledger_type !== "property"),
    recentLedgerIds
  )
);

// 极简账户创建
const showQuickAdd = ref(false);
const newAccountName = ref("");
const newAccountType = ref("");
const creatingAccount = ref(false);
const quickAddTypeOptions = LEDGER_TYPE_OPTIONS.filter(
  opt => opt.value !== "other"
);

function onAccountSelected() {
  emit("change");
}

async function quickCreateAccount() {
  const name = newAccountName.value.trim();
  const type = newAccountType.value;
  if (!name || !type) return;
  creatingAccount.value = true;
  try {
    let feeConfig:
      | {
          subscription_discount?: number;
          commission?: { rate: number; min: number | null };
        }
      | undefined = undefined;
    if (type === "fund") feeConfig = { subscription_discount: 0.1 };
    else if (type === "stock")
      feeConfig = { commission: { rate: 0.00025, min: null } };
    const payload: {
      name: string;
      ledger_type: string;
      fee_config?: Record<string, unknown> | null;
    } = { name, ledger_type: type };
    if (feeConfig) payload.fee_config = feeConfig as Record<string, unknown>;
    await createLedgerApi(payload);
    emit("accounts-changed");
    ElMessage.success(`已创建账户「${name}」`);
    resetQuickAdd();
  } catch (e) {
    const err = e as {
      response?: { data?: { message?: string } };
      message?: string;
    };
    ElMessage.error(err.message || "创建账户失败");
  } finally {
    creatingAccount.value = false;
  }
}

function resetQuickAdd() {
  showQuickAdd.value = false;
  newAccountName.value = "";
  newAccountType.value = "";
}
</script>

<style scoped>
/* 新建账户：次按钮语义（辅助操作，不抢主视觉），对齐 design.md 按钮规范 */
.account-create-btn {
  flex-shrink: 0;
  gap: 4px;
  height: 40px;
  padding: 0 16px;
  color: var(--text-primary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  transition:
    background-color 150ms ease,
    border-color 150ms ease;
}

.account-create-btn:hover {
  background-color: var(--bg-hover);
  border-color: var(--border-light);
}

.account-create-btn :deep(.el-icon) {
  margin-right: 0;
}
</style>
