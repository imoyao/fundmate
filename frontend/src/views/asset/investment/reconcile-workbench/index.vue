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

    <!-- 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗 -->
    <div v-if="hasPending" class="workbench-banner" role="alert">
      <IconifyIconOffline icon="ep:warning" class="workbench-banner__icon" />
      <div class="workbench-banner__text">
        有 {{ pendingCount }} 项差异待处理，点此前往对账工作台
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
        <el-tab-pane
          v-for="tab in domainTabs"
          :key="tab.key"
          :name="tab.key"
          :label="tab.label"
        >
          <CardBlock :title="tab.title" :description="tab.description">
            <template #action>
              <AssetTypeBadge :type="tab.badgeType" variant="tag" />
            </template>

            <!-- 域 B：真实差异列表（P1 接入） -->
            <template v-if="tab.key === 'B'">
              <div class="domain-b-body">
                <el-empty
                  v-if="!loading && bDiscs.length === 0"
                  description="暂无差异，持仓与流水一致"
                  :image-size="80"
                />
                <div v-else class="disc-table-wrap">
                  <el-table
                    :data="bDiscs"
                    stripe
                    size="small"
                    class="disc-table"
                  >
                    <el-table-column label="代码" prop="symbol" width="110" />
                    <el-table-column label="类型" width="90">
                      <template #default="{ row }">
                        <span class="disc-type">{{
                          typeLabel(row.discrepancy_type)
                        }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column
                      label="理论"
                      prop="expected_value"
                      width="100"
                      align="right"
                    />
                    <el-table-column
                      label="实际"
                      prop="actual_value"
                      width="100"
                      align="right"
                    />
                    <el-table-column label="差异" width="100" align="right">
                      <template #default="{ row }">
                        <span :class="diffClass(row.diff)">{{
                          formatDiff(row.diff)
                        }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="状态" width="90">
                      <template #default="{ row }">
                        <span
                          class="disc-status"
                          :class="`disc-status--${row.status}`"
                        >
                          {{ statusLabel(row.status) }}
                        </span>
                      </template>
                    </el-table-column>
                    <el-table-column label="操作" width="140">
                      <template #default="{ row }">
                        <el-button
                          v-if="row.status === 'pending'"
                          size="small"
                          text
                          @click="handleIgnore(row as DiscrepancyItem)"
                        >
                          忽略
                        </el-button>
                        <span v-else class="disc-muted">已处理</span>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </div>
            </template>

            <!-- 域 A/C：占位内容 -->
            <template v-else>
              <div class="domain-placeholder">
                <div class="domain-placeholder__status">
                  <span
                    class="domain-status-tag"
                    :class="`domain-status-tag--${tab.status}`"
                  >
                    {{ tab.statusLabel }}
                  </span>
                  <span class="domain-placeholder__hint">{{
                    tab.placeholderHint
                  }}</span>
                </div>
                <div class="domain-placeholder__body">
                  <p class="domain-placeholder__desc">{{ tab.desc }}</p>
                  <div
                    v-if="tab.links.length"
                    class="domain-placeholder__links"
                  >
                    <el-button
                      v-for="(link, i) in tab.links"
                      :key="i"
                      size="small"
                      text
                      @click="goTo(link.to)"
                    >
                      {{ link.label }}
                      <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
                    </el-button>
                  </div>
                </div>
              </div>
            </template>
          </CardBlock>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import {
  runReconciliation,
  listDiscrepancies,
  ignoreDiscrepancy,
  type DiscrepancyItem
} from "@/api/reconciliation";

defineOptions({ name: "ReconcileWorkbench" });

const router = useRouter();

/** 当前激活域 */
const activeDomain = ref<"A" | "B" | "C">("B");

/** 差异数据 */
const discs = ref<DiscrepancyItem[]>([]);
const loading = ref(false);
const running = ref(false);

/** 域 B 差异（当前只展示 B 域；A/C 分别走各自链路） */
const bDiscs = computed(() => discs.value.filter(d => d.domain === "B"));

/** 待裁决 / 已忽略计数（P1 接入真实统计） */
const pendingCount = computed(
  () => discs.value.filter(d => d.status === "pending").length
);
const ignoredCount = computed(
  () => discs.value.filter(d => d.status === "ignored").length
);
/** 数据日期：最近一次差异的 updated_at 或今日 */
const dataDateLabel = computed(() => {
  const t = discs.value
    .map(d => d.updated_at)
    .filter(Boolean)
    .sort()
    .pop();
  return t ? t.slice(0, 10) : "—";
});

/** 是否有待处理差异（Banner 显示条件） */
const hasPending = computed(() => pendingCount.value > 0);

/** 三域 Tab 定义（§6.3） */
const domainTabs = [
  {
    key: "A",
    label: "E账户对账",
    title: "E账户对账（域 A）",
    description: "E账户官方快照 vs 渠道持仓",
    badgeType: "e_account",
    status: "ready",
    statusLabel: "已接入",
    placeholderHint: "复用既有对账链路",
    desc: "E账户对账已上线，P2 迁入本工作台统一入口。本期保持原入口可用。",
    links: [{ to: { name: "InvestmentReconcile" }, label: "前往原对账中心" }]
  },
  {
    key: "B",
    label: "持仓快照",
    title: "持仓快照一致性（域 B）",
    description: "流水推演理论持仓 vs 实际持仓",
    badgeType: "fund",
    status: "ready",
    statusLabel: "已接入",
    placeholderHint: "数量差异 + 孤儿检测",
    desc: "P1 已接入：理论持仓 = 流水重建净份额，比对实际持仓数量差异与孤儿。",
    links: []
  },
  {
    key: "C",
    label: "对账单导入",
    title: "对账单/交割单导入对账（域 C）",
    description: "导入的券商/基金对账单 vs 系统持仓",
    badgeType: "fund",
    status: "planned",
    statusLabel: "P1 规划",
    placeholderHint: "本期占位",
    desc: "P1 落地：导入 commit 后自动触发对账，差异进本工作台补录。",
    links: [
      { to: "/inventory/investment/import", label: "前往交易导入" },
      { to: "/investment/eaccount-import", label: "前往 E账户导入" }
    ]
  }
];

/** 差异类型中文 */
function typeLabel(t: string): string {
  const map: Record<string, string> = {
    quantity: "数量",
    cost: "成本",
    cash: "资金",
    orphan: "孤儿"
  };
  return map[t] || t;
}

/** 状态中文 */
function statusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: "待处理",
    cleared: "已清除",
    ignored: "已忽略"
  };
  return map[s] || s;
}

