<template>
  <!-- 抽屉不占文档流；域面板写路径零重写；内嵌弹窗经 useNestedDialog 关自身遮罩 -->
  <el-drawer
    :model-value="open"
    :size="drawerSize"
    direction="rtl"
    append-to-body
    :modal="!nestedDialogOpen"
    class="recon-detail-drawer"
    @update:model-value="onVisibility"
  >
    <template #header>
      <div
        class="recon-detail__header"
        :class="{ 'recon-detail--dimmed': nestedDialogOpen }"
      >
        <div class="recon-detail__heading">
          <h2 class="recon-detail__title">{{ drawerTitle }}</h2>
          <p v-if="detailSub" class="recon-detail__sub">{{ detailSub }}</p>
        </div>
      </div>
    </template>

    <div
      v-loading="detailLoading"
      class="recon-detail__body"
      :class="{ 'recon-detail--dimmed': nestedDialogOpen }"
    >
      <!-- ① 来龙去脉：差异类型 / 账本 / 差额 / 发现时间；产品标识只在头部说一次 -->
      <ReconContextPanel :item="drawerItem" />

      <!-- ② 投资轨迹（公共 TransactionTable）。recon-symbol-allow：symbol 只作流水查询条件，不渲染成标题。 -->
      <ReconInvestmentTrail
        v-if="trail"
        :symbol="trail.symbol"
        :ledger-id="trail.ledgerId"
        :product-name="drawerItem?.title"
        @changed="emit('refresh', 'trail')"
      />

      <!-- ③ 处理动作：域 F 的阶段面板自带阶段标题，此 header 只服务单条/单组 -->
      <SectionHeader v-if="!isStageNav" title="处理动作" />

      <SoftBanner v-if="detailError" variant="warning" icon="ep:warning">
        {{ detailError }}
        <template #actions>
          <el-button size="small" @click="emit('refresh', errorKey)">
            重新加载
          </el-button>
        </template>
      </SoftBanner>

      <!-- 单条执行区只给这一条一个动作；域 F 阶段模式由 ReconStagePanel 承载 -->
      <ReconItemAction
        v-if="drawerItem && detailDomain !== 'F'"
        :item="drawerItem"
        @supplement="emit('supplement', $event)"
        @ignore="emit('ignore', $event)"
        @fix-dangling="emit('fixDangling', $event)"
        @eaccount-cover="emit('eaccountCover', $event)"
        @eaccount-ignore="emit('eaccountIgnore', $event)"
        @ghost-ignore="emit('ghostIgnore', $event)"
        @ghost-undo-ignore="emit('ghostUndoIgnore', $event)"
        @go-to="emit('goTo', $event)"
        @fix-orphan="emit('fixOrphan', $event)"
        @refresh="emit('refresh', $event)"
      />

      <template v-else>
        <DomainBDiscTable
          v-if="detailDomain === 'B'"
          :items="ctx.bDiscs"
          :loading="ctx.loading"
          @supplement="emit('supplement', $event)"
          @ignore="emit('ignore', $event)"
        />

        <template v-else-if="detailDomain === 'C'">
          <div v-if="entry" class="domain-entry">
            <div class="domain-entry__text">
              <p class="domain-entry__title">{{ entry.title }}</p>
              <p class="domain-entry__hint">{{ entry.hint }}</p>
            </div>
            <div class="domain-entry__actions">
              <el-button
                v-for="(link, i) in entry.links"
                :key="i"
                size="small"
                :type="i === 0 ? 'primary' : 'default'"
                :plain="i === 0"
                @click="emit('goTo', link.to)"
              >
                {{ link.label }}
              </el-button>
            </div>
          </div>
          <DomainBDiscTable
            :items="ctx.cDiscs"
            :loading="ctx.loading"
            empty-text="暂无缺流水的持仓"
            @supplement="emit('supplement', $event)"
            @ignore="emit('ignore', $event)"
          />
        </template>

        <EAccountDomainPanel
          v-else-if="detailDomain === 'A'"
          :items="ctx.eItems"
          :loading="ctx.eLoading"
          :acting="ctx.eActing"
          @cover="emit('eaccountCover', $event)"
          @ignore="emit('eaccountIgnore', $event)"
        />

        <DomainDGhostTable
          v-else-if="detailDomain === 'D'"
          :items="ctx.ghostGroups"
          :ignored-items="ctx.ghostIgnored"
          :loading="ctx.ghostLoading"
          :deleting-id="ctx.ghostDeletingId"
          :undoing-id="ctx.ghostUndoingId"
          @ignore="emit('ghostIgnore', $event)"
          @undo-ignore="emit('ghostUndoIgnore', $event)"
          @delete-txn="emit('ghostDeleteTxn', $event)"
        />

        <DomainEDividendTaxTable
          v-else-if="detailDomain === 'E'"
          :items="ctx.taxItems"
          :total-cents="ctx.taxTotalCents"
          :pending-count="ctx.taxPendingCount"
          :deferred-count="ctx.taxDeferredCount"
          :exempt-count="ctx.taxExemptCount"
          :loading="ctx.taxLoading"
          @recorded="emit('refresh', 'tax')"
        />

        <ReconStagePanel
          v-else-if="detailDomain === 'F'"
          :stage="activeStage"
          :buckets="stageBuckets"
          :loading="ctx.danglingLoading"
          :error="ctx.errors.dangling ?? ''"
          @update:focus-item="focusItem = $event"
          @fix-dangling="emit('fixDangling', $event)"
          @refresh="emit('refresh', $event)"
          @retry="emit('refresh', 'dangling')"
        />

        <DomainGOrphanLedger
          v-else-if="detailDomain === 'G'"
          :data="ctx.orphanLedgers"
          :loading="ctx.orphanLoading"
          :error="ctx.errors.orphan ?? ''"
          @submitted="emit('refresh', 'orphan')"
          @retry="emit('refresh', 'orphan')"
        />

        <p v-else class="recon-detail__hint">
          这条待办的处理入口在下方按钮，选中的来源没有需要展开的记录表。
        </p>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { provideNestedDialog } from "../composables/useNestedDialog";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import type {
  DanglingRefGroup,
  DiscrepancyItem,
  GhostDuplicateGroupItem,
  GhostDuplicateIgnore,
  GhostDuplicateTxn
} from "@/api/reconciliation";
import type { ReconciliationItem } from "@/api/eaccount";
import { DOMAIN_SOURCE_LABEL } from "../constants/reconTasks";
import { domainTabs, type WorkbenchDomainKey } from "../constants/domainTabs";
import {
  DANGLING_ACTION_LABEL,
  bucketByStage,
  type DanglingStage
} from "../utils/danglingRefEnrichScope";
import {
  DETAIL_ERROR_KEY,
  type ReconDetailContext
} from "../utils/reconDetail";
import { reconItemAsset, reconTrailQuery } from "../utils/reconDrawer";
import { reconAssetHeading } from "../utils/reconDisplay";
import type { ReconQueueItem } from "../utils/reconQueue";
import ReconContextPanel from "./ReconContextPanel.vue";
import ReconItemAction from "./ReconItemAction.vue";
import ReconInvestmentTrail from "./ReconInvestmentTrail.vue";
import ReconStagePanel from "./ReconStagePanel.vue";
import DomainBDiscTable from "./DomainBDiscTable.vue";
import EAccountDomainPanel from "./EAccountDomainPanel.vue";
import DomainDGhostTable from "./DomainDGhostTable.vue";
import DomainEDividendTaxTable from "./DomainEDividendTaxTable.vue";
import DomainGOrphanLedger from "./DomainGOrphanLedger.vue";

