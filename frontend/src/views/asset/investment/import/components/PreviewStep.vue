<script setup lang="ts">
import SummaryPanel from "./SummaryPanel.vue";
import PreviewTable from "./PreviewTable.vue";
import BatchFixPanel from "./BatchFixPanel.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  currentStep,
  selectedLedgerName,
  toggleAllocationPanel,
  showAllocationGroupPanel,
  showFixPanel,
  selectedCount,
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
  openCreateCashFromBanner,
  // #2836：口径收到 composable 里（= 当前勾不了的行数），与「跳过这 N 条」
  // 的实际动作同源。原先这里是 duplicate + blocked + error 的加法，
  // 漏掉「代码未匹配」——底栏说 168 条、概览条说需要修正 1 条，那 1 条凭空消失。
  pendingFixCount,
  // #2840：与 selectedCount 同一分母的两个补数，底栏据此可互算、并说清转账在不在里面
  unselectedCount,
  selectedTransferCount,
  // #2854：源文件行数对账 + 解析阶段未能纳入导入的行
  rowReconciliation,
  parseErrors
} = useImportWizardContext();
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

    <!-- #2854：源文件行数对账。未知操作名曾整行静默消失，预览 total 是丢过行的数，
         用户连「少了几行」都不知道。这里把差额与未登记的操作名显式写出来。 -->
    <SoftBanner
      v-if="rowReconciliation"
      class="row-reconciliation-banner"
      variant="warning"
      icon="ep:warning-filled"
    >
      <span class="banner-text">
        文件共 {{ rowReconciliation.source }} 行 = 可导入
        {{ rowReconciliation.imported }} 行 + 有意忽略
        {{ rowReconciliation.ignored }} 行 + 未能识别
        {{ rowReconciliation.failed }} 行
        <template v-if="!rowReconciliation.balanced">
          （对不平，请检查源文件是否有合并行或空行）
        </template>
      </span>
      <p v-if="rowReconciliation.ops.length" class="text-xs mt-1">
        未登记的操作类型：{{ rowReconciliation.ops.join("、") }}
        <span v-if="parseErrors.length">
          ，涉及行号 {{ parseErrors.map(e => e.line).join("、") }} </span
        >。请在映射表登记后再导入，不要手工编造标的。
      </p>
    </SoftBanner>

    <!-- #2281 引导态：能力宣告 + 关联入口（未关联现金账户时；不可关闭，tooltip 指向此处）。
         #2724 起壳由 SoftBanner 承担，select 与跳转按钮走 #actions slot -->
    <SoftBanner
      v-if="showCashBindingBanner"
      class="cash-binding-banner"
      variant="info"
      icon="ep:warning"
    >
      <span class="banner-text">
        检测到银证转账交易，支持导入：勾选转账行后，现金账户将自动生成反向流水（银行↔证券两本账自动配平）。请先为当前账户「{{
          selectedLedgerName
        }}」关联现金账户：
      </span>
      <template #actions>
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
      </template>
    </SoftBanner>

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
        <!-- 只留一份计数：分档构成（重复/待补全/错误）已在表格上方概览条与修正面板里，
             这里再列一遍等于同一批数字说第三遍（2026-11-02 UI 重排）。

             #2840：补数必须与「已选择」同分母（= 全量行 − 已选），否则三个数字来自
             三个口径、谁也验证不了谁。银证转账是否包含，由括号里显式写出，不靠推断。 -->
        <div class="action-summary">
          <span class="summary-primary">
            已选择 <strong>{{ selectedCount }}</strong> 条<template
              v-if="selectedTransferCount > 0"
              ><span class="summary-note"
                >（含
                <strong>{{ selectedTransferCount }}</strong>
                条银证转账）</span
              ></template
            ><template v-if="unselectedCount > 0"
              ><span class="summary-sep" aria-hidden="true">·</span
              ><span class="summary-note"
                >另有
                <strong>{{ unselectedCount }}</strong>
                条未勾选</span
              ></template
            >
          </span>
        </div>
        <div class="flex gap-3">
          <!-- #783 §十 边界一：全表皆重复时不存在「正常数据」，只留跳过出口 -->
          <el-button v-if="allRowsDuplicate" @click="skipAllDuplicatesAndBack">
            全部跳过，返回上一步
          </el-button>
          <!-- #2840：这个按钮不是「第二种导入」，而是「重置勾选为正常行」——
               说「跳过 N 条、导入 M 条」会把 N（待修行，不含转账）和 M（正常行）
               当成一次导入的两个部分，实际动作却会连已勾的转账一起清掉。
               故只用「正常行」这一侧的数字，并在提示里交代副作用。
               与主按钮口径相同时（已选就是全部正常行）它没有意义，不出现。 -->
          <el-tooltip
            v-else-if="pendingFixCount > 0 && selectedCount !== validRowsCount"
            content="会取消银证转账等其他勾选，只保留可自动导入的正常行"
            placement="top"
          >
            <el-button :loading="importing" @click="importNormalOnly"
              >{{
                importing
                  ? "正在导入..."
                  : `只导入正常行（${validRowsCount} 条）`
              }}
            </el-button>
          </el-tooltip>
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

/* 步骤3 智能体检：未关联现金账户的银证转账提示横幅。
   #2724 起壳由 SoftBanner info 承担，只保留「页面内位置」与内部控件尺寸：
   删除的本地壳样式：display/flex-wrap/gap/align-items/padding/background/border/
   radius，以及 `.banner-icon`（--color-warning-ink 图标改由 variant 的 info 图标承担）。 */
.cash-binding-banner {
  /* 位置：位于 header 与 step3-body 之间，左右与 header 对齐（12px 16px 0）。
     组件默认 margin-bottom 16px，这里补齐上方 12px 与左右 16px。 */
  margin: 12px 16px 16px;
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

  /* 12px：概览条与修正面板都是「紧贴表格的上下文」，间距只做分组、不做留白 */
  gap: 12px;
  min-height: calc(100vh - 240px);
  padding: 16px;
  overflow: hidden;
}

/*
 * #1792 内联修正面板：概览条下方、表格上方，三者同屏。
 * 有界内滚（max-height + overflow-y）——内容高时面板内部滚动，不产生页面级滚动条，
 * 表格仍是唯一可滚动的主体区域（#783 §1「仅表格区域纵向滚动」的口径按此放宽）。
 * 2026-11-02 起改用固定 220px（不再用 %）：百分比在 flex 容器里按 `.step3-body`
 * 的 min-height 解析，实测 34% 仍算出 245px+，把表格压到只剩 1 行——「看得见面板
 * 却看不见要改的行」。定死 px 后表格稳定保有 3~4 行，面板内部自己滚。
 */
.step3-fixpanel {
  flex: 0 1 auto;

  /* 180px 是「面板能看两张卡片 + 表格还留得下 2 行」的平衡点（实测 1440×900 与
     1280×720 两档）。面板不是越大越好：修完一条要能抬头看表格里那行变没变，
     全遮住的话用户只能收起面板再核对，来回两趟。 */
  max-height: 180px;
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
  align-items: center;
}

.summary-primary {
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.summary-primary strong {
  font-variant-numeric: tabular-nums;
}

/* #2840：补数与构成用次要色，主句「已选择 N 条」仍是唯一焦点；
   tabular-nums 让两个数字对齐，便于相加核对 */
.summary-note {
  font-weight: 400;
  color: var(--text-secondary);
}

.summary-note strong {
  font-weight: 600;
  color: var(--text-secondary);
}

.summary-sep {
  margin: 0 6px;
  color: var(--text-tertiary);
}
</style>
