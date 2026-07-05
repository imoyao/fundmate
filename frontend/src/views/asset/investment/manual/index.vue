<template>
  <div
    class="manual-entry-page p-4 md:p-8 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部导航与标题 -->
    <div class="flex items-center gap-4 mb-8">
      <el-button text @click="$router.back()">
        <IconifyIconOffline icon="ep:arrow-left" class="mr-1 text-lg" /> 返回
      </el-button>
      <h2 class="text-xl font-bold" :style="{ color: 'var(--text-primary)' }">
        完整记账
      </h2>
    </div>

    <!-- 主体录入卡片 -->
    <div
      class="rounded-xl p-6 sm:p-8 max-w-3xl mx-auto flex flex-col gap-8"
      :style="{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-default)',
        boxShadow: 'var(--shadow-raised)'
      }"
    >
      <!-- ===== 模块一：账户选择区（独立通栏分组） ===== -->
      <div
        class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-lg"
        :style="{
          backgroundColor: 'var(--bg-soft)',
          border: '1px solid var(--border-default)'
        }"
      >
        <div class="flex-1 flex items-center gap-3">
          <span
            class="text-xs font-medium"
            :style="{ color: 'var(--color-danger)' }"
            >*</span
          >
          <span
            class="text-sm font-medium"
            :style="{ color: 'var(--text-secondary)' }"
            >交易账户</span
          >
          <!-- 🔥 修改 1：给顶部的下拉框加了一个 class="account-select" -->
          <el-select
            v-model="selectedLedgerId"
            class="flex-1 account-select"
            style="min-width: 200px"
            placeholder="请选择交易账户以开始记账"
            filterable
            size="large"
          >
            <el-option
              v-for="ledger in tradableLedgers"
              :key="ledger.id"
              :label="ledger.name"
              :value="ledger.id"
            >
              <div class="flex items-center justify-between w-full">
                <span>{{ ledger.name }}</span>
                <el-tag
                  size="small"
                  round
                  class="px-1.5 py-0.5"
                  :style="{
                    backgroundColor: bgFromColor(
                      getLedgerColor(ledger.ledger_type)
                    ),
                    color: getLedgerColor(ledger.ledger_type)
                  }"
                >
                  {{
                    LEDGER_TYPE_SHORT[ledger.ledger_type] || ledger.ledger_type
                  }}
                </el-tag>
              </div>
            </el-option>
          </el-select>
        </div>

        <!-- 快捷创建按钮（非卖出/赎回/转换时显示） -->
        <el-button
          v-if="!showQuickAdd && !isSellLike && fundOpType !== 'convert'"
          type="primary"
          text
          size="small"
          @click="showQuickAdd = true"
        >
          <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新建账户
        </el-button>
      </div>

      <!-- 极简创建账户的折叠面板 -->
      <div
        v-if="showQuickAdd"
        class="mt-2 p-3 border rounded-lg transition-all"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <el-input
          v-model="newAccountName"
          placeholder="输入账户名称，如：华泰证券"
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

      <!-- ===== 模块二：操作类型切换 ===== -->
      <div v-if="selectedLedgerId">
        <div
          class="flex flex-wrap gap-1 p-1 rounded-lg"
          :style="{ backgroundColor: 'var(--bg-soft)' }"
        >
          <!-- 股票操作组 -->
          <template v-if="currentLedgerType === 'stock'">
            <el-radio-group
              v-model="stockOpType"
              size="default"
              class="flex-1 flex"
            >
              <el-radio-button label="buy" class="flex-1">
                <span class="px-4 py-1.5 block text-center">买入</span>
              </el-radio-button>
              <el-radio-button label="sell" class="flex-1">
                <span class="px-4 py-1.5 block text-center">卖出</span>
              </el-radio-button>
              <el-radio-button label="dividend" class="flex-1">
                <span class="px-4 py-1.5 block text-center">现金分红</span>
              </el-radio-button>
            </el-radio-group>
          </template>
          <!-- 基金操作组 -->
          <template v-else-if="['fund', 'bank'].includes(currentLedgerType)">
            <el-radio-group
              v-model="fundOpType"
              size="default"
              class="flex-1 flex"
            >
              <el-radio-button label="subscribe" class="flex-1">
                <span class="px-4 py-1.5 block text-center">申购</span>
              </el-radio-button>
              <el-radio-button label="redeem" class="flex-1">
                <span class="px-4 py-1.5 block text-center">赎回</span>
              </el-radio-button>
              <el-radio-button label="dividend_reinvest" class="flex-1">
                <span class="px-4 py-1.5 block text-center">红利再投</span>
              </el-radio-button>
              <el-radio-button label="convert" class="flex-1">
                <span class="px-4 py-1.5 block text-center">转换</span>
              </el-radio-button>
              <el-radio-button label="drip" class="flex-1">
                <span class="px-4 py-1.5 block text-center">定投</span>
              </el-radio-button>
            </el-radio-group>
          </template>
        </div>
      </div>

      <!-- ===== 模块三：动态表单 ===== -->
      <div
        v-if="!selectedLedgerId"
        class="py-12 text-center border-2 border-dashed rounded-xl"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <IconifyIconOffline
          icon="ep:pointer"
          class="text-4xl mb-3"
          :style="{ color: 'var(--text-tertiary)' }"
        />
        <p
          class="text-base font-medium"
          :style="{ color: 'var(--text-primary)' }"
        >
          请先选择上方交易账户
        </p>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
          我们将根据账户类型自动匹配可用的记账操作
        </p>
      </div>

      <div v-else class="flex flex-col gap-6">
        <!-- 证券买入 -->
        <BuyForm
          v-if="
            (currentLedgerType === 'stock' && stockOpType === 'buy') ||
            (['fund', 'bank'].includes(currentLedgerType) &&
              (fundOpType === 'subscribe' || fundOpType === 'drip'))
          "
          ref="buyFormRef"
          :ledgers="ledgers"
          :hide-account-select="true"
          :default-ledger-id="selectedLedgerId"
          :extra="fundOpType === 'drip' ? { reason: 'drip' } : undefined"
          @submit-success="onSubmitSuccess"
          @accounts-changed="loadLedgers"
        />
        <!-- 证券卖出 / 基金赎回 -->
        <SellForm
          v-else-if="
            (currentLedgerType === 'stock' && stockOpType === 'sell') ||
            (['fund', 'bank'].includes(currentLedgerType) &&
              fundOpType === 'redeem')
          "
          ref="sellFormRef"
          :ledgers="ledgers"
          :hide-account-select="true"
          :default-ledger-id="selectedLedgerId"
          @submit-success="onSubmitSuccess"
          @positions-loaded="sellableLedgerIds = $event"
        />
        <!-- 未实现功能占位 -->
        <div
          v-else
          class="py-8 text-center"
          :style="{ color: 'var(--text-tertiary)' }"
        >
          <IconifyIconOffline icon="ep:box" class="text-4xl mb-2" />
          <p>{{ getFundOpLabel(fundOpType) }} 功能开发中</p>
        </div>
      </div>

      <!-- ===== 模块四：底部操作区 ===== -->
      <div
        v-if="selectedLedgerId"
        class="pt-4 border-t flex justify-end gap-3"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <el-button class="action-btn" @click="$router.back()">取消</el-button>
        <el-button
          class="action-btn"
          type="primary"
          :loading="submitting"
          @click="handleGlobalSubmit"
        >
          确认记账
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getLedgers, createLedger as createLedgerApi } from "@/api/ledger";
import { LEDGER_TYPE_SHORT, LEDGER_TYPE_OPTIONS } from "@/constants";
import { getLedgerColor, bgFromColor } from "@/utils/ledger";
import BuyForm from "@/components/QuickEntry/BuyForm.vue";
import SellForm from "@/components/QuickEntry/SellForm.vue";