defineOptions({ name: "ReconQueueDetail" });

/** 抽屉内弹窗打开时关掉自己的遮罩、内容退到背景，避免两层 modal 叠加。 */
const nestedDialogOpen = provideNestedDialog();

const props = defineProps<{
  item: ReconQueueItem | null;
  open: boolean;
  /** domain 与 item 解耦：?domain= 直达时无待办也要能看到空态处理区 */
  domain: WorkbenchDomainKey | null;
  /** 域 F 的当前阶段（漏斗，2026-11-13）：非空 = 单阶段面板，null = 全量形态 */
  activeStage: DanglingStage | null;
  ctx: ReconDetailContext;
}>();

const emit = defineEmits<{
  close: [];
  refresh: [key: string];
  supplement: [row: DiscrepancyItem];
  ignore: [row: DiscrepancyItem];
  fixDangling: [group: DanglingRefGroup];
  eaccountCover: [row: ReconciliationItem];
  eaccountIgnore: [row: ReconciliationItem];
  ghostIgnore: [group: GhostDuplicateGroupItem];
  ghostUndoIgnore: [item: GhostDuplicateIgnore];
  ghostDeleteTxn: [txn: GhostDuplicateTxn];
  goTo: [to: string | { name: string }];
  fixOrphan: [item: ReconQueueItem];
}>();

