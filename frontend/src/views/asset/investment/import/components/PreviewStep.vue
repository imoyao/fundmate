<script setup lang="ts">
import { computed } from "vue";
import SummaryPanel from "./SummaryPanel.vue";
import PreviewTable from "./PreviewTable.vue";
import BatchFixPanel from "./BatchFixPanel.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  currentStep,
  selectedLedgerName,
  toggleAllocationPanel,
  showAllocationGroupPanel,
  duplicateCount,
  blockedCount,
  errorCount,
  showFixPanel,
  selectedCount,
  totalRows,
  validRowsCount,
  draftSavedLabel,
  draftSavedHintVisible,
  allRowsDuplicate,
  importNormalOnly,
  skipAllDuplicatesAndBack,
  importing,
  confirmImport,
  showCashBindingBanner,
  showCashTransferHint,
  linkedCashLedgerName,
  dismissCashBindingBanner,
  cashLedgersForImport,
  bannerCashLedgerId,
  linkCashAccount,
  openCreateCashFromBanner
} = useImportWizardContext();

/**
 * 待处理条数（重复 + 待补全 + 错误）：底栏「N 条待修正」与
 * 「仅导入正常数据」按钮显隐的唯一判据（#783 §9.2）。
 */
const pendingFixCount = computed(
  () => duplicateCount.value + blockedCount.value + errorCount.value
);
</script>

