<template>
  <!--
    批量回补（P2）。后端早就支持 transaction_ids 数组，旧页面却只能一组一组点。
    这里只收「后端判定可直接处理」的域 F / G 项，写之前把影响范围摊开，
    写之后给条数与撤销入口；撤销沿用既有 log_id 端点，不新增后端契约。
  -->
  <el-dialog
    :model-value="modelValue"
    title="批量回补可直接处理的记录"
    width="560px"
    @update:model-value="close"
  >
    <template v-if="!logs.length">
      <p class="batch-dialog__lead">
        已选 {{ items.length }} 项、共
        {{ totalRecords }} 条记录。系统已判定归属，
        只改关联或账本一列，不改份额与金额。
      </p>

      <ul class="batch-dialog__plan">
        <li v-for="(step, i) in steps" :key="`${step.kind}-${i}`">
          <strong>{{
            step.kind === "dangling" ? "挂回现存持仓" : "归入对应账本"
          }}</strong>
          <span>{{ step.ids.length }} 条记录</span>
          <span v-if="step.kind === 'dangling'">
            · 目标持仓 {{ step.targetPositionId }}
          </span>
          <span v-else>· {{ step.ledgerLabel }}</span>
        </li>
      </ul>

      <p class="batch-dialog__effect">
        每步都会记一条日志，处理完可凭日志编号撤销。找不到唯一归属的记录不在本次范围内，
        需要先补全信息；系统不会替你猜。
      </p>
      <p v-if="error" class="batch-dialog__error" role="alert">{{ error }}</p>
    </template>

    <template v-else>
      <p class="batch-dialog__result">
        本次回补 {{ totalUpdated }} 条记录，共 {{ logs.length }} 步。
      </p>
      <ul class="batch-dialog__logs">
        <li v-for="log in logs" :key="`${log.kind}-${log.logId}`">
          {{ log.kind === "dangling" ? "挂回持仓" : "归入账本" }} ·
          {{ log.updated }} 条 · 日志编号 {{ log.logId }}
        </li>
      </ul>
      <p class="batch-dialog__effect">
        撤销会还原这一步改过的关联或账本，不动其它记录。
      </p>
    </template>

    <template #footer>
      <el-button @click="close(false)">{{
        logs.length ? "完成" : "取消"
      }}</el-button>
      <el-button
        v-if="!logs.length"
        type="primary"
        :loading="submitting"
        :disabled="steps.length === 0"
        @click="submit"
      >
        确认批量回补
      </el-button>
      <el-button
        v-else
        type="primary"
        plain
        :loading="submitting"
        @click="undoAll"
      >
        撤销本次回补
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  backfillOrphanLedgers,
  reattachDanglingRefs,
  undoDanglingRefReattach,
  undoOrphanLedgerBackfill
} from "@/api/reconciliation";
import type { DanglingRefGroup, OrphanLedgerGroup } from "@/api/reconciliation";
import { reconLedgerName } from "../utils/reconDisplay";
import type { ReconQueueItem } from "../utils/reconQueue";

defineOptions({ name: "ReconBatchDialog" });

type StepKind = "dangling" | "orphan";
interface BatchStep {
  kind: StepKind;
  ids: number[];
  /** 域 F 的目标持仓 id；域 G 为 null */
  targetPositionId: number | null;
  /** 域 G 的拟归入账本名；域 F 为空串 */
  ledgerLabel: string;
}
interface BatchLog {
  kind: StepKind;
  logId: number;
  updated: number;
}

