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
                <AssetTypeBadge :type="ledger.ledger_type" variant="tag" />
              </div>
            </el-option>
          </el-select>
        </div>

        <!-- 快捷创建按钮（非卖出/赎回/转换时显示）
             次按钮语义：不用 `type="primary" text`——theme.scss 把主按钮文字色定为
             --text-inverse（白），text 变体又是透明底，白字透明底＝整颗按钮隐身。 -->
        <el-button
          v-if="!showQuickAdd && !isSellLike && fundOpType !== 'convert'"
          class="account-create-btn"
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

      <!-- ===== 模块二：操作类型切换 =====
           语义 = 表单取值（`role="radiogroup"`），按 design.md 归「D13 果冻胶囊」：
           每项一颗独立胶囊（透明底 + 1px 描边），选中态 brand-100 底 / brand-400 描边 /
           brand-700 字 + 弹性回弹。**不是** iOS 那种「软底轨道 + 白色滑块」的分段控制器——
           那套语言归 SegmentedControl（Tab 语义，切换的是「看什么」），两者不可互替。
           基金组有 6 项，故用 wrap 平铺而不是等分 flex-1：等分到 6 列时
           「红利再投 / 送股拆分」会被压成两行字。 -->
      <div v-if="selectedLedgerId">
        <el-radio-group
          v-if="currentLedgerType === 'stock'"
          v-model="stockOpType"
          class="op-switch"
          aria-label="操作类型"
        >
          <el-radio-button label="buy">买入</el-radio-button>
          <el-radio-button label="sell">卖出</el-radio-button>
          <el-radio-button label="dividend">现金分红</el-radio-button>
          <el-radio-button label="split">送股/拆分</el-radio-button>
        </el-radio-group>
        <el-radio-group
          v-else-if="['fund', 'bank'].includes(currentLedgerType)"
          v-model="fundOpType"
          class="op-switch"
          aria-label="操作类型"
        >
          <el-radio-button label="subscribe">申购</el-radio-button>
          <el-radio-button label="redeem">赎回</el-radio-button>
          <el-radio-button label="dividend_reinvest">红利再投</el-radio-button>
          <el-radio-button label="split">送股/拆分</el-radio-button>
          <el-radio-button label="convert">转换</el-radio-button>
          <el-radio-button label="drip">定投</el-radio-button>
        </el-radio-group>
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
          :style="{ color: 'var(--text-tertiary-ink)' }"
        />
        <p
          class="text-base font-medium"
          :style="{ color: 'var(--text-primary)' }"
        >
          请先从上方选择交易账户
        </p>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary-ink)' }">
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
        <!-- 分红 / 红利再投 / 送股拆分 -->
        <DividendForm
          v-else-if="isDividendLike || isSplit"
          ref="dividendFormRef"
          :ledgers="ledgers"
          :hide-account-select="true"
          :default-ledger-id="selectedLedgerId"
          :mode="
            isSplit
              ? 'split'
              : stockOpType === 'dividend'
                ? 'dividend'
                : 'dividend_reinvest'
          "
          @submit-success="onSubmitSuccess"
        />
        <!-- 未实现功能占位 -->
        <div
          v-else
          class="py-8 text-center"
          :style="{ color: 'var(--text-tertiary-ink)' }"
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
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import BuyForm from "@/components/QuickEntry/BuyForm.vue";
import SellForm from "@/components/QuickEntry/SellForm.vue";
import DividendForm from "./DividendForm.vue";
import { createLedger } from "@/api/ledger";
import {
  useQuickEntry,
  useQuickEntrySubmit
} from "@/composables/useQuickEntry";
import { useUnsavedChangesGuard } from "@/composables/useUnsavedChangesGuard";
import { LEDGER_TYPE_OPTIONS } from "@/constants";

defineOptions({ name: "ManualEntry" });

const router = useRouter();

// ── composables ──
const { ledgers, loadLedgers } = useQuickEntry({ autoLoad: true });

