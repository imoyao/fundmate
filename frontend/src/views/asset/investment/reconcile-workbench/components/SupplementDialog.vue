<template>
  <!--
    补录弹窗（第二轮：从「一张裸表单」补成「有前因后果的补录」）。
    owner 原话：「点了补充之后弹出的窗口没有上下文，不知道缺的是哪条，没法补充」。

    结构：① 补的是哪一条（产品名 / 账本 / 差额）→ ② 两种补法说清区别 → ③ 表单。
    完整的买卖记录不塞进弹窗，放右侧抽屉的「这个产品的投资轨迹」（见
    ReconInvestmentTrail），弹窗里给一句明确的指引。

    写路径零重写：仍调 POST /api/reconciliation/adjustments/，由后端分派
    increment（补一笔流水）/ set（覆盖式 SET 锚点），不合并手动录入端点。
  -->
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="600px"
    append-to-body
    class="recon-supplement"
    @update:model-value="close"
    @closed="resetForm"
  >
    <template v-if="target">
      <!-- ① 补的是哪一条 -->
      <SupplementContext :target="target" />

      <!-- ② 两种补法 -->
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="96px"
        size="default"
      >
        <el-form-item label="补录方式">
          <SegmentedControl
            v-model="form.kind"
            :options="KIND_OPTIONS"
            aria-label="补录方式"
          />
        </el-form-item>
        <p class="recon-supplement__explain">{{ modeExplain }}</p>

        <SoftBanner
          v-if="form.kind === 'set'"
          variant="warning"
          icon="ep:warning"
          dense
        >
          {{ setHint }}
        </SoftBanner>
        <SoftBanner
          v-else-if="ledgerMissing"
          variant="info"
          icon="ep:info-filled"
          dense
        >
          这条差异还没归到账本，补上的流水也会没有账本。补完记得去归置。
        </SoftBanner>

        <template v-if="form.kind === 'increment'">
          <SupplementTradeFields
            v-model:op-type="form.op_type"
            v-model:quantity="form.quantity"
            v-model:avg-price="form.avg_price"
            v-model:fee="form.fee"
            v-model:trade-date="form.confirm_date"
            :expected-quantity="target.expected_value"
          />
        </template>

        <template v-else>
          <el-form-item label="账上现有">
            <span class="recon-supplement__current">
              {{ reconQuantity(target.actual_value) }}
            </span>
          </el-form-item>
          <el-form-item label="目标份额" prop="quantity">
            <el-input-number
              v-model="form.quantity"
              :min="0"
              :precision="4"
              :controls="false"
              style="width: 100%"
              placeholder="对照券商账单填当前份额"
            />
          </el-form-item>
          <el-form-item label="成本单价" prop="avg_price">
            <el-input-number
              v-model="form.avg_price"
              :min="0"
              :precision="4"
              :controls="false"
              style="width: 100%"
              placeholder="每份成本价（元）"
            />
          </el-form-item>
          <el-form-item label="生效日期">
            <el-date-picker
              v-model="form.snapshot_date"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              placeholder="以哪天的持仓为准"
            />
          </el-form-item>
        </template>

        <el-form-item :label="TRADE_FIELD_LABELS.notes">
          <el-input
            v-model="form.reason"
            type="textarea"
            :rows="2"
            placeholder="写下改动依据，方便以后回看（选填）"
          />
        </el-form-item>
      </el-form>
    </template>

    <template #footer>
      <el-button @click="close(false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { errorMessageOf } from "@/utils/errorMessage";
import { computed, reactive, ref, watch } from "vue";
import {
  ElMessage,
  ElMessageBox,
  type FormInstance,
  type FormRules
} from "element-plus";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import {
  applyAdjustment,
  type AdjustmentPayload,
  type DiscrepancyItem
} from "@/api/reconciliation";
import SupplementContext from "./SupplementContext.vue";
import SupplementTradeFields from "./SupplementTradeFields.vue";
import { TRADE_FIELD_LABELS } from "@/constants";
import {
  reconAssetHeading,
  reconGroupTitle,
  reconQuantity
} from "../utils/reconDisplay";

