<template>
  <div class="recon-workbench-page">
    <WorkbenchHead
      :running="running"
      @recognize="recognizerVisible = true"
      @run="handleRun"
    />

    <WorkbenchBanner
      v-if="hasPending"
      :total="totalPending"
      @go="focusFirstPendingDomain"
    />

    <div class="workbench-metrics">
      <MetricGrid :cols="3">
        <MetricCard
          title="数据日期"
          :value="dataDateLabel"
          caption="最近一次对账数据日期"
        />
        <MetricCard
          title="待裁决差异"
          :value="pendingCount"
          unit="项"
          level="待处理"
          :featured="true"
        />
        <MetricCard
          title="已忽略"
          :value="ignoredCount"
          unit="项"
          caption="可撤销（P2 接入）"
        />
      </MetricGrid>
    </div>

    <div class="workbench-tabs">
      <el-tabs v-model="activeDomain" class="workbench-tabs__inner">
        <el-tab-pane v-for="tab in domainTabs" :key="tab.key" :name="tab.key">
          <template #label>
            <DomainTabLabel
              :label="tab.label"
              :count="domainPending(tab.key)"
            />
          </template>
          <CardBlock :title="tab.title" :description="tab.description">
            <template #action>
              <AssetTypeBadge :type="tab.badgeType" variant="tag" />
            </template>

            <DomainBDiscTable
              v-if="tab.key === 'B'"
              :items="bDiscs"
              :loading="loading"
              @supplement="openSupplement"
              @ignore="handleIgnore"
            />

            <template v-else-if="tab.key === 'A'">
              <!-- 识别候选（holding → 域 A，#1252）：AI 识别结果落草稿，确认后入库并刷新域 A 对账 -->
              <RecognizerCandidatesPanel
                kind="holding"
                :candidates="recognizerCandidates"
                :committing="committing"
                @discard="discardCandidates"
                @commit="commitCandidates"
              />
              <EAccountDomainPanel
                :items="eItems"
                :loading="eLoading"
                :acting="eActing"
                @cover="handleEAccountCover"
                @ignore="handleEAccountIgnore"
              />
            </template>

            <DomainDGhostTable
              v-else-if="tab.key === 'D'"
              :items="ghostGroups"
              :ignored-items="ghostIgnored"
              :loading="ghostLoading"
              :deleting-id="ghostDeletingId"
              :undoing-id="ghostUndoingId"
              @ignore="handleGhostIgnore"
              @undo-ignore="handleGhostUndoIgnore"
              @delete-txn="handleGhostDeleteTxn"
            />

            <!-- 域 E：红利税待办（#541）——账外缺一笔，不复用域 B 的差异表 -->
            <DomainEDividendTaxTable
              v-else-if="tab.key === 'E'"
              :items="taxItems"
              :total-cents="taxTotalCents"
              :pending-count="taxPendingCount"
              :loading="taxLoading"
              @recorded="loadDividendTax"
            />

            <!-- 域 F：悬空引用（#2866）——分组预览影响后二次回补 -->
            <DomainFDanglingRefs
              v-else-if="tab.key === 'F'"
              :data="danglingRefs"
              :loading="danglingLoading"
              @fix="openDanglingFix"
            />

            <!-- 域 C：导入交割单后自动比对孤儿持仓；后端只做孤儿检测，数量差异在域 B -->
            <template v-else-if="tab.key === 'C'">
              <!-- 识别候选（txn → 域 C，#1251）：AI 识别结果落草稿，确认后入库并触发域 C 对账 -->
              <RecognizerCandidatesPanel
                kind="txn"
                :candidates="recognizerCandidates"
                :committing="committing"
                @discard="discardCandidates"
                @commit="commitCandidates"
              />
              <div v-if="tab.entry" class="domain-entry">
                <div class="domain-entry__text">
                  <p class="domain-entry__title">{{ tab.entry.title }}</p>
                  <p class="domain-entry__hint">{{ tab.entry.hint }}</p>
                </div>
                <div class="domain-entry__actions">
                  <el-button
                    v-for="(link, i) in tab.entry.links"
                    :key="i"
                    size="small"
                    :type="i === 0 ? 'primary' : 'default'"
                    :plain="i === 0"
                    @click="goTo(link.to)"
                  >
                    {{ link.label }}
                  </el-button>
                </div>
              </div>
              <DomainBDiscTable
                :items="cDiscs"
                :loading="loading"
                empty-text="暂无孤儿持仓"
                @supplement="openSupplement"
                @ignore="handleIgnore"
              />
            </template>

            <el-empty v-else description="该域暂未提供内容" :image-size="80" />
          </CardBlock>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 就地补充弹窗（§6.4）：工作台内补录，表单状态与重置内聚在弹窗内 -->
    <SupplementDialog
      v-model="supplementVisible"
      :target="supplementTarget"
      @submitted="loadDiscrepancies"
    />

    <!-- 悬空引用修复向导（#2866）：预览 → 回补 → 撤销，状态内聚在弹窗 -->
    <DanglingRefFixDialog
      v-model="danglingFixVisible"
      :group="danglingFixGroup"
      @submitted="loadDanglingRefs"
    />

    <!-- AI 识别入口（P3 / #1250）：识别 → 预览核对 → 确认进草稿，保存后刷新候选 -->
    <RecognizerImportModal
      v-model="recognizerVisible"
      @saved="loadRecognizerCandidates"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import RecognizerImportModal from "@/components/QuickEntry/RecognizerImportModal.vue";