// ── 本地状态 ──
const selectedLedgerId = ref<number | null>(null);
const showQuickAdd = ref(false);
const newAccountName = ref("");
const newAccountType = ref("");
const creatingAccount = ref(false);
const quickAddTypeOptions = LEDGER_TYPE_OPTIONS.filter(
  opt => opt.value !== "other"
);

const currentLedgerType = computed(() => {
  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  return ledger?.ledger_type || null;
});

const sellableLedgerIds = ref<number[]>([]);

const tradableLedgers = computed(() => {
  let list = ledgers.value.filter(l => l.ledger_type !== "property");
  if (isSellLike.value || fundOpType.value === "convert") {
    return list.filter(l => sellableLedgerIds.value.includes(l.id));
  }
  return list;
});

const isSellLike = computed(() => {
  if (currentLedgerType.value === "stock") return stockOpType.value === "sell";
  if (currentLedgerType.value === "fund" || currentLedgerType.value === "bank")
    return fundOpType.value === "redeem";
  return false;
});

// 原始值。真正的 opType 是下面两个 computed——直接改 ref 会绕过守卫。
const stockOpTypeRaw = ref<"buy" | "sell" | "dividend" | "split">("buy");
const fundOpTypeRaw = ref<
  "subscribe" | "redeem" | "dividend_reinvest" | "convert" | "drip" | "split"
>("subscribe");

const buyFormRef = ref<InstanceType<typeof BuyForm>>();
const sellFormRef = ref<InstanceType<typeof SellForm>>();
const dividendFormRef = ref<InstanceType<typeof DividendForm>>();

// ── 未保存离开保护（#1891）──
// 本页三个表单各自填到一半时切走，数据会静默丢失且无任何提示。
// BuyForm / SellForm 自带 isDirty，但此前**只有 TransactionDrawer 在读**——
// 浮动快速录入那条路有保护，而手动记账页（更常填、更容易丢）整块漏掉了。
// DividendForm 连 isDirty 都没有，本次一并补上（见该组件内注释）。
//
// 三个表单是 v-if / v-else-if / v-else-if 互斥渲染，同时最多挂一个，
// 所以 || 组合是安全的：未挂载的那两个 ref 为 undefined，判定落到 false。
const isFormDirty = computed(
  () =>
    buyFormRef.value?.isDirty === true ||
    sellFormRef.value?.isDirty === true ||
    dividendFormRef.value?.isDirty === true
);

// 守卫内部自己注册 onBeforeRouteLeave，调用方无需接线；
// `confirmDiscard` 要解构出来给「切换操作类型」用（第二步）——它不是路由离开，
// onBeforeRouteLeave 拦不住 v-if 销毁表单。
const { confirmDiscard } = useUnsavedChangesGuard(() => isFormDirty.value, {
  message: "记账表单已填写，确定放弃吗？"
});

// ── 切换操作类型也要问一次（#1891 第二步）──
// 三个表单靠 v-if / v-else-if 互斥渲染，切 opType 会**直接销毁**已填的那个。
// 这不是路由离开，onBeforeRouteLeave 拦不住——上一轮只补了页面守卫，
// 用户「点一下卖出标签想看看怎么填」就会丢掉填好的买入表单。
//
// 改法：opType 由 computed setter 转发，setter 里先问一次，放弃才真正写值。
// 模板的 v-model 不用改，computed setter 对它是透明的。
//
// UI 回弹：el-radio-group 完全受控于 v-model，setter 拒绝时值没变，选中态自动回到
// 原项。**这一条没做浏览器复核**，若 Element Plus 版本行为不同，需要在 radio-group
// 上加 :key 强制重渲染。
/** 确认框在途：防止连点弹多个框，也防止两次切换交叉写值 */
const opTypeSwitching = ref(false);

async function switchOpType(next: string, apply: () => void) {
  if (opTypeSwitching.value) return;
  if (!isFormDirty.value) {
    apply();
    return;
  }
  opTypeSwitching.value = true;
  try {
    if (await confirmDiscard()) apply();
  } finally {
    opTypeSwitching.value = false;
  }
}

