<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import type { FixSectionKey } from "../composables/batchFixLogic";
import { ALLOCATION_OPTIONS } from "@/constants";

const {
  activeFixMode,
  fixModeOverride,
  singleFixScope,
  singleFixRows,
  fixSectionRows,
  fixSectionCounts,
  reverseRepoRows,
  repoDetectBasis,
  autoFillableRows,
  filledRows,
  canUndo,
  undoTopScope,
  undoLastFix,
  autoFillMissing,
  applyManualFill,
  revertRepoAllocation,
  batchFillCode,
  batchFixAmount,
  skipCategory,
  batchCodeInput,
  getMissingRowsByType,
  getCategoryDesc,
  getCategoryTagType,
  isCategoryActive,
  filterByCategory,
  autoFix,
  enrichingNav,
  hasFundRecordsForNav,
  fundRecordsCount,
  calculatedCount,
  showMatchDrawer,
  showFullTable,
  showProblemOnly,
  toggleFixPanel
} = useImportWizardContext();

const SECTION_LABELS: Record<FixSectionKey, string> = {
  error: "解析错误",
  missingCode: "代码未匹配",
  missingQtyPrice: "单价/数量缺失",
  mismatch: "数据不一致"
};

const AUTO_FIELD_LABELS: Record<string, string> = {
  quantity: "数量",
  price: "价格"
};

/** 可程序化自动处理的条目：mismatch 金额重算 + 基金净值抓取 + 已推算确认 */
const autoFixableCount = computed(
  () =>
    fixSectionCounts.value.mismatch +
    calculatedCount.value +
    (hasFundRecordsForNav.value ? fundRecordsCount.value : 0)
);

const modeLabel = computed(() => {
  switch (activeFixMode.value) {
    case "single":
      return "逐条修正模式";
    case "batch":
      return "分类批量修正模式";
    case "table":
      return "请到完整表格处理";
    default:
      return "";
  }
});