const props = defineProps<{
  modelValue: boolean;
  items: ReconQueueItem[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const submitting = ref(false);
const error = ref("");
const logs = ref<BatchLog[]>([]);

watch(
  () => props.modelValue,
  visible => {
    if (!visible) return;
    logs.value = [];
    error.value = "";
    submitting.value = false;
  }
);

/** 域 F 按目标持仓分组：不同目标不能塞进同一次 reattach 请求 */
const steps = computed<BatchStep[]>(() => {
  const dangling: DanglingRefGroup[] = [];
  const orphan: OrphanLedgerGroup[] = [];
  for (const item of props.items) {
    if (item.payload.kind === "danglingStage") {
      // 阶段聚合项拍平 groups（2026-11-13 恢复批量纳入）：逐组按目标持仓分组
      dangling.push(...item.payload.groups);
    }
    if (item.payload.kind === "orphan") orphan.push(item.payload.row);
  }

  const byTarget = new Map<number, number[]>();
  for (const group of dangling) {
    const target = group.live_position?.id;
    if (target === undefined) continue;
    const ids = group.transactions.map(t => t.id);
    byTarget.set(target, [...(byTarget.get(target) ?? []), ...ids]);
  }

  const result: BatchStep[] = [...byTarget.entries()].map(([target, ids]) => ({
    kind: "dangling",
    ids,
    targetPositionId: target,
    ledgerLabel: ""
  }));

  const orphanIds = orphan.flatMap(group =>
    group.transactions.filter(t => t.block_reason === null).map(t => t.id)
  );
  if (orphanIds.length) {
    const names = new Set(
      orphan.map(group => reconLedgerName(group.resolved_ledger?.name))
    );
    result.push({
      kind: "orphan",
      ids: orphanIds,
      targetPositionId: null,
      ledgerLabel: [...names].join("、")
    });
  }
  return result;
});

const totalRecords = computed(() =>
  steps.value.reduce((sum, step) => sum + step.ids.length, 0)
);
const totalUpdated = computed(() =>
  logs.value.reduce((sum, log) => sum + log.updated, 0)
);

function close(value: boolean): void {
  if (!value && logs.value.length) emit("submitted");
  emit("update:modelValue", value);
}

async function submit(): Promise<void> {
  submitting.value = true;
  error.value = "";
  const done: BatchLog[] = [];
  try {
    for (const step of steps.value) {
      if (step.kind === "dangling") {
        const res = await reattachDanglingRefs({
          transaction_ids: step.ids,
          target_position_id: step.targetPositionId!
        });
        const data = res.data;
        if (data?.log_id !== undefined) {
          done.push({
            kind: "dangling",
            logId: data.log_id,
            updated: data.updated ?? step.ids.length
          });
        }
      } else {
        const res = await backfillOrphanLedgers({ transaction_ids: step.ids });
        const data = res.data;
        if (data?.log_id !== undefined) {
          done.push({
            kind: "orphan",
            logId: data.log_id,
            updated: data.updated ?? step.ids.length
          });
        }
      }
    }
    logs.value = done;
    ElMessage.success(`已回补 ${totalUpdated.value} 条记录`);
    emit("submitted");
  } catch (e: unknown) {
    // 部分成功也要把已完成的日志留给用户撤销，不能吞掉
    logs.value = done;
    const err = e as { response?: { data?: { message?: string } } };
    error.value =
      err.response?.data?.message ||
      "回补中断，已完成的步骤可以撤销，未完成的记录保持原样。";
    emit("submitted");
  } finally {
    submitting.value = false;
  }
}

async function undoAll(): Promise<void> {
  submitting.value = true;
  error.value = "";
  try {
    for (const log of [...logs.value].reverse()) {
      if (log.kind === "dangling") {
        await undoDanglingRefReattach(log.logId);
      } else {
        await undoOrphanLedgerBackfill(log.logId);
      }
    }
    ElMessage.success(`已撤销 ${logs.value.length} 步回补`);
    logs.value = [];
    emit("submitted");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { message?: string } } };
    error.value =
      err.response?.data?.message || "撤销失败，重试或凭日志编号处理";
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.batch-dialog__lead,
.batch-dialog__effect,
.batch-dialog__result {
  margin: 0 0 var(--space-3);
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
}

.batch-dialog__result {
  font-weight: 600;
  color: var(--text-primary);
}

.batch-dialog__effect {
  padding-top: var(--space-2);
  margin-bottom: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  border-top: 1px solid var(--border-light);
}

.batch-dialog__plan,
.batch-dialog__logs {
  padding: 0 0 0 18px;
  margin: 0 0 var(--space-3);
  font-size: var(--text-label);
  line-height: 1.9;
  color: var(--text-secondary);
}

.batch-dialog__plan strong {
  color: var(--text-primary);
}

.batch-dialog__error {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-danger-ink);
}
</style>
