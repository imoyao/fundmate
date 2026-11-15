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
        <!-- no_anchor 只有一种修法（以此为准），没有可选项就不给选择器 -->
        <el-form-item v-if="!isNoAnchor" label="补录方式">
          <SegmentedControl
            v-model="form.kind"
            :options="KIND_OPTIONS"
            aria-label="补录方式"
          />
        </el-form-item>
        <p class="recon-supplement__explain">{{ modeExplain }}</p>

        <SoftBanner
          v-if="form.kind === 'anchor'"
          variant="info"
          icon="ep:info-filled"
          dense
        >
          这条差异多半是「缺基准」：账上现有
          {{
            reconQuantity(target.actual_value)
          }}，但流水没完整覆盖建仓，两边本来就不该互相核对。以当前持仓为准后，
          之前的流水不再参与份额推导。请先确认账上份额与券商账单一致；若怀疑份额本身有误，
          请关掉这里，到持仓详情用「按流水重算份额」。
        </SoftBanner>
        <SoftBanner
          v-else-if="form.kind === 'set'"
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
            v-model:amount="form.buy_amount"
            :asset-type="assetType"
            :nav-hint="navHint"
            :expected-quantity="target.expected_value"
          />
        </template>

        <template v-else-if="form.kind === 'set'">
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
              :precision="priceInput.precision"
              :step="priceInput.step"
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
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
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
import { priceInputMeta } from "@/utils/pricePrecision";
import { useSharesLinkage } from "@/composables/useSharesLinkage";
import { useFundTradeDate } from "@/composables/useFundTradeDate";
import {
  reconAssetHeading,
  reconGroupTitle,
  reconQuantity
} from "../utils/reconDisplay";
import { useSupplementForm } from "../composables/useSupplementForm";
import { useSupplementNavSync } from "../composables/useSupplementNavSync";
import { discActionOf } from "../utils/discAction";
import {
  adjustmentSuccessMessage,
  buildAdjustmentPayload,
  supplementLabels,
  type SupplementKind
} from "../utils/adjustmentPayload";

defineOptions({ name: "SupplementDialog" });

const KIND_OPTIONS = [
  { label: "补一笔交易", value: "increment" },
  { label: "把持仓改成", value: "set" }
] as const;

/** 三种裁决形态的文案/请求体判据在 `utils/adjustmentPayload`；这里只列可选模式 */
type Kind = SupplementKind;

const props = defineProps<{
  modelValue: boolean;
  target: DiscrepancyItem | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const submitting = ref(false);

// 表单模型 / 校验 / 重置：`composables/useSupplementForm`（含方向预填的判据调用）
const {
  form,
  formRef,
  rules,
  resetForm: resetFormFields,
  clearValidate
} = useSupplementForm(() => props.target);

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
const isNoAnchor = computed(
  () => !!props.target && discActionOf(props.target) === "anchor"
);
const labels = computed(() => supplementLabels(form.kind));
const dialogTitle = computed(() =>
  props.target
    ? `${labels.value.action} · ${reconGroupTitle(props.target.symbol, props.target.display_name)}`
    : labels.value.action
);
const submitLabel = computed(() => labels.value.submit);

// 差异行标的的品种（后端 `serialize_discrepancies`）：决定「能不能按金额 + 当日净值填」
const assetType = computed(() => props.target?.asset_type ?? "");

// 成本单价录入档：按品种取档（基金 4 位净值、股票 2 位、场内 3 位）；未知品种回落
// 契约的 4 位上限 —— 写死字面量会被 guard_price_precision 拦下（#3120）。
const priceInput = computed(() => priceInputMeta(assetType.value));

/**
 * `set` 是覆盖式 SET 锚点（backend/services/reconciliation_service.py:383-398），
 * 不新增流水；且后端 `resolve_snapshot_intent` 要求 ledger_id 非空、份额 > 0、
 * 单价 > 0。缺账本时直接挡住，别让用户填完表单才吃一个 400。
 */
const ledgerMissing = computed(
  () => !props.target || !Number.isFinite(props.target.ledger_id)
);
const modeExplain = computed(() => labels.value.explain);
const setHint = computed(() =>
  ledgerMissing.value
    ? "这条差异还没归到任何账本，不能直接改持仓。先归置账本，或改用「补一笔交易」。"
    : "改完不会新增买卖记录，这笔差异会标记为已处理。份额和成本单价都要大于 0。"
);

/**
 * 交易日期 → 确认净值（只对场外基金买入生效）。
 *
 * 与「记一笔」同一个口径：先算确认日、再按实际净值日拉净值（`useFundTradeDate`）。
 * 拉不到就置 `navMissing`，由表单提示「份额和净值请手填」，**不猜一个净值**。
 */
const { calcConfirmAndNav } = useFundTradeDate();
const { navMissing, navHint } = useSupplementNavSync({
  form,
  assetType,
  symbol: () => props.target?.symbol ?? "",
  calcConfirmAndNav
});

/**
 * 金额 ⇄ 份额 ⇄ 净值 ⇄ 手续费 四者联动：与「记一笔」共用
 * `@/composables/useSharesLinkage`（字段名不同靠访问器适配，载荷一字不改）。
 *
 * 只在「补一笔交易 + 买入」启用：卖出 / 存入 / 取出填的是份额（账单上写的就是份额），
 * 「把持仓改成」更是覆盖式 SET——在那种模式下改成本单价会顺手改写用户填的目标份额。
 */
useSharesLinkage({
  navMissing,
  enabled: () => form.kind === "increment" && form.op_type === "buy",
  fields: {
    amount: () => form.buy_amount,
    setAmount: value => {
      form.buy_amount = value;
    },
    shares: () => form.quantity,
    setShares: value => {
      form.quantity = value;
    },
    price: () => form.avg_price,
    fee: () => form.fee
  }
});

/** 预填方向/默认模式的判据住在 `useSupplementForm` + `utils/reconSupplement`（纯函数 + 单测） */
function resetForm(): void {
  resetFormFields(todayLocal());
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
  () => clearValidate()
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
  if (form.kind === "anchor" && ledgerMissing.value) {
    ElMessage.warning("这条差异还没归账本，先归置账本再设定基准");
    return;
  }
  if (form.kind === "set" && ledgerMissing.value) {
    ElMessage.warning("这条差异还没归账本，先归置账本，或改用「补一笔交易」");
    return;
  }
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  if (form.kind === "set" && !(await confirmOverwrite())) return;

  submitting.value = true;
  try {
    const payload = buildAdjustmentPayload(row, form, todayLocal());
    const res = await applyAdjustment(payload);
    ElMessage.success(
      adjustmentSuccessMessage(
        form.kind,
        res?.data?.discrepancy?.status === "pending"
      )
    );
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
