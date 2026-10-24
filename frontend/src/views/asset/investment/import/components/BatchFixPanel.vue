<script setup lang="ts">
// 批量修正内联面板（#1792）。展开于摘要面板下方，与表格同屏。
//
// 本文件只做「编排」：顶部形态标签与全局动作、table 模式的引导、四种形态的分支
// （table / batch / single / none）、逐条卡片列表、两个附属弹窗的开关。
// 四分区在 BatchFixBatchSections 里，分区外壳、卡片、弹窗各自成组件。
import { computed, reactive, ref } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import BatchFixBatchSections from "./BatchFixBatchSections.vue";
import BatchFixCard from "./BatchFixCard.vue";
import BatchFixDialogs from "./BatchFixDialogs.vue";
import {
  autoFixableCountOf,
  modeLabelOf,
  singleScopeLabelOf,
  type CardDraft
} from "./batchFixPanelModel";

const {
  activeFixMode,
  fixModeOverride,
  singleFixScope,
  singleFixRows,
  fixSectionRows,
  fixSectionCounts,
  reverseRepoRows,
  repoDetectBasis,
  filledRows,
  canUndo,
  undoLastFix,
  applyManualFill,
  batchFillCode,
  batchFixAmount,
  skipCategory,
  getCategoryTagType,
  autoFix,
  enrichingNav,
  hasFundRecordsForNav,
  fundRecordsCount,
  calculatedCount,
  showFullTable,
  showProblemOnly,
  toggleFixPanel
} = useImportWizardContext();

/** 可程序化自动处理的条目：mismatch 金额重算 + 基金净值抓取 + 已推算确认 */
const autoFixableCount = computed(() =>
  autoFixableCountOf(
    fixSectionCounts.value.mismatch,
    calculatedCount.value,
    hasFundRecordsForNav.value,
    fundRecordsCount.value
  )
);

const modeLabel = computed(() => modeLabelOf(activeFixMode.value));
const singleScopeLabel = computed(() =>
  singleScopeLabelOf(singleFixScope.value)
);

const isEmptyState = computed(
  () => activeFixMode.value === "none" && reverseRepoRows.value.length === 0
);

const singleResolvedHint = computed(
  () =>
    activeFixMode.value === "single" &&
    singleFixRows.value.length === 0 &&
    !isEmptyState.value
);

/** 错误行条数（table 模式引导用；批量态那条在 BatchFixBatchSections 内） */
const errorRowCount = computed(() => fixSectionCounts.value.error);

/** 逐条卡片的表单草稿：按 _rowKey 懒建，点「应用」才写回行数据 */
const cardDrafts = reactive<Record<string, CardDraft>>({});

function draftFor(row: any): CardDraft {
  if (!cardDrafts[row._rowKey]) {
    cardDrafts[row._rowKey] = { quantity: "", price: "", code: "" };
  }
  return cardDrafts[row._rowKey];
}

function updateDraft(row: any, field: keyof CardDraft, value: string) {
  draftFor(row)[field] = value;
}

function applyCardCode(row: any) {
  batchFillCode([row], draftFor(row).code);
}

function applyCardFill(row: any) {
  const draft = draftFor(row);
  applyManualFill(row, { quantity: draft.quantity, price: draft.price });
}

function backToBatch() {
  fixModeOverride.value = null;
  singleFixScope.value = "all";
}

/** §4 第 4 条：引导跳转完整表格手动处理（table 态要顺手收起面板） */
function gotoFullTable() {
  showFullTable.value = true;
  showProblemOnly.value = true;
  toggleFixPanel();
}

const showFilledDialog = ref(false);
const showRepoDialog = ref(false);
</script>

<template>
  <div class="batch-fix-panel" data-fix-panel>
    <!-- 顶部动作行：形态标签 + 一键自动修复 + 全局撤销 -->
    <div class="bf-actions bf-actions--top">
      <span v-if="modeLabel" class="bf-mode" :data-fix-mode="activeFixMode">
        {{ modeLabel }}
      </span>
      <el-button
        v-if="autoFixableCount > 0"
        type="primary"
        size="default"
        :loading="enrichingNav"
        @click="autoFix"
      >
        <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
        自动修复可处理项
      </el-button>
      <el-button size="default" :disabled="!canUndo" @click="undoLastFix()">
        <IconifyIconOffline icon="ep:refresh-left" class="mr-1" />
        撤销上一步
      </el-button>
    </div>

    <!-- table 模式：全部为解析错误，面板内无可批量项（§4 第 4 条引导 + 跳过） -->
    <el-alert
      v-if="activeFixMode === 'table' && errorRowCount > 0"
      type="warning"
      :closable="false"
      show-icon
      class="bf-alert"
    >
      <template #title>
        {{ errorRowCount }} 条解析错误无法在面板内修正，请到完整表格手动处理。
      </template>
      <div class="bf-alert-actions">
        <el-button size="small" @click="skipCategory(fixSectionRows.error)">
          跳过这 {{ errorRowCount }} 条
        </el-button>
        <el-button size="small" type="primary" @click="gotoFullTable">
          去完整表格
        </el-button>
      </div>
    </el-alert>

    <!-- 分类批量修正：四分区（§5） -->
    <BatchFixBatchSections
      @open-filled="showFilledDialog = true"
      @open-repo="showRepoDialog = true"
    />

    <!-- 逐条修正：卡片式单条表单（§4 第 1 条，≤10 条自动进入） -->
    <template v-if="activeFixMode === 'single'">
      <div class="bf-single-head">
        <span class="bf-single-title">
          逐条修正 — {{ singleScopeLabel }}（{{ singleFixRows.length }} 条）
        </span>
        <el-button
          v-if="fixModeOverride === 'single'"
          size="small"
          @click="backToBatch"
        >
          返回分类批量
        </el-button>
      </div>

      <p v-if="singleResolvedHint" class="bf-empty">该范围内的问题已全部处理</p>

      <div v-else class="bf-cards">
        <BatchFixCard
          v-for="{ row, section } in singleFixRows"
          :key="row._rowKey"
          :row="row"
          :section="section"
          :draft="draftFor(row)"
          :tag-type="getCategoryTagType(section, 1)"
          @update-draft="
            payload => updateDraft(row, payload.field, payload.value)
          "
          @apply-code="applyCardCode(row)"
          @apply-fill="applyCardFill(row)"
          @fix-amount="batchFixAmount([row])"
          @skip="skipCategory([row])"
        />
      </div>
    </template>

    <p v-if="isEmptyState" class="bf-empty">本批数据校验通过，无需修正</p>

    <!-- 面板底部（#783 §5：面板底部【收起批量修正】） -->
    <div class="bf-foot">
      <el-button size="default" @click="toggleFixPanel">
        收起批量修正
      </el-button>
    </div>

    <BatchFixDialogs
      v-model:filled-visible="showFilledDialog"
      v-model:repo-visible="showRepoDialog"
      :filled-rows="filledRows"
      :reverse-repo-rows="reverseRepoRows"
      :detect-basis="repoDetectBasis"
    />
  </div>
</template>

<style scoped>
/* #1792：内联展开于摘要面板下方，自身是带底色的分区面板（布局尺寸由 PreviewStep 施加） */
.batch-fix-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.bf-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.bf-mode {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: 999px;
}

.bf-alert {
  margin: 0;
}

.bf-alert-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}

.bf-single-head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.bf-single-title {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.bf-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
}

.bf-empty {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.bf-foot {
  display: flex;
  justify-content: center;
  padding-top: 4px;
  border-top: 1px dashed var(--border-default);
}
</style>