const singleScopeLabel = computed(() =>
  singleFixScope.value === "all"
    ? "全部问题"
    : SECTION_LABELS[singleFixScope.value]
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

/** 逆回购分区【撤销】的可撤目标：解析期自动置的「活钱」，手动设置过的不动 */
const repoRevertable = computed(() =>
  reverseRepoRows.value.filter(
    row => row.allocation === "liquid" && !row._allocationManual
  )
);

/** 错误行条数（批量模式的提示条与 table 模式引导共用） */
const errorRowCount = computed(() => fixSectionCounts.value.error);

/** 逐条卡片的表单草稿：按 _rowKey 懒建，点「应用」才写回行数据 */
const cardDrafts = reactive<
  Record<string, { quantity: string; price: string; code: string }>
>({});

function draftFor(row: any) {
  if (!cardDrafts[row._rowKey]) {
    cardDrafts[row._rowKey] = { quantity: "", price: "", code: "" };
  }
  return cardDrafts[row._rowKey];
}

function applyCardCode(row: any) {
  batchFillCode([row], draftFor(row).code);
}

function applyCardFill(row: any) {
  const draft = draftFor(row);
  applyManualFill(row, { quantity: draft.quantity, price: draft.price });
}

/** mismatch 卡片的差额说明（#783 §5：展示差额说明） */
function mismatchDiff(row: any): string {
  const qty = Number(row.quantity),
    prc = Number(row.price),
    amt = Number(row.amount);
  const calc = qty * prc;
  const diff = calc - amt;
  const sign = diff > 0 ? "+" : "";
  return `数量×价格 = ${calc.toFixed(2)}，当前金额 ${amt.toFixed(2)}，差额 ${sign}${diff.toFixed(2)}`;
}

/** 分区级【逐条修正】：切到卡片形态并圈定该分区（可再返回分类批量） */
function enterSingle(section: FixSectionKey) {
  singleFixScope.value = section;
  fixModeOverride.value = "single";
}

function backToBatch() {
  fixModeOverride.value = null;
  singleFixScope.value = "all";
}

/** §4 第 4 条：引导跳转完整表格手动处理 */
function gotoFullTable(closePanel: boolean) {
  showFullTable.value = true;
  showProblemOnly.value = true;
  if (closePanel) toggleFixPanel();
}

function allocationLabel(value: string): string {
  return ALLOCATION_OPTIONS.find(o => o.value === value)?.label || value;
}

function filledFieldsLabel(row: any): string {
  return (row._autoFilled || [])
    .map((f: string) => AUTO_FIELD_LABELS[f] || f)
    .join("、");
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
        <el-button size="small" type="primary" @click="gotoFullTable(true)">
          去完整表格
        </el-button>
      </div>
    </el-alert>

    <!-- 分类批量修正：四分区（§5） -->
    <div
      v-if="activeFixMode === 'batch' || reverseRepoRows.length > 0"
      class="bf-sections"
    >
      <template v-if="activeFixMode === 'batch'">
        <!-- 混合不可批量问题提示（§4 第 4 条：批量处理可批量部分，错误行引导 + 跳过） -->
        <el-alert
          v-if="errorRowCount > 0"
          type="warning"
          :closable="false"
          show-icon
          class="bf-alert bf-alert--inline"
        >
          <template #title>
            另有 {{ errorRowCount }} 条解析错误不支持批量修正。
          </template>
          <div class="bf-alert-actions">
            <el-button size="small" @click="skipCategory(fixSectionRows.error)">
              跳过这 {{ errorRowCount }} 条
            </el-button>
            <el-button size="small" @click="gotoFullTable(false)">
              去完整表格
            </el-button>
          </div>
        </el-alert>

        <!-- 分区一：代码未匹配 -->
        <section
          v-if="fixSectionCounts.missingCode > 0"
          class="bf-section"
          data-section="missingCode"
          :class="{ 'bf-section--active': isCategoryActive('missingCode') }"
          @click="filterByCategory('missingCode')"
        >
          <div class="bf-section-header">
            <span class="bf-section-label">{{
              SECTION_LABELS.missingCode
            }}</span>
            <span class="bf-section-desc">{{
              getCategoryDesc("missingCode")
            }}</span>
            <el-tag
              size="small"
              effect="dark"
              :type="
                getCategoryTagType('missingCode', fixSectionCounts.missingCode)
              "
            >
              {{ fixSectionCounts.missingCode }} 条
            </el-tag>
          </div>
          <div class="bf-section-actions" @click.stop>
            <template v-for="assetType in ['fund', 'stock']" :key="assetType">
              <template
                v-if="
                  getMissingRowsByType(fixSectionRows.missingCode, assetType)
                    .length > 0
                "
              >
                <el-button
                  v-if="
                    assetType === 'fund' &&
                    getMissingRowsByType(fixSectionRows.missingCode, 'fund')
                      .length > 1
                  "
                  type="primary"
                  size="small"
                  @click="showMatchDrawer = true"
                >
                  匹配基金代码（{{
                    getMissingRowsByType(fixSectionRows.missingCode, "fund")
                      .length
                  }}只）
                </el-button>
                <el-input
                  v-model="batchCodeInput"
                  :placeholder="
                    assetType === 'fund' ? '输入基金代码' : '输入股票代码'
                  "
                  size="small"
                  class="bf-input"
                />
                <el-button
                  type="primary"
                  size="small"
                  @click="
                    batchFillCode(
                      getMissingRowsByType(
                        fixSectionRows.missingCode,
                        assetType
                      ),
                      batchCodeInput
                    )
                  "
                >
                  应用到全部
                </el-button>
              </template>
            </template>
            <el-button
              size="small"
              class="bf-btn-right"
              @click="skipCategory(fixSectionRows.missingCode)"
            >
              全部跳过
            </el-button>
          </div>
        </section>

        <!-- 分区二：单价/数量缺失 -->
        <section
          v-if="fixSectionCounts.missingQtyPrice > 0"
          class="bf-section"
          data-section="missingQtyPrice"
          :class="{ 'bf-section--active': isCategoryActive('missingQtyPrice') }"
          @click="filterByCategory('missingQtyPrice')"
        >
          <div class="bf-section-header">
            <span class="bf-section-label">{{
              SECTION_LABELS.missingQtyPrice
            }}</span>
            <span class="bf-section-desc">{{
              getCategoryDesc("missingQtyPrice")
            }}</span>
            <el-tag
              size="small"
              effect="dark"
              :type="
                getCategoryTagType(
                  'missingQtyPrice',
                  fixSectionCounts.missingQtyPrice
                )
              "
            >
              {{ fixSectionCounts.missingQtyPrice }} 条
            </el-tag>
          </div>
          <p class="bf-section-meta">
            可自动填充 {{ autoFillableRows.length }} 条
            <span v-if="filledRows.length > 0" class="bf-section-meta-sub">
              ｜已填充 {{ filledRows.length }} 条
            </span>
          </p>
          <div class="bf-section-actions" @click.stop>
            <el-button
              type="primary"
              size="small"
              :disabled="autoFillableRows.length === 0"
              @click="autoFillMissing"
            >
              自动填充
            </el-button>
            <el-button
              size="small"
              :disabled="filledRows.length === 0"
              @click="showFilledDialog = true"
            >
              查看已填充数据
            </el-button>
            <el-button
              size="small"
              :disabled="undoTopScope !== 'fill'"
              @click="undoLastFix('fill')"
            >
              撤销
            </el-button>
            <el-button size="small" @click="enterSingle('missingQtyPrice')">
              逐条修正
            </el-button>
            <el-button
              size="small"
              class="bf-btn-right"
              @click="skipCategory(fixSectionRows.missingQtyPrice)"
            >
              全部跳过
            </el-button>
          </div>
        </section>

        <!-- 分区三：数据不一致 -->
        <section
          v-if="fixSectionCounts.mismatch > 0"
          class="bf-section"
          data-section="mismatch"
          :class="{ 'bf-section--active': isCategoryActive('mismatch') }"
          @click="filterByCategory('mismatch')"
        >
          <div class="bf-section-header">
            <span class="bf-section-label">{{ SECTION_LABELS.mismatch }}</span>
            <span class="bf-section-desc">{{
              getCategoryDesc("mismatch")
            }}</span>
            <el-tag
              size="small"
              effect="dark"
              :type="getCategoryTagType('mismatch', fixSectionCounts.mismatch)"
            >
              {{ fixSectionCounts.mismatch }} 条
            </el-tag>
          </div>
          <div class="bf-section-actions" @click.stop>
            <el-button
              type="primary"
              size="small"
              @click="batchFixAmount(fixSectionRows.mismatch)"
            >
              自动修正金额
            </el-button>
            <el-button size="small" @click="enterSingle('mismatch')">
              逐条修正
            </el-button>
            <el-button
              size="small"
              class="bf-btn-right"
              @click="skipCategory(fixSectionRows.mismatch)"
            >
              全部跳过
            </el-button>
          </div>
        </section>
      </template>

      <!-- 分区四：逆回购特殊处理（信息型，非问题分区） -->
      <section
        v-if="reverseRepoRows.length > 0"
        class="bf-section bf-section--info"
        data-section="reverse_repo"
      >
        <div class="bf-section-header">
          <span class="bf-section-label">逆回购识别</span>
          <span class="bf-section-desc">
            国债逆回购代码在解析时自动识别为逆回购，配置目标自动设为「活钱」
          </span>
          <el-tag size="small" effect="dark" type="info">
            {{ reverseRepoRows.length }} 条
          </el-tag>
        </div>
        <div class="bf-section-actions" @click.stop>
          <el-button size="small" @click="showRepoDialog = true">
            查看转换结果
          </el-button>
          <el-button
            size="small"
            :disabled="repoRevertable.length === 0"
            @click="revertRepoAllocation"
          >
            撤销
          </el-button>
        </div>
      </section>
    </div>

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
        <article
          v-for="{ row, section } in singleFixRows"
          :key="row._rowKey"
          class="bf-card"
          data-fix-card
          :data-section="section"
        >
          <div class="bf-card-header">
            <el-tag
              size="small"
              effect="plain"
              :type="getCategoryTagType(section, 1)"
            >
              {{ SECTION_LABELS[section] }}
            </el-tag>
            <span class="bf-card-name">
              {{ row.name || row.symbol || "未命名" }}
            </span>
            <span v-if="row.symbol" class="bf-card-meta">{{ row.symbol }}</span>
            <span v-if="row.trade_date" class="bf-card-meta">
              {{ row.trade_date }}
            </span>
          </div>

          <p v-if="section === 'error'" class="bf-card-error">
            {{ row.error }}
          </p>
          <p v-else-if="section === 'mismatch'" class="bf-card-diff">
            {{ mismatchDiff(row) }}
          </p>

          <div v-if="section === 'missingCode'" class="bf-card-form">
            <el-input
              v-model="draftFor(row).code"
              placeholder="输入证券代码"
              size="small"
              class="bf-input"
            />
            <el-button type="primary" size="small" @click="applyCardCode(row)">
              应用
            </el-button>
          </div>

          <div v-if="section === 'missingQtyPrice'" class="bf-card-form">
            <el-input
              v-model="draftFor(row).quantity"
              placeholder="数量"
              size="small"
              class="bf-input"
            />
            <el-input
              v-model="draftFor(row).price"
              placeholder="单价"
              size="small"
              class="bf-input"
            />
            <el-button type="primary" size="small" @click="applyCardFill(row)">
              应用
            </el-button>
          </div>

          <div v-if="section === 'mismatch'" class="bf-card-form">
            <el-button
              type="primary"
              size="small"
              @click="batchFixAmount([row])"
            >
              修正此条
            </el-button>
          </div>

          <div class="bf-card-footer">
            <el-button size="small" @click="skipCategory([row])">
              跳过此条
            </el-button>
          </div>
        </article>
      </div>
    </template>

    <p v-if="isEmptyState" class="bf-empty">本批数据校验通过，无需修正</p>

    <!-- 面板底部（#783 §5：面板底部【收起批量修正】） -->
    <div class="bf-foot">
      <el-button size="default" @click="toggleFixPanel">
        收起批量修正
      </el-button>
    </div>

    <!-- 【查看已填充数据】 -->
    <el-dialog
      v-model="showFilledDialog"
      title="已填充数据"
      width="640px"
      class="bf-dialog"
    >
      <el-table :data="filledRows" size="small" max-height="400">
        <el-table-column label="名称" prop="name" min-width="140" />
        <el-table-column label="代码" prop="symbol" width="100" />
        <el-table-column label="已填充字段" min-width="110">
          <template #default="{ row }">
            {{ filledFieldsLabel(row) }}
          </template>
        </el-table-column>
        <el-table-column label="数量" prop="quantity" width="110" />
        <el-table-column label="单价" prop="price" width="110" />
      </el-table>
      <p class="bf-dialog-note">
        数量 / 价格按「金额 ÷ 另一项」自动推算；点顶部【撤销上一步】可回滚。
      </p>
    </el-dialog>

    <!-- 【查看转换结果】（逆回购） -->
    <el-dialog
      v-model="showRepoDialog"
      title="逆回购转换结果"
      width="720px"
      class="bf-dialog"
    >
      <p class="bf-dialog-note">
        解析规则：沪市 204xxx、深市 1318xx
        代码自动识别为逆回购，配置目标自动设为
        「活钱」。类型识别是解析事实不可撤销；配置目标可在分区点【撤销】回退为「长期增值」。
      </p>
      <el-table :data="reverseRepoRows" size="small" max-height="400">
        <el-table-column label="日期" prop="trade_date" width="110" />
        <el-table-column label="代码" prop="symbol" width="90" />
        <el-table-column label="名称" prop="name" min-width="120" />
        <el-table-column label="金额" prop="amount" width="110" />
        <el-table-column label="识别依据" min-width="110">
          <template #default="{ row }">
            {{ repoDetectBasis(row) }}
          </template>
        </el-table-column>
        <el-table-column label="配置目标" width="110">
          <template #default="{ row }">
            {{ allocationLabel(row.allocation) }}
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
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
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: 999px;
}

.bf-alert {
  margin: 0;
}

.bf-alert--inline {
  grid-column: 1 / -1;
}

.bf-alert-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}

