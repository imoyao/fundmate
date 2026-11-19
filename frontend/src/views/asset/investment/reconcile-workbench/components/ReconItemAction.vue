<template>
  <!-- 抽屉「处理动作」聚焦版：只给这一条一个明确动作；差异/E账户/重复/孤儿的弹窗在
       index.vue 收口（这里 emit），补记红利税/补全信息弹窗自包含就地打开。 -->
  <div class="recon-item-action">
    <p v-if="isDone" class="recon-item-action__done">{{ doneText }}</p>

    <!-- 域 E：补记红利税（自包含弹窗，复用 DomainEDividendTaxTable 里的同一组件） -->
    <template v-else-if="tax">
      <p class="recon-item-action__lead">{{ item.summary }}</p>
      <div v-if="taxPending" class="recon-item-action__buttons">
        <el-button type="primary" plain @click="taxVisible = true">
          补记这笔税
        </el-button>
        <el-button text :loading="taxAcking" @click="ackTax">
          确认无需记账
        </el-button>
      </div>
      <p v-else class="recon-item-action__hint">
        红利税不会超过税前分红的
        20%，这笔更像别的品种的费用，对照交割单核对是否记错品种。
      </p>
      <RecordTaxDialog
        v-model="taxVisible"
        :item="taxRow"
        @recorded="emit('refresh', 'tax')"
      />
    </template>

    <!-- 域 F 执行区（漏斗 2026-11-13）：按 payload.stage 给唯一主动作 + 删除。
         错挂组不给「删除」（后端删除端点只认悬空流水，点了必 400）；
         无归属组（#3126）判据在 decideDanglingAction，没主动作时写原因。 -->
    <template v-else-if="danglingPayload">
      <p class="recon-item-action__lead">{{ item.summary }}</p>
      <p v-if="action.unowned" class="recon-item-action__reason">
        {{ action.unowned.reason }}
      </p>
      <div class="recon-item-action__buttons">
        <el-button
          v-if="action.primaryLabel"
          type="primary"
          plain
          @click="runPrimary"
        >
          {{ action.primaryLabel }}
        </el-button>
        <el-button
          v-if="!stageIsMislink"
          type="danger"
          plain
          @click="openRemediation('delete')"
        >
          删除
        </el-button>
      </div>
      <DanglingRefRemediationDialog
        v-model="remediationVisible"
        :group="stageGroup"
        :mode="remediationMode"
        @submitted="emit('refresh', 'dangling')"
      />
      <DanglingRefRebuildDialog
        v-if="action.rebuildTarget"
        v-model="rebuildVisible"
        :group="stageGroup"
        @rebuilt="emit('refresh', 'rebuilt')"
      />
      <DanglingRefMislinkDialog
        v-if="stageIsMislink"
        v-model="mislinkVisible"
        :group="stageGroup"
        @fixed="emit('refresh', 'dangling')"
      />
    </template>

    <!-- 其余域：明确的一条动作 -->
    <template v-else>
      <p class="recon-item-action__lead">{{ item.summary }}</p>
      <p v-if="item.stateReason" class="recon-item-action__reason">
        {{ item.stateReason }}
      </p>
      <div v-if="actions.length" class="recon-item-action__buttons">
        <el-button
          v-for="(btn, i) in actions"
          :key="i"
          :type="i === 0 ? 'primary' : 'default'"
          :plain="i === 0"
          @click="btn.run"
        >
          {{ btn.label }}
        </el-button>
      </div>
      <p
        v-else-if="item.state === 'incomplete'"
        class="recon-item-action__hint"
      >
        系统按账户名找不到唯一对应的账本，不会替你猜。先核对账户名与账本名一致，再回来归账。
      </p>
      <!-- 一行动作解释：三个动作改的是不同的一侧（补流水 / 改持仓 / 写基准），
           不写清楚时用户只能靠点一次看结果来分辨，而写库是不可逆的 -->
      <p v-if="discAction" class="recon-item-action__hint">
        {{ DISC_ACTION_HINTS[discAction] }}
      </p>
      <p v-if="eaccountRisk" class="recon-item-action__risk">
        {{ eaccountRisk }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { ackDividendTax } from "@/api/reconciliation";
import type {
  DiscrepancyItem,
  DividendTaxPendingItem,
  DanglingRefGroup,
  GhostDuplicateGroupItem,
  GhostDuplicateIgnore
} from "@/api/reconciliation";
import type { ReconciliationItem } from "@/api/eaccount";
import type { DanglingStagePayload, ReconQueueItem } from "../utils/reconQueue";
import {
  DISC_ACTION_HINTS,
  DISC_ACTION_LABELS,
  discActionEvent,
  discActionOf
} from "../utils/discAction";
import { decideDanglingAction } from "../utils/danglingRefEnrichScope";
import { ACTION_RISK_HINTS } from "../utils/reconLabels";
import RecordTaxDialog from "./RecordTaxDialog.vue";
import DanglingRefRemediationDialog from "./DanglingRefRemediationDialog.vue";
import DanglingRefRebuildDialog from "./DanglingRefRebuildDialog.vue";
import DanglingRefMislinkDialog from "./DanglingRefMislinkDialog.vue";

defineOptions({ name: "ReconItemAction" });

const props = defineProps<{ item: ReconQueueItem }>();

const emit = defineEmits<{
  supplement: [row: DiscrepancyItem];
  recompute: [row: DiscrepancyItem];
  ignore: [row: DiscrepancyItem];
  fixDangling: [group: DanglingRefGroup];
  eaccountCover: [row: ReconciliationItem];
  eaccountIgnore: [row: ReconciliationItem];
  ghostIgnore: [group: GhostDuplicateGroupItem];
  ghostUndoIgnore: [item: GhostDuplicateIgnore];
  goTo: [to: string | { name: string }];
  fixOrphan: [item: ReconQueueItem];
  recognize: [];
  refresh: [key: string];
}>();

const kind = computed(() => props.item.payload.kind);
const isDone = computed(() => props.item.state === "done");
const doneText = computed(() => {
  if (kind.value === "ghostIgnored")
    return "这组重复交易已经忽略，可在下方撤销。";
  if (kind.value === "import") return "这是导入入口，不是一笔待处理记录。";
  return "这条待办已经处理过了。";
});

const tax = computed(() => kind.value === "tax");
const taxPending = computed(() => {
  const row = (props.item.payload as { row?: DividendTaxPendingItem }).row;
  return row?.status === "待核对";
});
const taxRow = computed(
  () => (props.item.payload as { row: DividendTaxPendingItem }).row
);
const taxVisible = ref(false);
const taxAcking = ref(false);

/** 确认「这笔确实没有税」：红利税派息时法定暂不扣缴，只有「已卖出、持股不足一年、仍没配上税」才落到这里。不记 0 元流水（0 元是「无需纳税」不是「交了 0 元」）。 */
async function ackTax(): Promise<void> {
  const row = taxRow.value;
  if (!row?.dividend_on) return;
  taxAcking.value = true;
  try {
    await ackDividendTax({
      symbol: row.symbol,
      account_name: row.account_name,
      dividend_on: row.dividend_on,
      reason: "确认无需记账"
    });
    ElMessage.success("已确认这笔无需记账");
    emit("refresh", "tax");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "确认失败，请稍后重试");
  } finally {
    taxAcking.value = false;
  }
}