const detailDomain = computed(
  () => props.domain ?? props.item?.sourceDomain ?? null
);

/* 域 F 阶段漏斗：面板聚焦单组时上抛合成队列项（focusItem），头部/轨迹/来龙去脉随之切组级视角；返回阶段列表时面板发 null 退回。 */
const focusItem = ref<ReconQueueItem | null>(null);
/** 展示主体：面板聚焦的单组合成项优先于外部选中的队列项 */
const drawerItem = computed<ReconQueueItem | null>(
  () => focusItem.value ?? props.item
);
const stageBuckets = computed(() =>
  bucketByStage(props.ctx.danglingRefs?.groups ?? [])
);
/** 阶段导航态（域 F 且无单条/单组焦点）：处理动作 header 让位给阶段标题 */
const isStageNav = computed(
  () => detailDomain.value === "F" && drawerItem.value === null
);

/** 换阶段 / 关抽屉时清掉聚焦合成项，避免残留旧组视角 */
watch([() => props.domain, () => props.activeStage], () => {
  focusItem.value = null;
});

/** 产品标识的全抽屉唯一出处：有产品用「名称 · 代码」，无产品退回项原标题/来源名 */
const drawerTitle = computed(() => {
  const asset = drawerItem.value?.payload
    ? reconItemAsset(drawerItem.value.payload)
    : null;
  if (asset?.symbol) return reconAssetHeading(asset.symbol, asset.name);
  return (
    drawerItem.value?.title ||
    (detailDomain.value ? DOMAIN_SOURCE_LABEL[detailDomain.value] : "待办")
  );
});

/** 头部副标题：阶段导航 = 阶段动作名；单条/单组 = 「来源 · stateReason」 */
const detailSub = computed(() => {
  const item = drawerItem.value;
  if (item?.stateReason) return `${item.sourceLabel} · ${item.stateReason}`;
  if (item) return item.sourceLabel;
  return props.activeStage ? DANGLING_ACTION_LABEL[props.activeStage] : "";
});

/** 窄屏占满整屏、桌面 720px；matchMedia 只在跨阈值时触发（ExploreWatchlistTable 同款） */
const drawerSize = ref("720px");
let mq: MediaQueryList | null = null;
function onBreakpoint(e: MediaQueryListEvent | MediaQueryList): void {
  drawerSize.value = e.matches ? "100%" : "720px";
}
onMounted(() => {
  mq = window.matchMedia("(max-width: 768px)");
  onBreakpoint(mq);
  mq.addEventListener("change", onBreakpoint);
});
onBeforeUnmount(() => mq?.removeEventListener("change", onBreakpoint));

/** 投资轨迹的取数键：判据在 utils/reconDrawer（纯函数 + 单测），组件只消费 */
const trail = computed(() =>
  drawerItem.value?.payload ? reconTrailQuery(drawerItem.value.payload) : null
);

function onVisibility(value: boolean): void {
  if (!value) emit("close");
}

const entry = domainTabs.find(t => t.key === "C")?.entry ?? null;
const errorKey = computed(() =>
  detailDomain.value ? (DETAIL_ERROR_KEY[detailDomain.value] ?? "all") : "all"
);
const detailError = computed(() => props.ctx.errors[errorKey.value] ?? "");

/** 各域负责的 loader 键；失败时只重试该域，不整页重跑七个接口 */
const DOMAIN_LOADING_KEY = {
  A: "eLoading",
  B: "loading",
  C: "loading",
  D: "ghostLoading",
  E: "taxLoading",
  F: "danglingLoading",
  G: "orphanLoading"
} as const;

/** 选中单条/单组（drawerItem 存在）时内容已由队列数据驱动，不再盖遮罩 */
const detailLoading = computed(() => {
  if (drawerItem.value) return false;
  if (props.ctx.errors[errorKey.value]) return false;
  const key = detailDomain.value
    ? DOMAIN_LOADING_KEY[detailDomain.value]
    : null;
  return key ? props.ctx[key] : false;
});
</script>

<style scoped>
.recon-detail__header {
  width: 100%;
}

.recon-detail__heading,
.domain-entry__text {
  min-width: 0;
}

.recon-detail__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.recon-detail__sub {
  margin: 4px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.recon-detail__body {
  padding-bottom: var(--space-standard);
}

.recon-detail--dimmed {
  pointer-events: none;
  opacity: 0.3;
  transition: opacity 0.18s ease;
}

.recon-detail__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

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