defineOptions({ name: "ManualEntry" });

const router = useRouter();

// --- 状态 ---
const selectedLedgerId = ref<number | null>(null);
const ledgers = ref<any[]>([]);
const showQuickAdd = ref(false);
const newAccountName = ref("");
const newAccountType = ref("");
const creatingAccount = ref(false);
const quickAddTypeOptions = LEDGER_TYPE_OPTIONS.filter(
  opt => opt.value !== "property"
);

const currentLedgerType = computed(() => {
  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  return ledger?.ledger_type || null;
});

// 新增状态
const sellableLedgerIds = ref<number[]>([]);

// 修改 tradableLedgers
const tradableLedgers = computed(() => {
  let list = ledgers.value.filter(l => l.ledger_type !== "property");
  // 卖出/赎回/转换时，只显示有持仓的账户（通过 ledger_id 匹配）
  if (isSellLike.value || fundOpType.value === "convert") {
    return list.filter(l => sellableLedgerIds.value.includes(l.id));
  }
  return list;
});

// 判断当前是否处于卖出/赎回状态（此状态下不应该允许新建账户）
const isSellLike = computed(() => {
  if (currentLedgerType.value === "stock") {
    return stockOpType.value === "sell";
  }
  if (
    currentLedgerType.value === "fund" ||
    currentLedgerType.value === "bank"
  ) {
    return fundOpType.value === "redeem";
  }
  return false;
});

