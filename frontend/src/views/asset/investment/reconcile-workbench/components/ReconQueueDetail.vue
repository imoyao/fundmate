<template>
  <!--
    队列 → 处理区改成「右侧抽屉」（owner 第二轮）。
    旧版把处理区挂在队列下方：几百条待办时处理完一条要往回滚，
    而且 520px 弹窗塞不下「缺哪条 / 交易流水 / 补充表单」三段上下文。
    抽屉不占文档流，队列不位移；720px 宽度放得下三段的并排信息。

    写路径零重写：下面各域面板与上一版完全一致，仍承载归因 / 忽略 /
    补税 / 回填 / 撤销与二次确认。加载只加遮罩、不卸载内容，避免刷新时
    连带关掉挂在面板内的弹窗（上一轮实机抓到过的回归）。
  -->
  <el-drawer
    :model-value="open"
    :size="drawerSize"
    direction="rtl"
    append-to-body
    class="recon-detail-drawer"
    @update:model-value="onVisibility"
  >
    <template #header>
      <div class="recon-detail__header">
        <div class="recon-detail__heading">
          <h2 class="recon-detail__title">{{ drawerTitle }}</h2>
          <p class="recon-detail__sub">
            {{ item?.sourceLabel || domainLabel }} ·
            {{ item?.stateReason || "对照上面的记录再决定怎么处理" }}
          </p>
        </div>
        <el-button size="small" text @click="emit('close')">收起</el-button>
      </div>
    </template>

    <div v-loading="detailLoading" class="recon-detail__body">
      <!-- ① 来龙去脉：产品名 / 代码 / 账本 / 差额 / 发现时间 -->
      <ReconContextPanel :item="item" />

      <!-- ② 投资轨迹：该产品在该账本的交易流水（公共 TransactionTable） -->
      <ReconInvestmentTrail
        v-if="trail"
        :symbol="trail.symbol"
        :ledger-id="trail.ledgerId"
      />

      <!-- ③ 处理动作：既有域面板，写路径零重写 -->
      <SectionHeader
        title="处理动作"
        info="下面的操作会写回账本；有二次确认的会先弹确认。"
      />

      <SoftBanner v-if="detailError" variant="warning" icon="ep:warning">
        {{ detailError }}
        <template #actions>
          <el-button size="small" @click="emit('refresh', errorKey)">
            重新加载
          </el-button>
        </template>
      </SoftBanner>

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
        :loading="ctx.taxLoading"
        @recorded="emit('refresh', 'tax')"
      />

      <DomainFDanglingRefs
        v-else-if="detailDomain === 'F'"
        :data="ctx.danglingRefs"
        :loading="ctx.danglingLoading"
        :error="ctx.errors.dangling ?? ''"
        @fix="emit('fixDangling', $event)"
        @refresh="emit('refresh', 'dangling')"
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
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
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
  DETAIL_ERROR_KEY,
  type ReconDetailContext
} from "../utils/reconDetail";
import type { ReconQueueItem } from "../utils/reconQueue";
import ReconContextPanel from "./ReconContextPanel.vue";
import ReconInvestmentTrail from "./ReconInvestmentTrail.vue";
import DomainBDiscTable from "./DomainBDiscTable.vue";
import EAccountDomainPanel from "./EAccountDomainPanel.vue";
import DomainDGhostTable from "./DomainDGhostTable.vue";
import DomainEDividendTaxTable from "./DomainEDividendTaxTable.vue";
import DomainFDanglingRefs from "./DomainFDanglingRefs.vue";
import DomainGOrphanLedger from "./DomainGOrphanLedger.vue";

defineOptions({ name: "ReconQueueDetail" });

const props = defineProps<{
  item: ReconQueueItem | null;
  /** 抽屉是否展开（入站 ?domain=G 时即使没有待办也要能看到空态） */
  open: boolean;
  /**
   * 入站 `?domain=G` 直达时即使该类一条待办都没有，也要能看到对应处理区（空态）。
   * 故 domain 与 item 解耦：domain 决定渲染哪个面板，item 只决定标题与说明。
   */
  domain: WorkbenchDomainKey | null;
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
}>();

const detailDomain = computed(
  () => props.domain ?? props.item?.sourceDomain ?? null
);
const domainLabel = computed(() =>
  detailDomain.value ? DOMAIN_SOURCE_LABEL[detailDomain.value] : "待办"
);
const drawerTitle = computed(() => props.item?.title || domainLabel.value);

/** 抽屉在窄屏占满整屏，桌面固定 720px（el-drawer 的 size 是 inline style）。
 *  断点用 matchMedia 而非裸 innerWidth：只在跨越阈值时触发，不跟着每一次 resize 抖动，
 *  与全站移动端降级写法一致（ExploreWatchlistTable.vue）。 */
const MOBILE_MQ = "(max-width: 768px)";
const drawerSize = ref("720px");
let mq: MediaQueryList | null = null;
function onBreakpoint(e: MediaQueryListEvent | MediaQueryList): void {
  drawerSize.value = e.matches ? "100%" : "720px";
}
onMounted(() => {
  mq = window.matchMedia(MOBILE_MQ);
  onBreakpoint(mq);
  mq.addEventListener("change", onBreakpoint);
});
onBeforeUnmount(() => mq?.removeEventListener("change", onBreakpoint));

/** 投资轨迹的取数键：只消费确实带 symbol 的原始对象 */
const trail = computed<{ symbol: string; ledgerId: number | null } | null>(
  () => {
    const payload = props.item?.payload;
    if (!payload) return null;
    switch (payload.kind) {
      case "discrepancy":
        return { symbol: payload.row.symbol, ledgerId: payload.row.ledger_id };
      case "tax":
      case "eaccount":
      case "ghost":
        return { symbol: payload.row.symbol, ledgerId: null };
      case "dangling":
        return { symbol: payload.row.symbol, ledgerId: payload.row.ledger_id };
      default:
        return null;
    }
  }
);

function onVisibility(value: boolean): void {
  if (!value) emit("close");
}

const entry = computed(
  () => domainTabs.find(t => t.key === "C")?.entry ?? null
);
const errorKey = computed(() =>
  detailDomain.value ? (DETAIL_ERROR_KEY[detailDomain.value] ?? "all") : "all"
);
const detailError = computed(() => props.ctx.errors[errorKey.value] ?? "");

/** 失败时只重试负责这个来源的 loader，不整页重跑七个接口 */
const detailLoading = computed(() => {
  if (props.ctx.errors[errorKey.value]) return false;
  switch (detailDomain.value) {
    case "A":
      return props.ctx.eLoading;
    case "B":
    case "C":
      return props.ctx.loading;
    case "D":
      return props.ctx.ghostLoading;
    case "E":
      return props.ctx.taxLoading;
    case "F":
      return props.ctx.danglingLoading;
    case "G":
      return props.ctx.orphanLoading;
    default:
      return false;
  }
});
</script>

<style scoped>
.recon-detail__header {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  justify-content: space-between;
  width: 100%;
}

.recon-detail__heading {
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
