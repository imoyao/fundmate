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
        <el-tooltip content="导入交割单或手动录入持仓" placement="bottom">
          <el-button type="text" size="small" @click="goToInventory" class="text-gray-400 hover:text-primary">
            导入持仓 >
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
      <el-button
        type="primary"
        :loading="submitting"
        @click="handleSubmit"
      >
        确认记账
      </el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { getLedgers } from "@/api/ledger";
import BuyForm from "./BuyForm.vue";
import SellForm from "./SellForm.vue";
import { emitter } from '@/utils/mitt';

// ── v-model ──
const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "submitted"): void; // 保持原有事件名
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

// ── 状态 ──
const opType = ref<"buy" | "sell">("buy");
const ledgers = ref<any[]>([]);
const submitting = ref(false);

const buyFormRef = ref<InstanceType<typeof BuyForm>>();
const sellFormRef = ref<InstanceType<typeof SellForm>>();

// 控制 body 类（抽屉打开时隐藏 fab）
watch(visible, (val) => {
  if (val) document.body.classList.add("drawer-open");
  else document.body.classList.remove("drawer-open");
});

// 加载账户
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

// 打开时加载账户
watch(visible, (val) => {
  if (val) loadLedgers();
});

// tab 切换时，子组件内部已有各自的重置逻辑（v-if 销毁），无需额外操作
function onTabChange() {
  // v-if 会导致子组件重新创建，自然重置
}

// 子组件提交成功
function onSubmitSuccess() {
  visible.value = false;
  emit("submitted");
  // 🔥 新增：无论用户在哪，发送一条全局刷新指令
  emitter.emit('refresh-ledger-data');
}

// 提交按钮点击，委托给子组件
async function handleSubmit() {
  if (opType.value === "buy") {
    await buyFormRef.value?.handleSubmit();
  } else {
    await sellFormRef.value?.handleSubmit();
  }
}

function resetForm() {
  // 子组件已经由 v-if 和 destroy-on-close 销毁，无需手动重置
  opType.value = "buy";
}

function goToInventory() {
  visible.value = false;
  // 如果需要跳转，由父组件统一处理路由，此处仅关闭抽屉
}
</script>

<style scoped>
/* 保持原样式 */
:deep(.el-drawer__footer) {
  position: sticky;
  bottom: 0;
  background: var(--bg-card);
  padding-top: 12px;
  border-top: 1px solid var(--border-default);
  z-index: 10;
}
:deep(.el-drawer__body) {
  padding: 20px;
}
</style>
