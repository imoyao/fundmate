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

    <!-- 主体录入卡片：转换是唯一的两栏表单，768px 装两栏会把转入侧压到 279px
         （实测 #2348），所以转换时放开到 1024px；其余表单是单列，维持 768px。 -->
    <div
      class="rounded-xl p-6 sm:p-8 mx-auto flex flex-col gap-8"
      :class="fundOpType === 'convert' ? 'max-w-5xl' : 'max-w-3xl'"
      :style="{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-default)',
        boxShadow: 'var(--shadow-raised)'
      }"
    >
      <!-- ===== 模块一：账户选择区 → ManualAccountBar ===== -->
      <ManualAccountBar
        v-model:selected-ledger-id="selectedLedgerId"
        :options="tradableLedgers"
        :can-create="!isSellLike && fundOpType !== 'convert'"
        @reload="loadLedgers"
      />

      <!-- ===== 模块二：操作类型切换 → ManualOpSwitch ===== -->
      <ManualOpSwitch
        v-if="selectedLedgerId"
        v-model:stock-op-type="stockOpType"
        v-model:fund-op-type="fundOpType"
        :ledger-type="currentLedgerType"
      />

      <!-- ===== 模块三：动态表单 ===== -->
      <ManualEntryEmpty v-if="!selectedLedgerId" />

      <div v-else class="flex flex-col gap-6">
        <!-- 证券买入 -->
        <BuyForm
          v-if="
            (currentLedgerType === 'stock' && stockOpType === 'buy') ||
            (isFundLike(currentLedgerType) &&
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
            (isFundLike(currentLedgerType) && fundOpType === 'redeem')
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
          :mode="dividendMode"
          @submit-success="onSubmitSuccess"
        />
        <!-- 基金转换：三步向导 + 回执页（设计 docs/working-notes/fund-conversion-design-2026-10-17.md §6） -->
        <ConversionForm
          v-else-if="fundOpType === 'convert'"
          ref="conversionFormRef"
          :ledgers="ledgers"
          :default-ledger-id="selectedLedgerId"
          @done="onConversionDone"
          @positions-loaded="sellableLedgerIds = $event"
        />
        <!-- 未实现功能占位（当前仅防御性兜底：股票/基金操作均已分支覆盖） -->
        <div
          v-else
          class="py-8 text-center"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          <IconifyIconOffline icon="ep:box" class="text-4xl mb-2" />
          <p>{{ getFundOpLabel(fundOpType) }} 功能开发中</p>
        </div>
      </div>

      <!-- ===== 模块四：底部操作区 → ManualActionBar =====
           转换不走全局「确认记账」：它的提交发生在步骤条第 3 步（确认转换），
           且第 4 步是结果页——全局按钮在那里没有可提交的对象，故整条隐藏。 -->
      <ManualActionBar
        v-if="selectedLedgerId && fundOpType !== 'convert'"
        :submitting="submitting"
        @cancel="router.back()"
        @submit="handleGlobalSubmit"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import BuyForm from "@/components/QuickEntry/BuyForm.vue";
import SellForm from "@/components/QuickEntry/SellForm.vue";
import DividendForm from "./DividendForm.vue";
import ConversionForm from "./ConversionForm.vue";
import ManualAccountBar from "./manualView/ManualAccountBar.vue";
import ManualOpSwitch from "./manualView/ManualOpSwitch.vue";
import ManualEntryEmpty from "./manualView/ManualEntryEmpty.vue";
import ManualActionBar from "./manualView/ManualActionBar.vue";
import {
  useQuickEntry,
  useQuickEntrySubmit
} from "@/composables/useQuickEntry";
import { useUnsavedChangesGuard } from "@/composables/useUnsavedChangesGuard";
import {
  dividendModeOf,
  getFundOpLabel,
  isDividendLikeOf,
  isFundLike,
  isSellLikeOf,
  isSplitOf,
  submitOpTypeOf
} from "./manualView/manualEntryModel";
import type { FundOpType, StockOpType } from "./manualView/manualEntryModel";

defineOptions({ name: "ManualEntry" });

const router = useRouter();

// ── composables ──
const { ledgers, loadLedgers } = useQuickEntry({ autoLoad: true });

// ── 本地状态 ──
const selectedLedgerId = ref<number | null>(null);
const sellableLedgerIds = ref<number[]>([]);

const currentLedgerType = computed(() => {
  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  return ledger?.ledger_type || null;
});

// 原始值。真正的 opType 是下面两个 computed——直接改 ref 会绕过守卫。
const stockOpTypeRaw = ref<StockOpType>("buy");
const fundOpTypeRaw = ref<FundOpType>("subscribe");

const buyFormRef = ref<InstanceType<typeof BuyForm>>();
const sellFormRef = ref<InstanceType<typeof SellForm>>();
const dividendFormRef = ref<InstanceType<typeof DividendForm>>();
const conversionFormRef = ref<InstanceType<typeof ConversionForm>>();

// ── 未保存离开保护（#1891）──
// 本页三个表单各自填到一半时切走，数据会静默丢失且无任何提示。
// BuyForm / SellForm 自带 isDirty，但此前**只有 TransactionDrawer 在读**——
// 浮动快速录入那条路有保护，而手动记账页（更常填、更容易丢）整块漏掉了。
// DividendForm 连 isDirty 都没有，本次一并补上（见该组件内注释）。
//
// 三个表单是 v-if / v-else-if / v-else-if 互斥渲染，同时最多挂一个，
// 所以 || 组合是安全的：未挂载的那几个 ref 为 undefined，判定落到 false。
const isFormDirty = computed(
  () =>
    buyFormRef.value?.isDirty === true ||
    sellFormRef.value?.isDirty === true ||
    dividendFormRef.value?.isDirty === true ||
    conversionFormRef.value?.isDirty === true
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
  set: (v: StockOpType) => {
    if (v === stockOpTypeRaw.value) return;
    void switchOpType(v, () => {
      stockOpTypeRaw.value = v;
    });
  }
});