const stockOpType = computed({
  get: () => stockOpTypeRaw.value,
  set: (v: typeof stockOpTypeRaw.value) => {
    if (v === stockOpTypeRaw.value) return;
    void switchOpType(v, () => {
      stockOpTypeRaw.value = v;
    });
  }
});

const fundOpType = computed({
  get: () => fundOpTypeRaw.value,
  set: (v: typeof fundOpTypeRaw.value) => {
    if (v === fundOpTypeRaw.value) return;
    void switchOpType(v, () => {
      fundOpTypeRaw.value = v;
    });
  }
});

// 分红/红利再投：复用同一表单，按操作类型切换子模式
const isDividendLike = computed(() => {
  if (currentLedgerType.value === "stock")
    return stockOpType.value === "dividend";
  if (["fund", "bank"].includes(currentLedgerType.value || ""))
    return fundOpType.value === "dividend_reinvest";
  return false;
});

// 送股/拆分：复用分红表单（选持仓 + 份额），按操作类型切换子模式
const isSplit = computed(() => {
  if (currentLedgerType.value === "stock") return stockOpType.value === "split";
  if (["fund", "bank"].includes(currentLedgerType.value || ""))
    return fundOpType.value === "split";
  return false;
});

const opTypeComputed = computed(() => {
  if (isDividendLike.value || isSplit.value) return "dividend";
  return stockOpType.value === "sell" || fundOpType.value === "redeem"
    ? "sell"
    : "buy";
});
const {
  submitting,
  handleSubmit: coreHandleSubmit,
  resetForms
} = useQuickEntrySubmit(
  opTypeComputed,
  buyFormRef,
  sellFormRef,
  dividendFormRef
);

// ── 方法 ──
const getFundOpLabel = (type: string) => {
  const map: Record<string, string> = {
    dividend_reinvest: "红利再投",
    split: "送股/拆分",
    convert: "转换",
    drip: "定投"
  };
  return map[type] || type;
};

watch(selectedLedgerId, (newVal, oldVal) => {
  if (oldVal == null && newVal != null) {
    // 走 raw 而非 computed：这是首次选定账户后的**初始化**，不是用户主动切换操作类型。
    // 走 computed 会在极端时序下（表单刚挂载就被判脏）弹一个莫名其妙的确认框。
    stockOpTypeRaw.value = "buy";
    fundOpTypeRaw.value = "subscribe";
  }
});

/**
 * 新建账户（账户栏右上角「新建账户」的极简通道）。
 *
 * 只收两项：名称 + 渠道分组。提交时必须下发 `channel_category`——后端据它派生
 * `ledger_type`（#1101）。历史上这里把分组值塞进 `ledger_type` 提交，派生链
 * 落到 `map_ledger_type_to_channel_category('fund_platform')`，建出来的账户
 * 渠道分组为空、账本类型也错。
 *
 * 需要类现金绑定 / 组合 / 销售机构等完整字段时走账户页的 `CreateAccountDialog`，
 * 这里刻意保持极简，不复制第二套建账表单。
 */
async function quickCreateAccount() {
  const name = newAccountName.value.trim();
  const channel = newAccountType.value;
  if (!name || !channel) return;

  creatingAccount.value = true;
  try {
    const payload: {
      name: string;
      channel_category: string;
      fee_config?: Record<string, unknown>;
    } = { name, channel_category: channel };
    // 与账户页一致的费率初值：场外基金申购费 1 折，证券佣金万 2.5（免五）
    if (channel === "fund_platform")
      payload.fee_config = { subscription_discount: 0.1 };
    else if (channel === "securities")
      payload.fee_config = { commission: { rate: 0.00025, min: null } };

    const res = await createLedger(payload);
    const newLedger = (res as any)?.data ?? res;
    await loadLedgers();
    if (newLedger?.id) {
      selectedLedgerId.value = newLedger.id;
      resetQuickAdd();
      ElMessage.success(`已创建账户「${newLedger.name || name}」并自动选中`);
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || e?.message || "创建账户失败");
  } finally {
    creatingAccount.value = false;
  }
}

function resetQuickAdd() {
  showQuickAdd.value = false;
  newAccountName.value = "";
  newAccountType.value = "";
}

