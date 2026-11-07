<template>
  <!--
    队列 → 处理区的「主从」结构。选中一条待办后，这里渲染它所属来源的既有域面板：
    队列负责说人话，域面板负责承载真实的写路径与二次确认。
    没有新增纵向导航，也没有把后端域重新变回 tab。
  -->
  <!-- 加载只加遮罩，不替换内容：域面板内部挂着补全 / 回填 / 撤销弹窗，
       一旦在刷新时卸载整个面板，弹窗会被连带关掉，用户看不到「已处理」结果。 -->
  <CardBlock v-if="detailDomain" v-loading="detailLoading" class="recon-detail">
    <SectionHeader
      :title="`处理区 · ${item?.title || domainLabel}`"
      :info="item?.stateReason || ''"
    >
      <template #action>
        <el-button size="small" text @click="emit('close')">收起</el-button>
      </template>
    </SectionHeader>
    <p v-if="item?.summary" class="recon-detail__lead">{{ item.summary }}</p>

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
        empty-text="暂无孤儿持仓"
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
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
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
import DomainBDiscTable from "./DomainBDiscTable.vue";
import EAccountDomainPanel from "./EAccountDomainPanel.vue";
import DomainDGhostTable from "./DomainDGhostTable.vue";
import DomainEDividendTaxTable from "./DomainEDividendTaxTable.vue";
import DomainFDanglingRefs from "./DomainFDanglingRefs.vue";
import DomainGOrphanLedger from "./DomainGOrphanLedger.vue";

defineOptions({ name: "ReconQueueDetail" });

const props = defineProps<{
  item: ReconQueueItem | null;
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
.recon-detail {
  margin-top: var(--space-standard);
}

.recon-detail__lead {
  margin: 0 0 var(--space-compact);
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
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