const stockOpType = ref<"buy" | "sell" | "dividend">("buy");
const fundOpType = ref<
  "subscribe" | "redeem" | "dividend_reinvest" | "convert" | "drip"
>("subscribe");

const submitting = ref(false);

const buyFormRef = ref<InstanceType<typeof BuyForm>>();
const sellFormRef = ref<InstanceType<typeof SellForm>>();

// --- 工具方法 ---
const getFundOpLabel = (type: string) => {
  const map: Record<string, string> = {
    dividend_reinvest: "红利再投",
    convert: "转换",
    drip: "定投"
  };
  return map[type] || type;
};

// 只在首次选择账户时设置默认操作类型，之后切换账户保持原操作不变
watch(selectedLedgerId, (newVal, oldVal) => {
  if (oldVal == null && newVal != null) {
    stockOpType.value = "buy";
    fundOpType.value = "subscribe";
  }
});

async function quickCreateAccount() {
  const name = newAccountName.value.trim();
  const type = newAccountType.value;
  if (!name || !type) return;

  creatingAccount.value = true;
  try {
    let feeConfig: any = undefined;
    if (type === "fund") feeConfig = { subscription_discount: 0.1 };
    else if (type === "stock")
      feeConfig = { commission: { rate: 0.00025, min: null } };

    const payload: any = { name, ledger_type: type };
    if (feeConfig) payload.fee_config = feeConfig;

    const res = await createLedgerApi(payload);
    const newLedger = (res as any)?.data ?? res;

    await loadLedgers();
    selectedLedgerId.value = newLedger.id;
    resetQuickAdd();
    ElMessage.success(`已创建账户「${newLedger.name}」并自动选中`);
  } catch (e: any) {
    ElMessage.error(e?.message || "创建账户失败");
  } finally {
    creatingAccount.value = false;
  }
}

function resetQuickAdd() {
  showQuickAdd.value = false;
  newAccountName.value = "";
  newAccountType.value = "";
}

async function loadLedgers() {
  try {
    const res = await getLedgers();
    let data = (res as any)?.data;
    if (data && typeof data === "object" && !Array.isArray(data)) {
      data = data.data ?? data;
    }
    ledgers.value = Array.isArray(data) ? data : [];
  } catch {
    ledgers.value = [];
  }
}