async function handleGlobalSubmit() {
  await coreHandleSubmit();
}

function onSubmitSuccess() {
  ElMessageBox.confirm("交易记录已成功保存！", "记账成功", {
    confirmButtonText: "继续记录下一笔",
    cancelButtonText: "返回查看持仓",
    distinguishCancelAndClose: true,
    type: "success"
  })
    .then(() => {
      buyFormRef.value?.resetForm();
      sellFormRef.value?.resetForm();
      dividendFormRef.value?.resetForm();
      ElMessage.success("已重置，请继续录入");
    })
    .catch((action: any) => {
      if (action === "cancel") router.back();
    });
}

// ── 生命周期 ──
watch([stockOpType, fundOpType], () => {
  if (!isSellLike.value && fundOpType.value !== "convert") {
    sellableLedgerIds.value = [];
  }
});
</script>

<style scoped>
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

.manual-entry-page {
  font-family: var(
    --font-sans,
    "PingFang SC",
    "Hiragino Sans GB",
    "Microsoft YaHei",
    sans-serif
  );
}

/* ── 操作类型：D13 果冻胶囊（每项一颗独立胶囊，可换行；不做等分轨道） ── */
.op-switch {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.op-switch :deep(.el-radio-button) {
  flex: 0 0 auto;
}

.op-switch :deep(.el-radio-button__inner) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 74px;
  height: 34px;
  padding: 0 16px;
  font-size: var(--text-label);
  font-weight: 500;
  line-height: 1;
  color: var(--text-secondary);
  background: transparent !important;
  border: 1px solid var(--border-default) !important;
  border-radius: var(--radius-pill) !important;
  box-shadow: none !important;

  /* 果冻回弹：只在 transform 上弹，颜色过渡用线性缓动 */
  transform: translateZ(0);
  transform-origin: center;
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;
  will-change: transform;
}

/* Hover：描边提到品牌色，文字提到主色 */
.op-switch :deep(.el-radio-button__inner:hover) {
  color: var(--text-primary);
  border-color: var(--brand-400) !important;
}

/* 按下时的收缩反馈 */
.op-switch :deep(.el-radio-button__inner:active) {
  transform: scale(0.92) !important;
}

/* 选中：软按钮（brand-100 底 + brand-400 描边 + brand-700 字）+ 果冻回弹 */
.op-switch :deep(.el-radio-button.is-active .el-radio-button__inner) {
  color: var(--brand-700) !important;
  background: var(--brand-100) !important;
  border-color: var(--brand-400) !important;
  box-shadow: none !important;
  animation: button-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.op-switch :deep(.el-radio-button.is-active .el-radio-button__inner:hover) {
  color: var(--brand-700) !important;
  background: var(--brand-200) !important;
}

/* 键盘可达性：EP 把原生 radio 藏在视觉层下，焦点环要补到可视元素上 */
.op-switch
  :deep(
    .el-radio-button__original-radio:focus-visible + .el-radio-button__inner
  ) {
  box-shadow: var(--focus-ring) !important;
  outline: none;
}

/* 账户栏「新建账户」：次按钮（描边 + 卡片底），不能与主按钮抢焦点 */
.account-create-btn {
  flex-shrink: 0;
  height: 32px;
  padding: 0 12px;
  color: var(--text-primary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  transition:
    background-color 150ms ease,
    border-color 150ms ease,
    color 150ms ease;
}

.account-create-btn:hover {
  color: var(--brand-ink);
  background-color: var(--bg-hover);
  border-color: var(--brand-400);
}

/* 🔥 底部按钮物理反馈 */
.action-btn {
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.15s;
}

.action-btn:active {
  box-shadow: none !important;
  transform: translateY(1px) scale(0.96);
}

/* 🔥 修复：删除影响全局下拉框的样式，只对最顶层的交易账户生效 */
:deep(.account-select .el-select__wrapper) {
  padding: 0 12px 0 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

:deep(.account-select .el-select__selected-item) {
  font-weight: 500;
}

:deep(.el-button--primary) {
  height: 40px;
}
</style>