/** 域 F 阶段载荷：阶段已在 payload.stage，组件不再重算判据 */
const danglingPayload = computed(() =>
  kind.value === "danglingStage"
    ? (props.item.payload as DanglingStagePayload)
    : null
);
const stageGroup = computed(() => danglingPayload.value?.groups[0] ?? null);
const stageIsMislink = computed(
  () => danglingPayload.value?.stage === "mislink"
);
const remediationVisible = ref(false);
const remediationMode = ref<"enrich" | "delete">("enrich");
const rebuildVisible = ref(false);
const mislinkVisible = ref(false);

/** 执行区决策（判据在 `danglingRefEnrichScope.decideDanglingAction`）：主动作文字 + 重建接线 */
const action = computed(() =>
  decideDanglingAction(
    danglingPayload.value?.stage,
    stageGroup.value,
    props.item.actionLabel
  )
);

function openRemediation(mode: "enrich" | "delete"): void {
  remediationMode.value = mode;
  remediationVisible.value = true;
}

/** 主按钮按阶段分发：reattach/rebuild/fill/mislink 各走自己的弹窗或事件 */
function runPrimary(): void {
  const payload = danglingPayload.value;
  if (!payload) return;
  if (payload.stage === "unowned") {
    if (action.value.unowned?.outcome === "fill") openRemediation("enrich");
    else if (action.value.unowned?.outcome === "rebuild")
      rebuildVisible.value = true;
    return;
  }
  if (payload.stage === "reattach") {
    emit("fixDangling", payload.groups[0]!);
    return;
  }
  if (payload.stage === "rebuild") {
    rebuildVisible.value = true;
    return;
  }
  if (payload.stage === "mislink") {
    mislinkVisible.value = true;
    return;
  }
  openRemediation("enrich");
}