defineOptions({ name: "SupplementDialog" });

const KIND_OPTIONS = [
  { label: "补一笔交易", value: "increment" },
  { label: "把持仓改成", value: "set" }
] as const;

type Kind = (typeof KIND_OPTIONS)[number]["value"];

const props = defineProps<{
  modelValue: boolean;
  target: DiscrepancyItem | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const formRef = ref<FormInstance>();
const submitting = ref(false);

const form = reactive({
  kind: "increment" as Kind,
  op_type: "buy",
  quantity: undefined as number | undefined,
  avg_price: undefined as number | undefined,
  fee: undefined as number | undefined,
  confirm_date: "",
  snapshot_date: "",
  reason: ""
});

/** 本地日历日，不用 toISOString（UTC 会把上海时间的凌晨算成前一天） */
function todayLocal(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

const target = computed(() => props.target);
const heading = computed(() =>
  props.target
    ? reconAssetHeading(props.target.symbol, props.target.display_name)
    : ""
);
const dialogTitle = computed(() =>
  props.target
    ? `补录这笔 · ${reconGroupTitle(props.target.symbol, props.target.display_name)}`
    : "补录这笔"
);
const submitLabel = computed(() =>
  form.kind === "set" ? "改成这个持仓" : "补上这笔"
);

/**
 * `set` 是覆盖式 SET 锚点（backend/services/reconciliation_service.py:383-398），
 * 不新增流水；且后端 `resolve_snapshot_intent` 要求 ledger_id 非空、份额 > 0、
 * 单价 > 0。缺账本时直接挡住，别让用户填完表单才吃一个 400。
 */
const ledgerMissing = computed(
  () => !props.target || !Number.isFinite(props.target.ledger_id)
);
const modeExplain = computed(() =>
  form.kind === "set"
    ? "把账上的份额和成本直接改成你填的数。适合券商账单显示的就是当前持仓、只是我们这边记错了的情况。"
    : "补上缺的那笔买卖，会同时记一条交易流水并重算持仓。适合少记了一笔买入或卖出的情况。"
);
const setHint = computed(() =>
  ledgerMissing.value
    ? "这条差异还没归到任何账本，不能直接改持仓。先归置账本，或改用「补一笔交易」。"
    : "改完不会新增买卖记录，这笔差异会标记为已处理。份额和成本单价都要大于 0。"
);

const rules = computed<FormRules>(() => ({
  quantity: [
    {
      validator: (_rule, value, callback) => {
        if (typeof value !== "number" || !Number.isFinite(value)) {
          callback(new Error("份额还没填"));
          return;
        }
        if (value <= 0) {
          callback(new Error("份额要大于 0"));
          return;
        }
        callback();
      },
      trigger: "change"
    }
  ],
  avg_price: [
    {
      validator: (_rule, value, callback) => {
        if (typeof value !== "number" || !Number.isFinite(value)) {
          callback(new Error("单价还没填"));
          return;
        }
        if (value <= 0) {
          callback(new Error("单价要大于 0"));
          return;
        }
        callback();
      },
      trigger: "change"
    }
  ]
}));

/**
 * 预填买卖方向（owner：多了还是少了我们是知道的）。口径见 backend
 * reconciliation_service.py:171-198：diff = 账上份额(actual_value) − 按流水
 * 算的份额(expected_value)。diff<0 = 流水比账上多 = 少记了一笔卖出 ⇒ sell；
 * diff>0 = 少记了一笔买入 ⇒ buy；0/缺失不预填。只对 quantity 型生效：
 * orphan 是「持仓行没了、流水是对的」（#3066 按流水重建持仓处理，不能引导
 * 补一笔卖出），cost 与买卖方向无关。只预填方向，不预填数量（数量口径待
 * owner 拍板，不自作主张）。
 */
function inferOpType(row: DiscrepancyItem | null): "buy" | "sell" | null {
  if (!row || row.discrepancy_type !== "quantity") return null;
  const { expected_value: e, actual_value: a, diff } = row;
  // diff 缺失时按两值现算（backend :198 的同款口径），都没有则不预填
  const d =
    diff ?? (typeof e === "number" && typeof a === "number" ? a - e : null);
  if (d === null || d === 0) return null;
  return d < 0 ? "sell" : "buy";
}

function resetForm(): void {
  form.kind = "increment";
  // 按当前差异重新算方向（不是写死 buy）：打开弹窗 / 关闭后重开都要走这里
  form.op_type = inferOpType(props.target) ?? "buy";
  form.quantity = undefined;
  form.avg_price = undefined;
  form.fee = undefined;
  form.confirm_date = "";
  form.snapshot_date = todayLocal();
  form.reason = "";
  formRef.value?.clearValidate();
}

function close(value: boolean): void {
  emit("update:modelValue", value);
}

/** 每次打开重新取账本名、重置表单；切方式时清掉上一档的校验红字 */
watch(
  () => props.modelValue,
  open => {
    if (!open) return;
    resetForm();
  }
);
watch(
  () => form.kind,
  () => formRef.value?.clearValidate()
);

async function confirmOverwrite(): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      `把「${heading.value}」的持仓直接改成 ${reconQuantity(form.quantity)}、成本单价 ${form.avg_price} 元？这一步不会新增买卖记录，原有快照会被覆盖。`,
      "确认改成这个持仓",
      {
        type: "warning",
        confirmButtonText: "确认修改",
        cancelButtonText: "再看看"
      }
    );
    return true;
  } catch {
    return false;
  }
}

