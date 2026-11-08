<template>
  <!--
    抽屉 ③「处理动作」的聚焦版（owner 第三轮）。
    抽屉是「为这一条待办」开的，所以这里只给这一条一个明确的动作，
    不再把整个域的清单重新列一遍——那和外面队列重复，用户也找不到自己该点哪个
    （owner 原话：「不是应该直接有一个按钮就够了吗？怎么又把所有的都列出来」）。

    写路径零重写：
    - 差异 / E账户 / 重复 / 孤儿 的弹窗在 index.vue 收口，这里只 emit 对应事件；
    - 补记红利税、补全缺失信息 的弹窗是自包含的，就地打开，写完后 emit('refresh')。
  -->
  <div class="recon-item-action">
    <p v-if="isDone" class="recon-item-action__done">{{ doneText }}</p>

    <!-- 域 E：补记红利税（自包含弹窗，复用 DomainEDividendTaxTable 里的同一组件） -->
    <template v-else-if="tax">
      <p class="recon-item-action__lead">{{ item.summary }}</p>
      <div v-if="taxPending" class="recon-item-action__buttons">
        <el-button type="primary" plain @click="taxVisible = true">
          补记这笔税
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

    <!-- 域 F 缺信息：补全缺失信息（自包含弹窗，复用 DomainFDanglingRefs 里的同一组件） -->
    <template v-else-if="danglingIncomplete">
      <p class="recon-item-action__lead">{{ item.summary }}</p>
      <div class="recon-item-action__buttons">
        <el-button type="primary" plain @click="remediationVisible = true">
          补全信息
        </el-button>
      </div>
      <DanglingRefRemediationDialog
        v-model="remediationVisible"
        :group="danglingRow"
        mode="enrich"
        @submitted="emit('refresh', 'dangling')"
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type {
  DiscrepancyItem,
  DividendTaxPendingItem,
  DanglingRefGroup,
  GhostDuplicateGroupItem,
  GhostDuplicateIgnore
} from "@/api/reconciliation";
import type { ReconciliationItem } from "@/api/eaccount";
import type { ReconQueueItem } from "../utils/reconQueue";
import RecordTaxDialog from "./RecordTaxDialog.vue";
import DanglingRefRemediationDialog from "./DanglingRefRemediationDialog.vue";

defineOptions({ name: "ReconItemAction" });

const props = defineProps<{ item: ReconQueueItem }>();

const emit = defineEmits<{
  supplement: [row: DiscrepancyItem];
  ignore: [row: DiscrepancyItem];
  fixDangling: [group: DanglingRefGroup];
  eaccountCover: [row: ReconciliationItem];
  eaccountIgnore: [row: ReconciliationItem];
  ghostIgnore: [group: GhostDuplicateGroupItem];
  ghostUndoIgnore: [item: GhostDuplicateIgnore];
  goTo: [to: string | { name: string }];
  fixOrphan: [item: ReconQueueItem];
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
  return row?.status === "未扣";
});
const taxRow = computed(
  () => (props.item.payload as { row: DividendTaxPendingItem }).row
);
const taxVisible = ref(false);

const danglingIncomplete = computed(
  () => kind.value === "dangling" && props.item.state !== "ready"
);
const danglingRow = computed(
  () => (props.item.payload as { row: DanglingRefGroup }).row
);
const remediationVisible = ref(false);

/** 除税 / 缺信息两类自包含弹窗外，其余域给出这一条应做的动作；
 *  用 emit 复用 index.vue 已收口的弹窗与端点，不新增写路径。 */
const actions = computed(() => {
  const item = props.item;
  switch (kind.value) {
    case "discrepancy":
      return [
        {
          label: "补充这笔",
          run: () =>
            emit("supplement", (item.payload as { row: DiscrepancyItem }).row)
        },
        {
          label: "忽略这条",
          run: () =>
            emit("ignore", (item.payload as { row: DiscrepancyItem }).row)
        }
      ];
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
    case "dangling":
      return [
        {
          label: "回补关联",
          run: () =>
            emit("fixDangling", (item.payload as { row: DanglingRefGroup }).row)
        }
      ];
    case "orphan":
      return item.state === "ready"
        ? [{ label: "核对并归入账本", run: () => emit("fixOrphan", item) }]
        : [];
    case "import":
      return [
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

.recon-item-action__done {
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
}
</style>