.bf-sections {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 10px;
  min-width: 0;
}

.bf-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: border-color 0.2s;
}

.bf-section:hover,
.bf-section--active {
  border-color: var(--color-primary);
}

.bf-section--info {
  cursor: default;
}

.bf-section-header {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.bf-section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.bf-section-desc {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: var(--text-tertiary-ink);
}

.bf-section-meta {
  margin: 0;
  font-size: 12px;
  color: var(--color-warning-ink);
}

.bf-section-meta-sub {
  color: var(--text-tertiary-ink);
}

.bf-section-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.bf-section-actions .el-button + .el-button {
  margin-left: 0;
}

.bf-btn-right {
  margin-left: auto;
}

.bf-input {
  width: 132px;
}

.bf-single-head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.bf-single-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.bf-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
}

.bf-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--color-warning);
  border-radius: 8px;
}

.bf-card-header {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.bf-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.bf-card-meta {
  font-size: 11px;
  color: var(--text-tertiary-ink);
}

.bf-card-error {
  margin: 0;
  font-size: 12px;
  color: var(--color-danger-ink, var(--color-warning-ink));
}

.bf-card-diff {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.bf-card-form {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.bf-card-form .el-button + .el-button {
  margin-left: 0;
}

.bf-card-footer {
  display: flex;
  justify-content: flex-end;
}

.bf-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.bf-foot {
  display: flex;
  justify-content: center;
  padding-top: 4px;
  border-top: 1px dashed var(--border-default);
}

.bf-dialog-note {
  margin: 8px 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
