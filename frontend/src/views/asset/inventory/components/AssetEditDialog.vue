<template>
  <el-dialog
    v-model="visible"
    title="编辑资产"
    width="460px"
    destroy-on-close
    :before-close="onBeforeClose"
  >
    <el-form :model="form" label-width="96px">
      <!--
        名称：后端 AssetUpdate（schemas.py:55）与前端 AssetUpdateInput
        本就允许改，此前弹窗只暴露「金额 / 备注」，属入口与能力对不上。
        长度对齐 Asset.name 的 String(200)，保存前做非空校验，避免写空名后
        「同名负债聚合」与账本迁移去重静默失真。
      -->
      <el-form-item label="资产名称">
        <el-input
          v-model="form.name"
          maxlength="200"
          placeholder="请输入资产名称"
        />
      </el-form-item>
      <!--
        子类选择（#1849）：选项复用盘点页录入的同一份枚举，不另造一套。
      -->
      <el-form-item v-if="isFixedCategory" label="子类">
        <el-select
          v-model="form.minorCategory"
          class="w-full"
          placeholder="请选择子类（房产 / 汽车 / 黄金）"
          clearable
        >
          <el-option
            v-for="opt in fixedSubtypeOptions"
            :key="opt.key"
            :label="opt.label"
            :value="opt.key"
          />
        </el-select>
      </el-form-item>
      <!--
        值变动（D99/D100）：填的是「本次变动量」这个**独立业务事实**，
        不是变动后绝对值。绝对值无法支持乱序补录：当前值已含后续变动，
        用「新值 − 当前值」反推 delta 会把后面整条曲线平移。
        详见 docs/design/asset-value-history-design.md §8 实现期修订。
      -->
      <el-form-item label="本次变动量">
        <el-input-number
          v-model="form.delta"
          :precision="2"
          :step="1000"
          class="w-full"
        />
        <p class="change-hint">
          当前{{ valueNoun }} {{ currentLabel }} → 变动后
          {{ afterLabel }}；<br />
          填增减金额，负数表示还款／减少；填 0 表示只改资料、不记一笔变动
        </p>
      </el-form-item>
      <el-form-item v-if="form.delta !== 0" label="变动日期">
        <el-date-picker
          v-model="form.effectiveDate"
          type="date"
          class="w-full"
          value-format="YYYY-MM-DD"
          :clearable="false"
          placeholder="选择业务发生日"
        />
      </el-form-item>
      <el-form-item v-if="form.delta !== 0" label="变动说明">
        <el-input
          v-model="form.changeNote"
          maxlength="500"
          placeholder="选填，如「10 月月供」「年度重估」"
        />
      </el-form-item>
      <el-form-item v-if="form.delta !== 0" label="标记">
        <el-checkbox v-model="form.isCorrection">
          这是更正（冲销此前误录的一笔）
        </el-checkbox>
      </el-form-item>
      <el-form-item label="备注">
        <el-input
          v-model="form.notes"
          type="textarea"
          :rows="2"
          placeholder="选填，资产级备注（不随变动记录）"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <!-- 取消走 requestClose：before-close 只拦关闭按钮 / ESC / 点遮罩，程序化 close 走不到它 -->
      <el-button @click="requestClose(() => (visible = false))">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 编辑资产弹窗（名称 + 本次变动量 + 变动日期/说明 + 备注 + 条件子类）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。弹窗自己持有表单与保存副作用，
 * 保存成功后抛 `saved`，由页面决定如何刷新。
 *
 * delta == 0 时只提交资料字段，不写事件（设计 §5.2、验收 A10）；delta != 0 时
 * 追加 effective_date / change_note / client_token，由后端唯一写者写 append-only
 * 事件并更新 assets.amount 投影。
 */
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  updateAsset,
  type AssetRecord,
  type AssetUpdateInput
} from "@/api/assets";
import {
  useUnsavedChangesGuard,
  useDialogForm
} from "@/composables/useUnsavedChangesGuard";
import { formatAmount } from "@/utils/currency";
import { formatDate } from "@/utils/date";
import { getErrorMessage } from "../helpers";
import { ASSET_TYPE_MAP } from "../constants";

const props = defineProps<{
  /** 弹窗显隐（v-model） */
  modelValue: boolean;
  /** 待编辑的资产行；关闭状态下可为 null */
  asset: AssetRecord | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [visible: boolean];
  /** 保存成功（调用方负责刷新列表） */
  saved: [];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value)
});

const saving = ref(false);

/** 子类选项（#1849）：复用盘点页录入用的同一份枚举，不另造一套 */
const fixedSubtypeOptions = ASSET_TYPE_MAP.fixed;

/** 固定资产大类才补子类：其余大类的 minor_category 语义不同 */
const isFixedCategory = computed(() => props.asset?.major_category === "fixed");

