<script setup lang="ts">
/**
 * 数据预览概览条（2026-11-02 由「三张卡片」改为「一行胶囊」）。
 *
 * 改版动因：旧版把同一批数字说了三遍——卡片条数、卡片内 chips 细分、底部「已选择」；
 * 且三张卡各自带「展开查看 / 收起」「批量修正」按钮，同屏三个主按钮争夺注意力，
 * 而点卡片本体什么都不发生。更糟的是「需要修正」卡要先把 5+1+180 自己算一遍，
 * 才知道 186 条是由什么构成的。
 *
 * 新版把卡片压成一行**可点的筛选器**：
 * - 每颗胶囊 = 一个类别，点主体即筛表（原「展开查看 / 收起」按钮退场）；
 * - 胶囊左侧的复选框保留原「按类全选」能力（勾选与筛选是两个动作，故分成两个靶区）；
 * - 「需要修正」下方直接写出 `N 条 = 解析错误 a · 代码未匹配 b · …`，等式不再靠用户算；
 * - 类别色点即图例：绿=可导入、橙=可导入但需留意、红=阻断，与状态列三态同源。
 *
 * 被删掉的两处（不是丢功能）：「已选择 N 条」只在底部操作条保留一份；
 * 「展开全部数据」由首颗「全部」胶囊承担。
 */
import { computed } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import AllocationGroupPanel from "./AllocationGroupPanel.vue";
import type { SummaryCategory } from "../composables/useImportWizard";

const {
  showAllocationGroupPanel,
  summaryCounts,
  fixBreakdown,
  completeTransferCount,
  selectedLedgerLinkedCash,
  allRowsDuplicate,
  tableStatusFilter,
  isCategoryExpanded,
  toggleCategoryFilter,
  expandAllData,
  categoryCheckState,
  toggleCategorySelection
} = useImportWizardContext();

interface CapsuleDef {
  key: SummaryCategory;
  label: string;
  /** 语义色：绿=可导入 / 橙=可导入但需留意 / 红=阻断 */
  tone: "success" | "warning" | "danger";
  /** 悬停说明：胶囊只有 4 个字，语义靠它补 */
  hint: string;
}

const capsules: CapsuleDef[] = [
  {
    key: "complete",
    label: "可直接导入",
    tone: "success",
    hint: "校验通过，勾选的按成交额入库、手续费单列"
  },
  {
    key: "duplicate",
    label: "疑似重复",
    tone: "warning",
    hint: "与已有记录疑似重复，默认跳过，勾选可保留"
  },
  {
    key: "fix",
    label: "需要修正",
    tone: "danger",
    hint: "其中信息不全的行无法可靠导入，点此筛选并打开修正面板"
  }
];

/** 「全部」胶囊的选中态：没有任何类别筛选时成立 */
const allActive = computed(() => tableStatusFilter.value === "");

/**
 * 「全部」的条数**由三类相加得出**，不读 `totalRows`：后者是解析结果的计数 ref，
 * 在忽略行 / 增删行等路径上靠多处赋值维持同步（1234 / 1443 / 2548 三处），一旦漏一处
 * 就会出现「全部 ≠ 三类之和」——而这正是概览条要消灭的那类不一致。
 * 相加则恒等，等式结构性成立。
 */
const totalCount = computed(() => {
  const c = summaryCounts.value;
  return c.complete + c.duplicate + c.fix;
});

/** 「需要修正」的构成（四分区之和恒等于该胶囊条数，故等号成立而非约等于） */
const fixChips = computed(() => {
  const b = fixBreakdown.value;
  const chips: Array<{ label: string; count: number }> = [];
  if (b.error > 0) chips.push({ label: "解析错误", count: b.error });
  if (b.missingCode > 0)
    chips.push({ label: "代码未匹配", count: b.missingCode });
  if (b.missingQtyPrice > 0)
    chips.push({ label: "数量或价格缺失", count: b.missingQtyPrice });
  if (b.mismatch > 0)
    chips.push({ label: "差额超出手续费", count: b.mismatch });
  return chips;
});

/**
 * #2281：转账行的能力提示。未关联现金账户时是待办（警示色），已关联时是能力（主色）。
 */
const transferNote = computed(() => {
  const n = completeTransferCount.value;
  if (n === 0) return null;
  return {
    text: selectedLedgerLinkedCash.value
      ? `含 ${n} 条银证转账，可勾选导入`
      : `含 ${n} 条银证转账，需先关联现金账户`,
    warn: !selectedLedgerLinkedCash.value
  };
});

/** 每颗胶囊的复选框三态算一次供模板复用（避免每 render 对全表多扫几遍） */
const cardCheckStates = computed(() => ({
  complete: categoryCheckState("complete"),
  duplicate: categoryCheckState("duplicate"),
  fix: categoryCheckState("fix")
}));

function onCardCheck(key: SummaryCategory, val: string | number | boolean) {
  toggleCategorySelection(key, Boolean(val));
}
</script>