async function submit(): Promise<void> {
  const row = props.target;
  if (!row) return;
  if (form.kind === "set" && ledgerMissing.value) {
    ElMessage.warning("这条差异还没归账本，先归置账本，或改用「补一笔交易」");
    return;
  }
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  if (form.kind === "set" && !(await confirmOverwrite())) return;

  submitting.value = true;
  try {
    const payload: AdjustmentPayload = {
      kind: form.kind,
      discrepancy_id: row.id,
      symbol: row.symbol,
      name: row.display_name || undefined,
      ledger_id: row.ledger_id,
      quantity: form.quantity,
      avg_price: form.avg_price,
      reason: form.reason || undefined
    };
    if (form.kind === "increment") {
      payload.op_type = form.op_type;
      // 用户填的是成交当天：trade_date 与 confirm_date 都传这个日期。
      // 后端 `resolve_trade_date` 的口径本就是 trade_date 缺省回落 confirm_date，
      // 显式补上 trade_date，让流水列表按真实成交日排序（此前只有确认日）。
      payload.trade_date = form.confirm_date || undefined;
      payload.confirm_date = form.confirm_date || undefined;
      // 手续费：只有买入/卖出有成交费。存入/取出是银证转账，字段虽已隐藏，
      // 但用户可能先填了手续费再切过来（值不清空），故此处按 op_type 收口，
      // 否则会给一笔转账记上佣金。空值不传（后端按 0 计），填 0 也照传。
      const hasTradeFee = form.op_type === "buy" || form.op_type === "sell";
      payload.fee =
        hasTradeFee && typeof form.fee === "number" ? form.fee : undefined;
    } else {
      payload.snapshot_date = form.snapshot_date || todayLocal();
    }
    await applyAdjustment(payload);
    ElMessage.success(form.kind === "set" ? "持仓已改" : "这笔已补上");
    close(false);
    emit("submitted");
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "没保存成功，稍后再试");
  } finally {
    submitting.value = false;
  }
}

resetForm();
</script>

<style scoped>
.recon-supplement__explain {
  padding-left: 96px;
  margin: 0 0 var(--space-compact);
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}

.recon-supplement__current {
  font-size: var(--text-small);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
</style>