/** 负债/应收叫「余额」，房产等叫「估值」，避免与持仓 NAV 混（设计 §3.1） */
const valueNoun = computed(() =>
  ["liability", "receivable"].includes(props.asset?.major_category ?? "")
    ? "余额"
    : "估值"
);
const currentAmount = computed(() => props.asset?.amount ?? 0);
const currentLabel = computed(() => `¥${formatAmount(currentAmount.value)}`);
const afterLabel = computed(
  () => `¥${formatAmount(currentAmount.value + (form.value.delta || 0))}`
);

const form = ref<{
  id: number | null;
  name: string;
  /** 本次变动量（元，带符号）；0 = 不记一笔变动 */
  delta: number;
  effectiveDate: string;
  changeNote: string;
  isCorrection: boolean;
  notes: string;
  /** 子类键（minor_category）：#1849 补分类入口所需 */
  minorCategory: string | null;
}>({
  id: null,
  name: "",
  delta: 0,
  effectiveDate: "",
  changeNote: "",
  isCorrection: false,
  notes: "",
  minorCategory: null
});

/**
 * 声明**必须在下面那个 `watch(..., { immediate: true })` 之前**——immediate 会同步
 * 执行回调回填本快照，声明在后面就是 TDZ ReferenceError（vue-tsc 会报 TS2304）。
 */
const EMPTY_FORM = {
  id: null,
  name: "",
  delta: 0,
  effectiveDate: "",
  changeNote: "",
  isCorrection: false,
  notes: "",
  minorCategory: null
};

const { isDirty, fillOnOpen, markSaved } = useDialogForm(form, () => ({
  ...EMPTY_FORM
}));

/**
 * 一次弹窗生命周期共用一个 client_token：loading 期间重复点击、保存失败后重试
 * 都复用同一笔，后端 UNIQUE + ON CONFLICT DO NOTHING 兜底，不产生第二条事件。
 * 保存成功后弹窗关闭，下次打开会生成新 token（设计 §5.4、验收 A9）。
 */
let clientToken = "";
/** 上次提交的变动要点；仅用于判断「失败重试时用户是否改过表单」 */
let lastAttemptKey = "";
function newClientToken(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

watch(
  () => props.modelValue,
  open => {
    if (open) {
      clientToken = newClientToken();
      lastAttemptKey = "";
    }
    fillOnOpen(open, () => ({
      id: props.asset?.id ?? null,
      name: props.asset?.name || "",
      delta: 0,
      // formatDate 走全站日期唯一入口，避免 toISOString() 的 UTC 跨日（东八区差一天）
      effectiveDate: formatDate(new Date()),
      changeNote: "",
      isCorrection: false,
      notes: props.asset?.notes || "",
      minorCategory: props.asset?.minor_category ?? null
    }));
  },
  { immediate: true }
);

const { onBeforeClose, requestClose } = useUnsavedChangesGuard(
  () => isDirty.value,
  {
    message: "资产名称／变动量／变动日期／说明／备注已改动，确定放弃吗？"
  }
);

async function save() {
  if (!form.value.id || saving.value) return;
  // name 是展示与多处聚合的隐式业务键，写空名会让这些结果静默失真，前端先挡住。
  const name = form.value.name.trim();
  if (!name) {
    ElMessage.warning("资产名称不能为空");
    return;
  }
  const delta = Number(form.value.delta || 0);
  if (delta !== 0) {
    if (!form.value.effectiveDate) {
      ElMessage.warning("请选择变动日期");
      return;
    }
    if (currentAmount.value + delta < 0) {
      ElMessage.warning(`变动后${valueNoun.value}不能为负`);
      return;
    }
  }

  saving.value = true;
  try {
    const payload: AssetUpdateInput = {
      name,
      notes: form.value.notes,
      // 只在固定资产大类下提交子类：其余大类的 minor_category 有各自的语义
      ...(isFixedCategory.value
        ? { minor_category: form.value.minorCategory || null }
        : {})
    };
    if (delta !== 0) {
      // 失败重试时若用户改了变动要点，必须换 token：否则后端按「重放」返回
      // 首次结果，界面提示保存成功、数值却没变（静默失真）。未改表单的重试
      // 仍复用同一 token，靠 UNIQUE + ON CONFLICT DO NOTHING 保证幂等。
      const attemptKey = [
        delta,
        form.value.effectiveDate,
        form.value.changeNote,
        form.value.isCorrection
      ].join("|");
      if (lastAttemptKey && lastAttemptKey !== attemptKey) {
        clientToken = newClientToken();
      }
      lastAttemptKey = attemptKey;
      // 绝不提交 amount 绝对值：那会把「补录历史」退化成覆盖当前值
      payload.delta = delta;
      payload.effective_date = form.value.effectiveDate;
      payload.change_note = form.value.changeNote;
      payload.client_token = clientToken;
      if (form.value.isCorrection) payload.change_kind = "correction";
    }
    await updateAsset(form.value.id, payload);
    ElMessage.success("资产已更新");
    // 显式清脏：即便 modelValue→false 分支因时序未跑到，也保证基线与当前值一致
    markSaved();
    visible.value = false;
    emit("saved");
  } catch (e) {
    ElMessage.error(getErrorMessage(e, "更新失败"));
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.change-hint {
  margin: 4px 0 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}
</style>
