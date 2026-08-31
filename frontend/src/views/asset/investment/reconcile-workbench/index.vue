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
        <AssetTypeBadge
          :type="activeDomain === 'A' ? 'e_account' : 'fund'"
          variant="tag"
        />
      </div>
    </header>

    <!-- 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗 -->
    <div v-if="hasPending" class="workbench-banner" role="alert">
      <IconifyIconOffline icon="ep:warning" class="workbench-banner__icon" />
      <div class="workbench-banner__text">
        有 {{ pendingCount }} 项差异待处理，点此前往对账工作台
      </div>
    </div>

    <!-- 顶部状态栏：数据日期 / 待裁决计数（占位数据，P1 接入真实计算） -->
    <div class="workbench-metrics">
      <MetricGrid :cols="3">
        <MetricCard
          title="数据日期"
          :value="dataDateLabel"
          caption="各域最新快照/导入日期"
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
          caption="可撤销（P1 接入）"
        />
      </MetricGrid>
    </div>

    <!-- 三域 Tab（§6.3）：本期占位，P1/P2 逐域接入 -->
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

            <!-- 占位内容：域状态标签 + 说明，P1/P2 填入实际对账逻辑 -->
            <div class="domain-placeholder">
              <div class="domain-placeholder__status">
                <span
                  class="domain-status-tag"
                  :class="`domain-status-tag--${tab.status}`"
                >
                  {{ tab.statusLabel }}
                </span>
                <span class="domain-placeholder__hint">
                  {{ tab.placeholderHint }}
                </span>
              </div>
              <div class="domain-placeholder__body">
                <p class="domain-placeholder__desc">{{ tab.desc }}</p>
                <div v-if="tab.links.length" class="domain-placeholder__links">
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
          </CardBlock>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { IconifyIconOffline } from "@/components/ReIcon";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";

defineOptions({ name: "ReconcileWorkbench" });

const router = useRouter();

/** 当前激活域 */
const activeDomain = ref<"A" | "B" | "C">("A");

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
    description: "期初快照 + 流水推演 vs 实际持仓",
    badgeType: "fund",
    status: "planned",
    statusLabel: "P1 规划",
    placeholderHint: "本期占位",
    desc: "P1 落地：快照份额 + 期后流水净变化（confirm_date > snapshot_date）比对数量差异。",
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

/** 待裁决计数（占位：本期 0，P1 接入 discrepancies 统计） */
const pendingCount = ref(0);
/** 已忽略计数（占位） */
const ignoredCount = ref(0);
/** 数据日期占位 */
const dataDateLabel = ref("—");

/** 是否有待处理差异（Banner 显示条件，占位） */
const hasPending = computed(() => pendingCount.value > 0);

/** 导航到既有入口（本期不破坏现状，并行） */
function goTo(to: string | { name: string }): void {
  router.push(to);
}
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
