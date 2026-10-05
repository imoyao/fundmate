<script setup lang="ts">
import { computed } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import AllocationGroupPanel from "./AllocationGroupPanel.vue";
import type { SummaryCategory } from "../composables/useImportWizard";

const {
  showAllocationGroupPanel,
  summaryCounts,
  fixBreakdown,
  totalRows,
  selectedCount,
  isCategoryExpanded,
  toggleCategoryFilter,
  expandAllData,
  categoryCheckState,
  toggleCategorySelection,
  toggleFixPanel
} = useImportWizardContext();

/** 标题（#783 §3.1 原型文案）：有问题时追加「，发现以下问题」 */
const pageTitle = computed(() =>
  summaryCounts.value.fix + summaryCounts.value.duplicate > 0
    ? "数据预览 — 系统已自动分析，发现以下问题"
    : "数据预览 — 系统已自动分析"
);

interface CardDef {
  key: SummaryCategory;
  label: string;
  icon: string;
  iconClass: string;
  desc: string;
}

/** 三卡片（#783 §3.2 原型；emoji 禁用，改用语义图标） */
const cards: CardDef[] = [
  {
    key: "complete",
    label: "数据完整",
    icon: "ep:circle-check-filled",
    iconClass: "is-complete",
    desc: "可直接导入"
  },
  {
    key: "duplicate",
    label: "疑似重复",
    icon: "ep:warning-filled",
    iconClass: "is-duplicate",
    desc: "已自动跳过，如需保留请手动勾选"
  },
  {
    key: "fix",
    label: "需要修正",
    icon: "ep:circle-close-filled",
    iconClass: "is-fix",
    desc: "补全或修正后才能可靠导入"
  }
];

/** 「需要修正」卡的细分错误统计（#783 §3.2），四类之和恒等于该卡条数 */
const fixChips = computed(() => {
  const b = fixBreakdown.value;
  const chips: Array<{ label: string; count: number }> = [];
  if (b.error > 0) chips.push({ label: "解析错误", count: b.error });
  if (b.missingCode > 0)
    chips.push({ label: "代码未匹配", count: b.missingCode });
  if (b.missingQtyPrice > 0)
    chips.push({ label: "数量或价格缺失", count: b.missingQtyPrice });
  if (b.mismatch > 0) chips.push({ label: "数据不一致", count: b.mismatch });
  return chips;
});

/** 每卡复选框三态算一次供模板复用（避免每 render 对全表多扫几遍） */
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
    <section class="summary-panel" aria-label="数据预览摘要">
      <div class="summary-head">
        <span class="summary-title">{{ pageTitle }}</span>
      </div>

      <div class="summary-cards">
        <div
          v-for="card in cards"
          :key="card.key"
          class="summary-card"
          :class="`summary-card--${card.key}`"
          :data-category="card.key"
        >
          <div class="card-head">
            <el-checkbox
              :model-value="cardCheckStates[card.key] === 'all'"
              :indeterminate="cardCheckStates[card.key] === 'some'"
              :aria-label="`${card.label}全选`"
              @change="onCardCheck(card.key, $event)"
            />
            <IconifyIconOffline
              :icon="card.icon"
              class="card-icon"
              :class="card.iconClass"
            />
            <span class="card-label">{{ card.label }}</span>
            <strong class="card-count">{{ summaryCounts[card.key] }}</strong>
            <span class="card-unit">条</span>
          </div>

          <p class="card-desc">{{ card.desc }}</p>

          <!-- 需要修正卡：细分错误统计 + 批量修正入口（#1791 要做的事 3） -->
          <div v-if="card.key === 'fix' && fixChips.length" class="card-chips">
            <span v-for="chip in fixChips" :key="chip.label" class="chip">
              {{ chip.label }} {{ chip.count }}
            </span>
          </div>

          <div class="card-actions">
            <el-button
              link
              type="primary"
              size="small"
              @click="toggleCategoryFilter(card.key)"
            >
              {{ isCategoryExpanded(card.key) ? "收起" : "展开查看" }}
            </el-button>
            <el-button
              v-if="card.key === 'fix'"
              link
              type="warning"
              size="small"
              @click="toggleFixPanel"
            >
              批量修正
            </el-button>
          </div>
        </div>
      </div>

      <div class="summary-foot">
        <span class="foot-selected">
          已选择 <strong>{{ selectedCount }}</strong> 条
        </span>
        <el-button size="small" @click="expandAllData">
          展开全部数据（{{ totalRows }}）
        </el-button>
      </div>
    </section>

    <AllocationGroupPanel v-if="showAllocationGroupPanel" />
  </div>
</template>

<style scoped>
.step3-topbar {
  display: flex;

  /* 验收③：摘要面板在表格滚动区之外且不参与收缩——展开任一类别时面板常驻 */
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 12px;
  align-items: stretch;
}

/* 三卡片占整行；配置目标面板（子组件根）保留原有的 240px 弹性基宽 */
.step3-topbar > .summary-panel {
  flex: 1 1 100%;
  min-width: 100%;
}

.step3-topbar > :deep(.allocation-group-panel),
.step3-topbar > :deep(.allocation-group-empty) {
  flex: 1 1 240px;
  min-width: 240px;
}

.summary-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.summary-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
}

.summary-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.card-head {
  display: flex;
  gap: 6px;
  align-items: center;
}

.card-icon {
  font-size: 16px;
}

.card-icon.is-complete {
  color: var(--color-success-ink);
}

.card-icon.is-duplicate {
  color: var(--color-warning-ink);
}

.card-icon.is-fix {
  color: var(--color-danger-ink);
}

.card-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-count {
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.card-unit {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.card-desc {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.card-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 1px 8px;
  font-size: 11px;
  color: var(--color-danger-ink);
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger-30);
  border-radius: 999px;
}

.card-actions {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-top: auto;
}

.summary-foot {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px dashed var(--border-default);
}

.foot-selected {
  font-size: 13px;
  color: var(--text-secondary);
}

.foot-selected strong {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
</style>
