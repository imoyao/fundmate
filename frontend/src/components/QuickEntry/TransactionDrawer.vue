<template>
  <el-drawer
    v-model="visible"
    size="480px"
    direction="rtl"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="resetForm"
  >
    <template #header>
      <div class="flex items-center justify-between w-full">
        <span>记录交易</span>
        <el-tooltip
          content="导入持仓快照/交易流水、查看全部持仓"
          placement="bottom"
        >
          <el-button
            link
            size="small"
            class="text-gray-400 hover:text-primary"
            @click="goToInventory"
          >
            去全面盘点 >
          </el-button>
        </el-tooltip>
        <el-tooltip
          content="截图/文本识别交易（接 txn_import 场景）"
          placement="bottom"
        >
          <el-button
            link
            size="small"
            class="text-gray-400 hover:text-primary"
            @click="openRecognizer"
          >
            截图导入 >
          </el-button>
        </el-tooltip>
      </div>
    </template>

    <!-- 操作类型切换 -->
    <el-tabs v-model="opType" class="mb-4" @tab-change="onTabChange">
      <el-tab-pane label="买入" name="buy" />
      <el-tab-pane label="卖出" name="sell" />
    </el-tabs>

    <!-- 买入表单 -->
    <BuyForm
      v-if="opType === 'buy'"
      ref="buyFormRef"
      :ledgers="ledgers"
      @submit-success="onSubmitSuccess"
      @accounts-changed="loadLedgers"
    />

    <!-- 卖出表单 -->
    <SellForm
      v-if="opType === 'sell'"
      ref="sellFormRef"
      :ledgers="ledgers"
      @submit-success="onSubmitSuccess"
    />

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        确认记账
      </el-button>
    </template>
  </el-drawer>

  <!-- AI 识别截图导入（接 txn_import）→ 候选落 recon-draft，由统一对账工作台确认入库（#934） -->
  <RecognizerImportModal
    v-model="recognizerVisible"
    scenario-lock="txn_import"
    @saved="onRecognizerSaved"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useUnsavedChangesGuard } from "@/composables/useUnsavedChangesGuard";
import BuyForm from "./BuyForm.vue";
import SellForm from "./SellForm.vue";
import RecognizerImportModal from "./RecognizerImportModal.vue";
import {
  useQuickEntry,
  useQuickEntrySubmit
} from "@/composables/useQuickEntry";

const router = useRouter();

const props = defineProps<{ modelValue: boolean }>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "submitted"): void;
}>();

// ── 未保存离开保护（#1853）──
// 脏状态住在 BuyForm / SellForm 内部（两者各自 expose isDirty），父组件只能间接读。
// 注意：**el-drawer 没有 before-close**（那是 el-dialog 的 prop），且本抽屉已
// `:close-on-click-modal="false"` 禁用点遮罩——所以拦截点放在 v-model 的 setter 上，
// 它同时覆盖关闭按钮 / ESC / 底部「取消」三条路。
const isDirty = computed(() => {
  const form = opType.value === "buy" ? buyFormRef.value : sellFormRef.value;
  return form?.isDirty === true;
});

const { confirmDiscard } = useUnsavedChangesGuard(() => isDirty.value, {
  message: "交易表单已填写，确定放弃吗？"
});

/** 确认通过后的放行标志：只对本次 emit 生效，避免后续关闭被误拦 */
const allowClose = ref(false);

const visible = computed({
  get: () => props.modelValue,
  set: val => {
    if (!val && !allowClose.value && isDirty.value) {
      void confirmDiscard().then(ok => {
        if (!ok) return;
        allowClose.value = true;
        emit("update:modelValue", false);
        allowClose.value = false;
      });
      return;
    }
    emit("update:modelValue", val);
  }
});

const opType = ref<"buy" | "sell">("buy");
const buyFormRef = ref<InstanceType<typeof BuyForm>>();
const sellFormRef = ref<InstanceType<typeof SellForm>>();

const { ledgers, loadLedgers } = useQuickEntry();
const { submitting, handleSubmit, emitRefresh, resetForms } =
  useQuickEntrySubmit(opType, buyFormRef, sellFormRef);

watch(visible, val => {
  if (val) {
    document.body.classList.add("drawer-open");
    loadLedgers();
  } else {
    document.body.classList.remove("drawer-open");
  }
});

function onTabChange() {} // v-if 自动重置

function onSubmitSuccess() {
  // 先清脏再关：保存成功后表单仍是脏的，而关闭走的是 v-model setter——
  // 不先清就会弹「确定放弃吗？」（`resetForm` 挂在 @closed 上，跑在关闭之后）。
  resetForms();
  visible.value = false;
  emit("submitted");
  emitRefresh();
}

function resetForm() {
  opType.value = "buy";
  resetForms();
}

function goToInventory() {
  // #936：此前只关抽屉、不跳转，按钮点了没反应。全面盘点是导入与持仓的集中入口
  // （导入持仓快照 / 导入交易流水 / 持仓明细），故关抽屉后跳过去。
  visible.value = false;
  router.push("/inventory");
}

// 截图导入（#934）：打开 AI 识别模态（锁定 txn_import），候选落 recon-draft 后由工作台确认入库
const recognizerVisible = ref(false);
function openRecognizer() {
  recognizerVisible.value = true;
}
function onRecognizerSaved() {
  ElMessage.success("已存入对账草稿，请在「统一对账工作台」确认入库");
  recognizerVisible.value = false;
  visible.value = false;
}
</script>

<style scoped>
/* 保持原样式 */
:deep(.el-drawer__footer) {
  position: sticky;
  bottom: 0;
  z-index: 10;
  padding-top: 12px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-default);
}

:deep(.el-drawer__body) {
  padding: 20px;
}
</style>