async function handleGlobalSubmit() {
  submitting.value = true;
  try {
    const type = currentLedgerType.value;
    if (type === "stock") {
      if (stockOpType.value === "buy") await buyFormRef.value?.handleSubmit();
      else if (stockOpType.value === "sell")
        await sellFormRef.value?.handleSubmit();
      else ElMessage.info("分红功能开发中");
    } else if (type === "fund" || type === "bank") {
      if (fundOpType.value === "subscribe")
        await buyFormRef.value?.handleSubmit();
      else if (fundOpType.value === "redeem")
        await sellFormRef.value?.handleSubmit();
      else ElMessage.info("该功能开发中");
    }
  } finally {
    submitting.value = false;
  }
}

// 替换 ManualEntry.vue 里面的 onSubmitSuccess
function onSubmitSuccess() {
  ElMessageBox.confirm("交易记录已成功保存！", "记账成功", {
    confirmButtonText: "继续记录下一笔",
    cancelButtonText: "返回查看持仓",
    distinguishCancelAndClose: true,
    type: "success"
  })
    .then(() => {
      // ✅ 点击【继续记录下一笔】：调用子组件的 resetForm 清空数据
      // 因为父组件的 selectedLedgerId 依然通过 props 往下传，子组件重置后会自动恢复当前选中的账户！
      buyFormRef.value?.resetForm();
      sellFormRef.value?.resetForm();
      ElMessage.success("已重置，请继续录入");
    })
    .catch((action: any) => {
      if (action === "cancel") {
        // ✅ 点击【返回查看持仓】：跳回上一页
        router.back();
      }
    });
}

onMounted(() => {
  loadLedgers();
  document.body.classList.add("hide-global-fab");
});

onBeforeUnmount(() => {
  document.body.classList.remove("hide-global-fab");
});

// 清空卖出账户缓存（当不再是卖出/转换类操作时）
watch([stockOpType, fundOpType], () => {
  if (!isSellLike.value && fundOpType.value !== "convert") {
    sellableLedgerIds.value = [];
  }
});
</script>

<style scoped>
.manual-entry-page {
  font-family: var(
    --font-sans,
    "PingFang SC",
    "Hiragino Sans GB",
    "Microsoft YaHei",
    sans-serif
  );
}

/* 🔥 隐藏右下角全局 FAB */
.hide-global-fab .global-fab,
.hide-global-fab .back-to-top {
  display: none !important;
}

/* 🔥 单选按钮组：克制、优雅的 Segmented Control + 果冻回弹动画 */
:deep(.el-radio-button__inner) {
  border: none !important;
  background: transparent !important;
  border-radius: 6px;
  /* 核心动画配置 */
  transform: translateZ(0);
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    background-color 0.2s,
    color 0.2s,
    box-shadow 0.2s;
  will-change: transform;
  transform-origin: center;
  color: var(--text-tertiary);
  font-weight: 500;
  box-shadow: none !important;
}

/* 按下时的收缩反馈 */
:deep(.el-radio-button__inner:active) {
  transform: scale(0.92) !important;
}

/* 选中状态时的果冻回弹动画 */
:deep(.el-radio-button.is-active .el-radio-button__inner) {
  background: #fff !important;
  color: var(--color-danger) !important;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06) !important;
  animation: button-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Hover 状态 */
:deep(.el-radio-button__inner:hover) {
  color: var(--text-primary);
}
:deep(.el-radio-button.is-active .el-radio-button__inner:hover) {
  color: var(--color-danger) !important;
}

/* 🔥 果冻回弹关键帧 */
@keyframes button-pop {
  0% {
    transform: scale(1);
  }
  30% {
    transform: scale(0.9);
  }
  60% {
    transform: scale(1.06);
  }
  80% {
    transform: scale(0.96);
  }
  100% {
    transform: scale(1);
  }
}

/* 🔥 底部按钮物理反馈 */
.action-btn {
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.15s;
}
.action-btn:active {
  transform: translateY(1px) scale(0.96);
  box-shadow: none !important;
}

/* 🔥 修复：删除影响全局下拉框的样式，只对最顶层的交易账户生效 */
:deep(.account-select .el-select__wrapper) {
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 12px 0 0 !important;
}
:deep(.account-select .el-select__selected-item) {
  font-weight: 500;
}
</style>