<template>
  <div class="step3-container">
    <div class="step3-header">
      <!-- #783 P1：原型要的「重新选择文件」入口。预览页的「上一步」唯一含义就是换文件，
           故把泛称改成具体动作，用户不必推断点下去会发生什么 -->
      <el-button size="default" @click="currentStep = 1"
        >重新选择文件</el-button
      >
      <span class="header-ledger">导入账户：{{ selectedLedgerName }}</span>
      <!-- #783 §一/§8.1：草稿状态文案——保存成功即现身，3 秒后淡出（不占位、不打断） -->
      <Transition name="draft-hint">
        <span v-if="draftSavedHintVisible" class="header-draft" role="status">
          草稿·已保存 {{ draftSavedLabel }}
        </span>
      </Transition>
      <div class="header-actions ml-auto flex items-center gap-3">
        <el-button size="default" @click="toggleAllocationPanel">
          <IconifyIconOffline icon="ep:setting" class="mr-1" />
          {{ showAllocationGroupPanel ? "收起配置" : "设置配置目标" }}
        </el-button>
      </div>
    </div>

    <!-- #2281 引导态：能力宣告 + 关联入口（未关联现金账户时；不可关闭，tooltip 指向此处） -->
    <div v-if="showCashBindingBanner" class="cash-binding-banner">
      <IconifyIconOffline icon="ep:warning" class="banner-icon" />
      <span class="banner-text">
        检测到银证转账交易，支持导入：勾选转账行后，现金账户将自动生成反向流水（银行↔证券两本账自动配平）。请先为当前账户「{{
          selectedLedgerName
        }}」关联现金账户：
      </span>
      <el-select
        v-model="bannerCashLedgerId"
        class="banner-select"
        size="small"
        clearable
        placeholder="选择现金账户"
        @change="linkCashAccount"
      >
        <el-option
          v-for="c in cashLedgersForImport"
          :key="c.id"
          :label="c.name"
          :value="c.id"
        />
      </el-select>
      <el-button
        class="banner-create-btn"
        size="small"
        link
        type="primary"
        @click="openCreateCashFromBanner"
        >+ 新建现金账户</el-button
      >
    </div>

    <!-- #2281 轻量提示态：已关联仍告知能力存在（默认不勾选，由用户决定），可关闭 -->
    <div v-else-if="showCashTransferHint" class="cash-transfer-hint">
      <IconifyIconOffline icon="ep:info-filled" class="hint-icon" />
      <span class="hint-text">
        已为「{{ selectedLedgerName }}」关联现金账户「{{
          linkedCashLedgerName
        }}」。转账行可勾选导入（默认不勾选，由你决定），导入后现金账户自动生成反向流水。
      </span>
      <el-button
        class="hint-close-btn"
        size="small"
        text
        type="primary"
        @click="dismissCashBindingBanner"
        >知道了</el-button
      >
    </div>

    <div class="step3-body">
      <SummaryPanel />
      <!-- #1792：批量修正面板改为摘要下方内联展开（原右侧覆盖式抽屉已移除），
           摘要、修正面板、表格三者同屏互不覆盖 -->
      <BatchFixPanel v-if="showFixPanel" class="step3-fixpanel" />
      <PreviewTable />
    </div>

    <div class="fixed-action-bar">
      <div class="action-content">
        <div class="action-summary">
          <span class="summary-primary">
            已选择 <strong>{{ selectedCount }}</strong> 条<template
              v-if="pendingFixCount > 0"
              >（正常数据），<strong>{{ pendingFixCount }}</strong>
              条待修正</template
            >
          </span>
          <span v-if="pendingFixCount > 0" class="summary-secondary">
            本次共识别 {{ totalRows }} 条：{{ duplicateCount }} 条重复 /
            {{ blockedCount }} 条待补全<template v-if="errorCount > 0"
              >/ {{ errorCount }} 条错误</template
            >
          </span>
        </div>
        <div class="flex gap-3">
          <!-- #783 §十 边界一：全表皆重复时不存在「正常数据」，只留跳过出口 -->
          <el-button v-if="allRowsDuplicate" @click="skipAllDuplicatesAndBack">
            全部跳过，返回上一步
          </el-button>
          <el-button
            v-else-if="pendingFixCount > 0"
            :loading="importing"
            @click="importNormalOnly"
            >{{
              importing ? "正在导入..." : `仅导入正常数据（${validRowsCount}）`
            }}
          </el-button>
          <el-button
            type="primary"
            :disabled="selectedCount === 0"
            :loading="importing"
            class="import-btn"
            @click="confirmImport"
            >{{ importing ? "正在导入..." : `确认导入 ${selectedCount} 条` }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step3-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.step3-header {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
}

/* 步骤3 智能体检：未关联现金账户的银证转账提示横幅 */
.cash-binding-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 10px 14px;
  margin: 12px 16px 0;
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.banner-icon {
  font-size: var(--text-body);
  color: var(--color-warning-ink);
}

.banner-text {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.banner-select {
  width: 180px;
}

.banner-create-btn {
  font-weight: 500;
}

/* #2281 轻量提示态：主色系弱化样式，与引导态的警示态区分 */
.cash-transfer-hint {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 8px 14px;
  margin: 12px 16px 0;
  background: var(--color-primary-10);
  border: 1px solid var(--color-primary-20);
  border-radius: var(--radius-sm);
}

.hint-icon {
  font-size: var(--text-small);
  color: var(--color-primary-ink);
}

.hint-text {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.hint-close-btn {
  flex-shrink: 0;
  margin-left: auto;
}

.header-ledger {
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--text-primary);
}

/* 草稿状态文案（#783 §一/§8.1）：次级信息，不让它跟账户名抢注意力 */
.header-draft {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 3 秒后淡出：进出各 0.3s，避免出现/消失的突兀跳变 */
.draft-hint-enter-active,
.draft-hint-leave-active {
  transition: opacity 0.3s ease;
}

.draft-hint-enter-from,
.draft-hint-leave-to {
  opacity: 0;
}

.step3-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  min-height: calc(100vh - 240px);
  padding: 16px;
  overflow: hidden;
}

/*
 * #1792 内联修正面板：摘要下方、表格上方，三者同屏。
 * 有界内滚（max-height + overflow-y）——内容高时面板内部滚动，不产生页面级滚动条，
 * 表格仍是唯一可滚动的主体区域（#783 §1「仅表格区域纵向滚动」的口径按此放宽）。
 */
.step3-fixpanel {
  flex: 0 1 auto;
  max-height: 42%;
  overflow-y: auto;
}

.fixed-action-bar {
  position: sticky;
  bottom: 0;
  z-index: 10;
  padding: 12px 16px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-default);
}

.action-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1100px;
  margin: 0 auto;
}

.action-summary {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-primary {
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.summary-secondary {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
