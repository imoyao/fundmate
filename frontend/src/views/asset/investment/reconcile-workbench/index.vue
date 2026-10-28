<template>
  <div class="recon-workbench-page">
    <!-- 页头（拆分见 WorkbenchHead）：标题 + AI 识别 / 运行对账 -->
    <WorkbenchHead
      :running="running"
      @recognize="recognizerVisible = true"
      @run="handleRun"
    />

    <!-- 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗；点击切换到待处理域（#1259） -->
    <div
      v-if="hasPending"
      class="workbench-banner workbench-banner--clickable"
      role="alert"
      tabindex="0"
      @keydown.enter="focusFirstPendingDomain"
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
            <DomainTabLabel
              :label="tab.label"
              :count="domainPending(tab.key)"
            />
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
                :acting="eActing"
                @cover="handleEAccountCover"
                @ignore="handleEAccountIgnore"
              />
            </template>

            <!-- 域 D：跨账本重复交易（#2151）——未忽略组 + 已忽略清单，逐组核对 -->
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

            <!-- 域 E：红利税待办（#541）——不是「差异」而是「账外缺一笔」，
                 故不复用域 B 的差异表；每行陈述事实，并把补记做成一个按钮 -->
            <DomainEDividendTaxTable
              v-else-if="tab.key === 'E'"
              :items="taxItems"
              :total-cents="taxTotalCents"
              :pending-count="taxPendingCount"
              :loading="taxLoading"
              @recorded="loadDividendTax"
            />

            <!-- 域 C：对账单/交割单导入（2026-10-28 接入真实列表）。
                 这一域的用户动作是「去导入」，所以入口放在这个 Tab 里、做成正式按钮；
                 导入提交后后端自动跑一次对账，孤儿持仓（有仓位无流水）回到这里。
                 ⚠️ 后端域 C 只做孤儿检测，不做数量比对——数量差异在域 B，
                 故文案只说「孤儿」不说「差异全在这里」。 -->
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

            <!-- 兜底：新增域忘了写视图时给一句话，而不是静默空白 -->
            <el-empty v-else description="该域暂未提供内容" :image-size="80" />
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
import { ref, computed, onMounted, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
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
import DomainDGhostTable from "./components/DomainDGhostTable.vue";
import DomainEDividendTaxTable from "./components/DomainEDividendTaxTable.vue";
import WorkbenchHead from "./components/WorkbenchHead.vue";
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

/** 当前激活域：初值优先取 URL 的 `?domain=`，非法值一律回落到 B（#2151）。
 *  这样横幅「去处理」跳 `?domain=D` 才真的落在域 D，而不是跳过来还停在 B。 */
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

/* 切域只改本地状态，**刻意不写回 URL**。
 *
 * WHY：布局层 `layout/components/lay-content/index.vue` 以 `route.fullPath` 作
 * `<component :key>`。任何 query 改写 ⇒ fullPath 变 ⇒ 整页组件销毁重建，
 * `onMounted` 里五个加载器全部重跑——用户看到的就是「点一下 tab 整页刷新」：
 * 旧页面组件被移除、`recon-workbench-page` 重新挂载、六个请求重发（#2706 实测）。
 * 同一个坑在 `views/agent/index.vue` 已留过注（对话页改写 query 会把会话消息清空）。
 *
 * 那 `?domain=` 还留不留？留，但只作**入站寻址**：横幅从别处跳过来时带 query，
 * 初值读它落地（见上方 `activeDomain`），落地后域状态由 tab 自己持有。
 * 代价是刷新/分享不再保留当前 tab——与仓内惯例一致（`inventory` 的 `?tab=`
 * 同样「只读不摘」）。要同时满足两边，只能改布局层 key 粒度，那是全局改动，
 * 会波及 iframe 多页签（`lay-frame` 按 fullPath 管理），不值得为单个页面动。
 */

/** 反向同步：`?domain=` 变化时 tab 跟着走。
 *  只处理合法值——非法值不动 tab，避免把用户从有效域弹走。
 *  注：当前布局 key 粒度下 query 变化必伴随重挂载，故本 watch 极少触发；
 *  保留它是因为一旦布局层 key 改为 path，这条入站契约仍需成立。 */
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
  loadRecognizerCandidates();
});
</script>

<style scoped>
.recon-workbench-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
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

.workbench-banner__icon {
  font-size: var(--text-body);
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

/* ===== 域内引导区（域 C：导入入口） =====
   这一域唯一的前置动作是「去导入」，所以入口做成正式按钮而不是 text 链接——
   无边框小字在卡片里读起来像临时占位，用户不确定能不能点（2026-10-28 反馈）。 */
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
