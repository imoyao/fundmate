<!--
  录入通用资产（页面编排层）。

  结构对齐最新设计语言（`frontend/design.md`）：
  - 页头走 `PageHeaderBar`（此前是裸 `<h2>`，字号 24/700，与全站 32/300 的页头不一致）
  - 内容外壳与页头同宽同内边距（`--space-5` + 680px 单列居中，同 `views/profile`）
  - 卡片走 `CardBlock`（统一 `--bg-card` + `--radius-lg` + `--border-light` + `--shadow-raised`），
    不再手写 `el-card` 的 16px 圆角 / 32-40px 内边距

  本页只做编排：表单、校验、提交在 `assetEntry/AssetEntryForm.vue`。
-->
<template>
  <div
    class="asset-entry-page min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="asset-entry-head">
      <PageHeaderBar
        title="录入资产"
        subtitle="记录房产、现金、信用卡、贷款等非交易类资产，完善你的资产负债表"
      >
        <template #action>
          <el-button text @click="router.push('/inventory')">
            <IconifyIconOffline icon="ep:arrow-left" class="mr-1" />
            返回盘点
          </el-button>
        </template>
      </PageHeaderBar>
    </div>

    <div class="asset-entry-shell">
      <AssetEntryForm
        :ledgers="ledgers"
        :initial="initial"
        :picked-ledger="pickedLedger"
        @create-ledger="showCreateLedgerDialog = true"
      />
    </div>

    <!-- 新增账户弹窗 -->
    <AssetCreateLedgerDialog
      v-model:visible="showCreateLedgerDialog"
      :ledgers="ledgers"
      @created="onLedgerCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { IconifyIconOffline } from "@/components/ReIcon";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";

import { getLedgers } from "@/api/ledger";
import AssetEntryForm from "./assetEntry/AssetEntryForm.vue";
import AssetCreateLedgerDialog from "./assetEntry/AssetCreateLedgerDialog.vue";
import { parseInitialFromQuery } from "./assetEntry/assetEntryModel";

defineOptions({ name: "AssetEntry" });

const route = useRoute();
const router = useRouter();

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
.asset-entry-page {
  padding: var(--space-5);
}

/* 页头与内容区同宽（680px 单列）：不覆盖 max-width 时页头按 --layout-content-width
   居中，标题会跑到卡片左侧很远的地方（PageHeaderBar 文档里点名的错位形态）。 */
.asset-entry-head :deep(.page-header) {
  max-width: 680px;
}

.asset-entry-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-section);
  max-width: 680px;
  margin: 0 auto;
}

/* 弹窗样式：三条都是裸 `:deep`，编译成 `[data-v-x] .el-dialog`，
   要求 .el-dialog 是带 scopeId 元素的**后代**。所以它们必须留在本页——
   搬进 AssetCreateLedgerDialog 后 el-dialog 就是那个组件的根元素自己，
   既不是自己的后代、也匹配不上，弹窗背景与标题会静默退回 EP 默认样式。 */
:deep(.el-dialog) {
  background-color: var(--bg-card);
  border-radius: var(--radius-lg);
}

:deep(.el-dialog__title) {
  font-size: var(--text-num-strong);
  font-weight: 600;
  color: var(--text-primary);
}

:deep(.el-dialog__body) {
  padding: var(--space-standard) var(--space-loose);
}
</style>
