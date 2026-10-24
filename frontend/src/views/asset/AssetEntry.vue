<template>
  <div
    class="asset-entry p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="mb-6">
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        录入通用资产
      </h2>
      <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary-ink)' }">
        记录房产、现金、信用卡、贷款等非交易类资产，完善你的资产负债表
      </p>
    </div>

    <AssetEntryForm
      :ledgers="ledgers"
      :initial="initial"
      :picked-ledger="pickedLedger"
      @create-ledger="showCreateLedgerDialog = true"
    />

    <!-- 新增账户弹窗 -->
    <AssetCreateLedgerDialog
      v-model:visible="showCreateLedgerDialog"
      @created="onLedgerCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";

import { getLedgers } from "@/api/ledger";
import AssetEntryForm from "./assetEntry/AssetEntryForm.vue";
import AssetCreateLedgerDialog from "./assetEntry/AssetCreateLedgerDialog.vue";
import { parseInitialFromQuery } from "./assetEntry/assetEntryModel";

defineOptions({ name: "AssetEntry" });

const route = useRoute();

const ledgers = ref<any[]>([]);
const showCreateLedgerDialog = ref(false);
/** 弹窗刚建出来的账户，递给表单回填「所属账户」 */
const pickedLedger = ref<{ id: number; name: string } | null>(null);

/**
 * URL 解析出的初值（?category= / ?minor= / ?type=）。
 * 三个参数都来自盘点页快捷录入或手敲，非法值一律忽略——见 `parseInitialFromQuery`。
 */
const initial = parseInitialFromQuery(route.query);

async function fetchLedgers() {
  try {
    const res = await getLedgers();
    ledgers.value = (res as any).data ?? [];
  } catch (e) {
    console.error(e);
  }
}

/** 先刷新账户列表再回填，否则 el-select 会闪一下「选项里没有的 id」 */
async function onLedgerCreated(ledger: { id: number; name: string }) {
  await fetchLedgers();
  pickedLedger.value = ledger;
}

onMounted(fetchLedgers);
</script>

<style scoped>
/* 弹窗样式：三条都是裸 `:deep`，编译成 `[data-v-x] .el-dialog`，
   要求 .el-dialog 是带 scopeId 元素的**后代**。所以它们必须留在本页——
   搬进 AssetCreateLedgerDialog 后 el-dialog 就是那个组件的根元素自己，
   既不是自己的后代、也匹配不上，弹窗背景与标题会静默退回 EP 默认样式。 */
:deep(.el-dialog) {
  background-color: var(--bg-card);
  border-radius: 16px;
}

:deep(.el-dialog__title) {
  font-size: var(--text-num-strong);
  font-weight: 600;
  color: var(--text-primary);
}

:deep(.el-dialog__body) {
  padding: 24px 32px;
}
</style>