import type { DiscrepancyItem, DanglingRefGroup } from "@/api/reconciliation";
import DomainBDiscTable from "./components/DomainBDiscTable.vue";
import EAccountDomainPanel from "./components/EAccountDomainPanel.vue";
import RecognizerCandidatesPanel from "./components/RecognizerCandidatesPanel.vue";
import DomainDGhostTable from "./components/DomainDGhostTable.vue";
import DomainEDividendTaxTable from "./components/DomainEDividendTaxTable.vue";
import DomainFDanglingRefs from "./components/DomainFDanglingRefs.vue";
import DanglingRefFixDialog from "./components/DanglingRefFixDialog.vue";
import WorkbenchHead from "./components/WorkbenchHead.vue";
import WorkbenchBanner from "./components/WorkbenchBanner.vue";
import DomainTabLabel from "./components/DomainTabLabel.vue";
import SupplementDialog from "./components/SupplementDialog.vue";
import { domainTabs, type WorkbenchDomainKey } from "./constants/domainTabs";
import { normalizeDomain } from "./utils/domainQuery";
import { pickFirstPendingDomain } from "./utils/domainFocus";
import { useWorkbenchDomains } from "./composables/useWorkbenchDomains";

defineOptions({ name: "ReconcileWorkbench" });

const router = useRouter();

/** 三域数据与操作（#980 拆分：加载/对账/忽略/归因/识别入库统一收口在 composable） */
const {
  loading,
  running,
  bDiscs,
  cDiscs,
  eItems,
  eLoading,
  eActing,
  ghostGroups,
  ghostIgnored,
  ghostLoading,
  ghostDeletingId,
  ghostUndoingId,
  taxItems,
  taxTotalCents,
  taxPendingCount,
  taxLoading,
  danglingRefs,
  danglingLoading,
  loadDanglingRefs,
  loadDividendTax,
  recognizerCandidates,
  committing,
  totalPending,
  hasPending,
  dataDateLabel,
  domainPending,
  domainIgnored,
  loadDiscrepancies,
  loadEAccount,
  loadGhostDuplicates,
  loadRecognizerCandidates,
  commitCandidates,
  discardCandidates,
  handleRun,
  handleIgnore,
  handleEAccountCover,
  handleEAccountIgnore,
  handleGhostIgnore,
  handleGhostUndoIgnore,
  handleGhostDeleteTxn
} = useWorkbenchDomains();

const route = useRoute();

/** 当前激活域：初值取 URL `?domain=`，非法值回落 B（#2151） */
const activeDomain = ref<WorkbenchDomainKey>(
  normalizeDomain(route.query.domain) ?? "B"
);

/** 顶部「待裁决差异」= 当前激活域的 pending 数，与下方表格可见可操作行口径一致（#1259） */
const pendingCount = computed(() => domainPending(activeDomain.value));
/** 顶部「已忽略」= 当前激活域的 ignored 数（#1259） */
const ignoredCount = computed(() => domainIgnored(activeDomain.value));

/** AI 识别入口弹窗（P3 / #1250）：开合状态与原版一致，保留在页面层 */
const recognizerVisible = ref(false);

/** 就地补充弹窗（§6.4）：不跳「记一笔」；表单重置在弹窗打开时自动执行 */
const supplementVisible = ref(false);
const supplementTarget = ref<DiscrepancyItem | null>(null);

function openSupplement(row: DiscrepancyItem): void {
  supplementTarget.value = row;
  supplementVisible.value = true;
}

/** 悬空引用修复弹窗（#2866）：整组交给弹窗，刷新由 submitted 触发 */
const danglingFixVisible = ref(false);
const danglingFixGroup = ref<DanglingRefGroup | null>(null);

function openDanglingFix(group: DanglingRefGroup): void {
  danglingFixGroup.value = group;
  danglingFixVisible.value = true;
}

/** 导航到既有入口（并行不破坏现状） */
function goTo(to: string | { name: string }): void {
  router.push(to);
}

/** Banner 点击：切换到第一个有待处理差异的域并定位到表格区（#1259） */
function focusFirstPendingDomain(): void {
  // 选域顺序与「为什么是固定顺序」见 utils/domainFocus.ts
  const target = pickFirstPendingDomain(domainPending);
  if (!target) return;
  activeDomain.value = target;
  nextTick(() => {
    document
      .querySelector(".workbench-tabs")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

/* 切域刻意不写回 URL：布局层以 route.fullPath 作 <component :key>，改写 query 会整页
 * 重建并重跑所有加载器（#2706）。`?domain=` 仅作入站寻址；watch 留给未来 key 粒度改动。 */

/** 反向同步 `?domain=`（只认合法值）；布局 key 改为 path 后这条入站契约仍需成立 */
watch(
  () => route.query.domain,
  raw => {
    const next = normalizeDomain(raw);
    if (next && next !== activeDomain.value) activeDomain.value = next;
  }
);

onMounted(() => {
  loadDiscrepancies();
  loadEAccount();
  loadGhostDuplicates();
  loadDividendTax();
  loadDanglingRefs();
  loadRecognizerCandidates();
});
</script>

<style scoped>
.recon-workbench-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

/* 状态栏 */
.workbench-metrics {
  margin-bottom: 20px;
}

/* 三域 Tab */
.workbench-tabs__inner {
  padding: 4px;
}

/* 域 C 引导区：入口动作是「去导入」，做成正式按钮而非 text 链接 */
.domain-entry {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-compact);
  margin-bottom: var(--space-compact);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.domain-entry__text {
  min-width: 0;
}

.domain-entry__title {
  margin: 0 0 2px;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.domain-entry__hint {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.domain-entry__actions {
  display: flex;
  flex-shrink: 0;
  gap: var(--space-2);
}
</style>
