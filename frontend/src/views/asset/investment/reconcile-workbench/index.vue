<template>
  <div class="recon-workbench-page">
    <!-- 页头 -->
    <header class="workbench-head">
      <div class="workbench-head__text">
        <h1 class="workbench-head__title">对账工作台</h1>
        <p class="workbench-head__subtitle">
          统一处理 E账户对账、持仓快照一致性、对账单导入的差异与补充
        </p>
      </div>
      <div class="workbench-head__actions">
        <el-button size="small" @click="recognizerVisible = true">
          <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
          AI 识别
        </el-button>
        <el-button
          size="small"
          type="primary"
          :loading="running"
          @click="handleRun"
        >
          <IconifyIconOffline icon="ep:refresh-right" class="mr-1" />
          运行对账
        </el-button>
      </div>
    </header>

    <!-- 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗；点击切换到待处理域（#1259） -->
    <div
      v-if="hasPending"
      class="workbench-banner workbench-banner--clickable"
      role="alert"
      @click="focusFirstPendingDomain"
    >
      <IconifyIconOffline icon="ep:warning" class="workbench-banner__icon" />
      <div class="workbench-banner__text">
        有 {{ totalPending }} 项差异待处理，点击切换到对应域处理
      </div>
    </div>

    <!-- 顶部状态栏（真实数据：P1 接入 discrepancies 统计） -->
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

    <!-- 三域 Tab（§6.3）：B 已接入真实对账，A/C 保持原入口 -->
    <div class="workbench-tabs">
      <el-tabs v-model="activeDomain" class="workbench-tabs__inner">
        <el-tab-pane v-for="tab in domainTabs" :key="tab.key" :name="tab.key">
          <template #label>
            <span class="domain-tab-label">
              {{ tab.label }}
              <span
                v-if="domainPending(tab.key) > 0"
                class="domain-tab-count"
                >{{ domainPending(tab.key) }}</span
              >
            </span>
          </template>
          <CardBlock :title="tab.title" :description="tab.description">
            <template #action>
              <AssetTypeBadge :type="tab.badgeType" variant="tag" />
            </template>

            <!-- 域 B：真实差异列表（P1 接入） -->
            <DomainBDiscTable
              v-if="tab.key === 'B'"
              :items="bDiscs"
              :loading="loading"
              @supplement="openSupplement"
              @ignore="handleIgnore"
            />

            <!-- 域 A：E账户对账（P2 迁入工作台，复用既有 /api/e-account/ 链路） -->
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
                @cover="handleEAccountCover"
                @ignore="handleEAccountIgnore"
              />
            </template>

            <!-- 域 C：占位内容 -->
            <template v-else>
              <!-- 识别候选（txn → 域 C，#1251）：AI 识别结果落草稿，确认后入库并触发域 C 对账 -->
              <RecognizerCandidatesPanel
                kind="txn"
                :candidates="recognizerCandidates"
                :committing="committing"
                @discard="discardCandidates"
                @commit="commitCandidates"
              />
              <DomainPlaceholder :tab="tab" @go="goTo" />
            </template>
          </CardBlock>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 就地补充弹窗（§6.4）：工作台内补录，绝不跳「记一笔」；
         表单状态与重置内聚在弹窗内（打开即重置，等价原 openSupplement 语义） -->
    <SupplementDialog
      v-model="supplementVisible"
      :target="supplementTarget"
      @submitted="loadDiscrepancies"
    />

    <!-- AI 识别入口（P3 / #1250）：截图/文本识别 → 预览核对 → 确认进草稿；
         保存后刷新候选列表 -->
    <RecognizerImportModal
      v-model="recognizerVisible"
      @saved="loadRecognizerCandidates"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { IconifyIconOffline } from "@/components/ReIcon";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import RecognizerImportModal from "@/components/QuickEntry/RecognizerImportModal.vue";
import type { DiscrepancyItem } from "@/api/reconciliation";
import DomainBDiscTable from "./components/DomainBDiscTable.vue";
import EAccountDomainPanel from "./components/EAccountDomainPanel.vue";
import RecognizerCandidatesPanel from "./components/RecognizerCandidatesPanel.vue";
import DomainPlaceholder from "./components/DomainPlaceholder.vue";
import SupplementDialog from "./components/SupplementDialog.vue";
import { domainTabs } from "./constants/domainTabs";
import { useWorkbenchDomains } from "./composables/useWorkbenchDomains";

defineOptions({ name: "ReconcileWorkbench" });

const router = useRouter();

/** 三域数据与操作（#980 拆分：加载/对账/忽略/归因/识别入库统一收口在 composable） */
const {
  loading,
  running,
  bDiscs,
  eItems,
  eLoading,
  recognizerCandidates,
  committing,
  totalPending,
  hasPending,
  dataDateLabel,
  domainPending,
  domainIgnored,
  loadDiscrepancies,
  loadEAccount,
  loadRecognizerCandidates,
  commitCandidates,
  discardCandidates,
  handleRun,
  handleIgnore,
  handleEAccountCover,
  handleEAccountIgnore
} = useWorkbenchDomains();

/** 当前激活域 */
const activeDomain = ref<"A" | "B" | "C">("B");

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

/** 导航到既有入口（并行不破坏现状） */
function goTo(to: string | { name: string }): void {
  router.push(to);
}

/** Banner 点击：切换到第一个有待处理差异的域并定位到表格区（#1259） */
function focusFirstPendingDomain(): void {
  const order: ("A" | "B" | "C")[] = ["B", "C", "A"];
  const target = order.find(k => domainPending(k) > 0);
  if (!target) return;
  activeDomain.value = target;
  nextTick(() => {
    document
      .querySelector(".workbench-tabs")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

onMounted(() => {
  loadDiscrepancies();
  loadEAccount();
  loadRecognizerCandidates();
});
</script>

<style scoped>
.recon-workbench-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

/* 页头 */
.workbench-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}

.workbench-head__title {
  margin: 0 0 6px;
  font-size: var(--text-display);
  font-weight: 300;
  color: var(--text-primary);
}

.workbench-head__subtitle {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.workbench-head__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗 */
.workbench-banner {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

/* Banner 可点击：点击切换到待处理域（#1259） */
.workbench-banner--clickable {
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.workbench-banner--clickable:hover {
  background: color-mix(in srgb, var(--brand-100) 40%, var(--bg-soft));
  border-color: var(--brand-400);
}

/* Tab 标签内的各域待处理数角标（#1259） */
.domain-tab-label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.domain-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 11px;
  line-height: 1;
  color: var(--text-inverse);
  background: var(--brand-600, #d98b2b);
  border-radius: 999px;
}

.workbench-banner__icon {
  font-size: 16px;
  color: var(--brand-700);
}

.workbench-banner__text {
  flex: 1;
}

/* 状态栏 */
.workbench-metrics {
  margin-bottom: 20px;
}

/* 三域 Tab */
.workbench-tabs__inner {
  padding: 4px;
}
</style>