<template>
  <div class="step3-topbar">
    <section class="summary-panel" aria-label="数据预览概览">
      <div class="ov-bar">
        <!-- 首颗：全部（未筛选态）。条数由三类相加得出，故三胶囊之和与它恒等 -->
        <button
          type="button"
          class="ov-all"
          :class="{ 'is-active': allActive }"
          data-category="all"
          @click="expandAllData"
        >
          全部
          <strong class="ov-count">{{ totalCount }}</strong>
        </button>

        <span class="ov-divider" aria-hidden="true" />

        <!-- 三类别：左侧复选框（按类全选）+ 右侧主体（筛选表格） -->
        <div
          v-for="cap in capsules"
          :key="cap.key"
          class="ov-chip"
          :class="[
            `ov-chip--${cap.tone}`,
            { 'is-active': isCategoryExpanded(cap.key) }
          ]"
          :data-category="cap.key"
          :title="cap.hint"
        >
          <el-checkbox
            class="ov-chip-check"
            :model-value="cardCheckStates[cap.key] === 'all'"
            :indeterminate="cardCheckStates[cap.key] === 'some'"
            :aria-label="`${cap.label}全选`"
            @change="onCardCheck(cap.key, $event)"
          />
          <button
            type="button"
            class="ov-chip-btn"
            :aria-pressed="isCategoryExpanded(cap.key)"
            @click="toggleCategoryFilter(cap.key)"
          >
            <span class="ov-dot" aria-hidden="true" />
            <span class="ov-label">{{ cap.label }}</span>
            <strong class="ov-count">{{ summaryCounts[cap.key] }}</strong>
          </button>
        </div>

        <span
          v-if="transferNote"
          class="ov-note"
          :class="{ 'ov-note--warn': transferNote.warn }"
          >{{ transferNote.text }}</span
        >
      </div>

      <!-- 等式行：把这个胶囊条数由什么构成直接写出来，替代旧版卡片内 chips + 用户自己加的算式 -->
      <p v-if="fixChips.length" class="ov-breakdown">
        <span class="ov-breakdown-head"
          >需要修正 <strong>{{ summaryCounts.fix }}</strong> 条 =</span
        >
        <span
          v-for="(chip, i) in fixChips"
          :key="chip.label"
          class="ov-breakdown-item"
        >
          {{ chip.label }} <strong>{{ chip.count }}</strong>
          <span v-if="i < fixChips.length - 1" class="ov-sep">·</span>
        </span>
      </p>

      <!-- #783 §十 边界一：全表皆重复时说明「为什么没有可导入的行」，与底栏出口配对 -->
      <p v-if="allRowsDuplicate" class="ov-alert">
        本次识别的 {{ totalCount }}
        条记录全部与已有记录重复，已默认跳过。如需保留，请在下方逐条勾选；也可以点击「重新选择文件」换一份数据。
      </p>
    </section>

    <AllocationGroupPanel v-if="showAllocationGroupPanel" />
  </div>
</template>

<style scoped>
.step3-topbar {
  display: flex;

  /* 验收③：概览条在表格滚动区之外且不参与收缩——展开任一类别时都常驻 */
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 12px;
  align-items: stretch;
}

/* 概览条占整行；配置目标面板（子组件根）保留原有的 240px 弹性基宽 */
.step3-topbar > .summary-panel {
  flex: 1 1 100%;
  min-width: 100%;
}

.step3-topbar > :deep(.allocation-group-panel),
.step3-topbar > :deep(.allocation-group-empty) {
  flex: 1 1 240px;
  min-width: 240px;
}

/* 一行胶囊：白色卡面，只留最轻的边框，把纵向空间让给表格 */
.summary-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.ov-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

/* ── 「全部」胶囊 ── */
.ov-all {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 30px;
  padding: 0 12px;
  font-family: inherit;
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: 999px;
  transition:
    border-color 0.15s,
    background 0.15s;
}

.ov-all:hover {
  border-color: var(--color-primary-20);
}

.ov-all.is-active {
  color: var(--color-primary-ink);
  background: var(--color-primary-10);
  border-color: var(--color-primary);
}

.ov-divider {
  align-self: center;
  width: 1px;
  height: 18px;
  margin: 0 2px;
  background: var(--border-default);
}

/* ── 三类别胶囊：外层只管边框与选中态，内层是两个独立靶区 ── */
.ov-chip {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  height: 30px;
  padding: 0 10px 0 8px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: 999px;
  transition:
    border-color 0.15s,
    background 0.15s;
}

.ov-chip:hover {
  border-color: var(--color-primary-20);
}

/* 选中 = 表格正被这个类别筛选，用主色描边而非填充，避免与语义色点抢注意力 */
.ov-chip.is-active {
  background: var(--color-primary-10);
  border-color: var(--color-primary);
}

.ov-chip :deep(.el-checkbox) {
  height: auto;
  margin-right: 0;
}

.ov-chip-btn {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 100%;
  padding: 0 2px;
  font-family: inherit;
  font-size: var(--text-label);
  color: var(--text-primary);
  cursor: pointer;
  background: none;
  border: 0;
}

.ov-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 语义色与状态列三态同源：绿=可导入 / 橙=可导入但需留意 / 红=阻断 */
.ov-chip--success .ov-dot {
  background: var(--color-success-ink);
}

.ov-chip--warning .ov-dot {
  background: var(--color-warning-ink);
}

.ov-chip--danger .ov-dot {
  background: var(--color-danger-ink);
}

.ov-label {
  white-space: nowrap;
}

.ov-count {
  font-size: var(--text-small);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 转账提示胶囊：与三类别的实心胶囊区分——它是说明，不是入口 */
.ov-note {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--color-primary-ink);
  background: var(--color-primary-10);
  border-radius: 999px;
}

.ov-note--warn {
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
}

/* ── 等式行 ── */
.ov-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.ov-breakdown-head strong,
.ov-breakdown-item strong {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.ov-breakdown-item {
  display: inline-flex;
  gap: 4px;
  align-items: baseline;
}

.ov-sep {
  margin-left: 4px;
  color: var(--text-tertiary-ink);
}

/* 边界提示（#783 §十）：告警级文字色 + 暖沙金底边 */
.ov-alert {
  padding: 8px 10px;
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm);
}
</style>