const fundOpType = computed({
  get: () => fundOpTypeRaw.value,
  set: (v: FundOpType) => {
    if (v === fundOpTypeRaw.value) return;
    void switchOpType(v, () => {
      fundOpTypeRaw.value = v;
    });
  }
});

// ── 三个「当前是不是某类操作」的判定 ──
// 原先模板写一遍（决定渲染哪个表单）、脚本写一遍（决定走哪条提交通道），
// 两份口径一旦不同步，表现是「点了没反应」或「提交到错误的通道」。
// 统一收进 manualEntryModel，这里只做参数绑定。
const isSellLike = computed(() =>
  isSellLikeOf(currentLedgerType.value, stockOpType.value, fundOpType.value)
);

const isDividendLike = computed(() =>
  isDividendLikeOf(currentLedgerType.value, stockOpType.value, fundOpType.value)
);

const isSplit = computed(() =>
  isSplitOf(currentLedgerType.value, stockOpType.value, fundOpType.value)
);

/** DividendForm 的子模式：split 优先，其次按证券/基金分流 */
const dividendMode = computed(() =>
  dividendModeOf(isSplit.value, currentLedgerType.value, stockOpType.value)
);

const tradableLedgers = computed(() => {
  let list = ledgers.value.filter(l => l.ledger_type !== "property");
  if (isSellLike.value || fundOpType.value === "convert") {
    return list.filter(l => sellableLedgerIds.value.includes(l.id));
  }
  return list;
});

const opTypeComputed = computed(() =>
  submitOpTypeOf(
    isDividendLike.value,
    isSplit.value,
    stockOpType.value,
    fundOpType.value
  )
);

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
watch(selectedLedgerId, (newVal, oldVal) => {
  if (oldVal == null && newVal != null) {
    // 走 raw 而非 computed：这是首次选定账户后的**初始化**，不是用户主动切换操作类型。
    // 走 computed 会在极端时序下（表单刚挂载就被判脏）弹一个莫名其妙的确认框。
    stockOpTypeRaw.value = "buy";
    fundOpTypeRaw.value = "subscribe";
  }
});

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
      conversionFormRef.value?.resetForm();
      ElMessage.success("已重置，请继续录入");
    })
    .catch((action: any) => {
      if (action === "cancel") router.back();
    });
}

/**
 * 转换结果页的收尾（#2348 第四轮）——不走上面的模态框。
 *
 * 转换页提交后停在回执页（单号 + 三个数 + 确认时间），本身就是完整的收尾；
 * 再弹「交易记录已成功保存！」等于把刚说过的话换个框重说一遍。所以这里按
 * 用户在回执页上明确点的那个出口直接执行，不再追问一次。
 */
function onConversionDone(action: "again" | "list") {
  if (action === "list") {
    router.push("/transactions");
    return;
  }
  conversionFormRef.value?.resetForm();
}

// ── 生命周期 ──
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

/* 账户下拉回到输入基线契约的常规外观（design.md #1772）：
   旧版在这里用 :deep 清掉底色 / 描边 / 阴影，把 select 变成"一片无边界文字"，
   与同屏其它输入框不是同一种东西——「页面侧只允许覆盖令牌或纯几何 :deep」。 */
:deep(.el-button--primary) {
  height: 40px;
}
</style>