/** 单条差异行（判据与文案都要它；只在 discrepancy 类待办上非空） */
const discRow = computed<DiscrepancyItem | null>(() =>
  kind.value === "discrepancy"
    ? (props.item.payload as { row: DiscrepancyItem }).row
    : null
);
const discAction = computed(() =>
  discRow.value ? discActionOf(discRow.value) : null
);

/** E账户归因的风险句（临门一脚）：只在抽屉按钮旁露一次，列表态不出现 */
const eaccountRisk = computed(() =>
  kind.value === "eaccount" ? ACTION_RISK_HINTS.eaccountCover : ""
);

/** 除税/缺信息两类自包含弹窗外，其余域给出这一条应做的动作；用 emit 复用 index.vue 收口的弹窗，不新增写路径。 */
const actions = computed(() => {
  const item = props.item;
  switch (kind.value) {
    case "discrepancy": {
      // 文案与事件按差异类型选（判据在 utils/discAction.ts）：原硬编码「补充这笔」，而 quantity 差异补录后差额不变（#3134），点多少次都平不了账。
      const row = discRow.value;
      const action = discAction.value;
      if (!row || !action) return [];
      return [
        {
          label: DISC_ACTION_LABELS[action],
          run: () => {
            if (discActionEvent(action) === "recompute") emit("recompute", row);
            else emit("supplement", row);
          }
        },
        {
          label: "忽略这条",
          run: () => emit("ignore", row)
        }
      ];
    }
    case "eaccount":
      return [
        {
          label: "核对并归因",
          run: () =>
            emit(
              "eaccountCover",
              (item.payload as { row: ReconciliationItem }).row
            )
        },
        {
          label: "忽略",
          run: () =>
            emit(
              "eaccountIgnore",
              (item.payload as { row: ReconciliationItem }).row
            )
        }
      ];
    case "ghost":
      return [
        {
          label: "忽略这组重复",
          run: () =>
            emit(
              "ghostIgnore",
              (item.payload as { row: GhostDuplicateGroupItem }).row
            )
        }
      ];
    case "ghostIgnored":
      return [
        {
          label: "撤销忽略",
          run: () =>
            emit(
              "ghostUndoIgnore",
              (item.payload as { row: GhostDuplicateIgnore }).row
            )
        }
      ];
    case "orphan":
      return item.state === "ready"
        ? [{ label: "确认归入账本", run: () => emit("fixOrphan", item) }]
        : [];
    case "import":
      return [
        {
          label: "AI 识别",
          run: () => emit("recognize")
        },
        {
          label: "前往交易导入",
          run: () => emit("goTo", "/inventory/investment/import")
        }
      ];
    default:
      return [];
  }
});
</script>

<style scoped>
.recon-item-action {
  padding: var(--space-standard);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.recon-item-action__lead {
  margin: 0 0 10px;
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
}

.recon-item-action__reason {
  margin: 0 0 10px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.recon-item-action__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.recon-item-action__hint {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.recon-item-action__risk {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
}

.recon-item-action__done {
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
}
</style>