/** 差异值格式：最小单位 → 展示份数 */
function formatDiff(diff: number | null): string {
  if (diff === null) return "—";
  return String(diff);
}

function diffClass(diff: number | null): string {
  if (!diff) return "disc-diff-zero";
  return diff > 0 ? "disc-diff-pos" : "disc-diff-neg";
}

/** 加载差异列表 */
async function loadDiscrepancies(): Promise<void> {
  loading.value = true;
  try {
    const res = await listDiscrepancies();
    discs.value = res.data ?? [];
  } catch {
    discs.value = [];
  } finally {
    loading.value = false;
  }
}

/** 运行对账（域 B） */
async function handleRun(): Promise<void> {
  running.value = true;
  try {
    await runReconciliation("B");
    ElMessage.success("对账完成");
    await loadDiscrepancies();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "对账失败");
  } finally {
    running.value = false;
  }
}

/** 忽略一条差异（临时） */
async function handleIgnore(row: DiscrepancyItem): Promise<void> {
  try {
    await ignoreDiscrepancy(row.id, { permanent: false });
    ElMessage.success("已忽略");
    await loadDiscrepancies();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "忽略失败");
  }
}

/** 导航到既有入口（并行不破坏现状） */
function goTo(to: string | { name: string }): void {
  router.push(to);
}

onMounted(() => {
  loadDiscrepancies();
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
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
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
  color: var(--text-tertiary);
}

.workbench-head__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗 */
.workbench-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding: 12px 16px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
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

/* 域 B 差异表 */
.domain-b-body {
  padding: 4px 0;
}

.disc-table-wrap {
  overflow-x: auto;
}

.disc-table {
  width: 100%;
}

.disc-type {
  padding: 1px 8px;
  font-size: 12px;
  border-radius: 4px;
  background: var(--bg-soft);
  color: var(--text-secondary);
}

.disc-diff-zero {
  color: var(--text-tertiary);
}

.disc-diff-pos {
  color: var(--tag-sage-green);
}

.disc-diff-neg {
  color: var(--color-danger-system);
}

.disc-status {
  padding: 1px 8px;
  font-size: 12px;
  border-radius: 999px;
}

.disc-status--pending {
  color: var(--tag-caramel);
  background: color-mix(in srgb, var(--tag-caramel) 12%, transparent);
}

.disc-status--cleared {
  color: var(--tag-sage-green);
  background: color-mix(in srgb, var(--tag-sage-green) 12%, transparent);
}

.disc-status--ignored {
  color: var(--text-tertiary);
  background: var(--bg-soft);
}

.disc-muted {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 域 A/C 占位 */
.domain-placeholder {
  padding: 8px 4px;
}

.domain-placeholder__status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.domain-status-tag {
  padding: 2px 10px;
  font-size: 12px;
  line-height: 1.6;
  border-radius: 999px;
}

.domain-status-tag--ready {
  color: var(--tag-sage-green);
  background: color-mix(in srgb, var(--tag-sage-green) 12%, transparent);
}

.domain-status-tag--planned {
  color: var(--text-tertiary);
  background: var(--bg-soft);
}

.domain-placeholder__hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.domain-placeholder__desc {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.domain-placeholder__links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
