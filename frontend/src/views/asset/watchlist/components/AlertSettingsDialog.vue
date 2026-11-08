<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  getAlertSettings,
  updateAlertSettings,
  type WatchlistMagnitudeType
} from "@/api/watchlistAlerts";

/**
 * 提醒「默认口径」：幅度阈值与回看窗口由用户在小窗里改，后端只给默认值。
 *
 * 作用范围刻意写清楚：这里改的是**没单独设置过的标的**用的口径；
 * 单标的的自定义阈值在行内「提醒」区块里设（后者覆盖前者）。
 */
defineOptions({ name: "AlertSettingsDialog" });

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  /** 保存成功后通知外层重算（单标的区块的「生效口径」可能随之变化） */
  (e: "saved"): void;
}>();

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value)
});

const loading = ref(false);
const saving = ref(false);

/** 表单草稿：只有「用户确实要保存」的两个幅度类型 */
const form = reactive({
  CHANGE_PCT: {
    enabled: false,
    threshold: 5,
    windowDays: null as number | null
  },
  DRAWDOWN: { enabled: false, threshold: 10, windowDays: 60 }
});

/** 回撤窗口的合法区间与后端 `watchlist_alert_rules.WINDOW_BOUNDS` 一致 */
const WINDOW_MIN = 5;
const WINDOW_MAX = 250;

async function load() {
  loading.value = true;
  try {
    const { data } = await getAlertSettings();
    const byType = new Map(data.items.map(item => [item.alert_type, item]));
    const pct = byType.get("CHANGE_PCT");
    const dd = byType.get("DRAWDOWN");
    form.CHANGE_PCT.enabled = pct?.is_enabled ?? false;
    form.CHANGE_PCT.threshold =
      pct?.threshold_value ?? data.defaults.CHANGE_PCT.threshold_value;
    form.DRAWDOWN.enabled = dd?.is_enabled ?? false;
    form.DRAWDOWN.threshold =
      dd?.threshold_value ?? data.defaults.DRAWDOWN.threshold_value;
    form.DRAWDOWN.windowDays =
      dd?.window_days ?? data.defaults.DRAWDOWN.window_days ?? 60;
  } catch {
    ElMessage.error("读取提醒默认设置失败");
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.modelValue,
  visible => {
    if (visible) load();
  }
);

function validate(): boolean {
  const pct = form.CHANGE_PCT;
  if (pct.enabled && (pct.threshold <= 0 || pct.threshold > 50)) {
    ElMessage.warning("单日跌幅阈值需在 0.5~50% 之间");
    return false;
  }
  const dd = form.DRAWDOWN;
  if (dd.enabled && (dd.threshold <= 0 || dd.threshold >= 91)) {
    ElMessage.warning("回撤阈值需在 1~90% 之间");
    return false;
  }
  const windowDays = dd.windowDays ?? 60;
  if (windowDays < WINDOW_MIN || windowDays > WINDOW_MAX) {
    ElMessage.warning(`回看窗口需在 ${WINDOW_MIN}~${WINDOW_MAX} 个交易日之间`);
    return false;
  }
  return true;
}

async function save() {
  if (!validate()) return;
  saving.value = true;
  try {
    const items: Array<{
      alert_type: WatchlistMagnitudeType;
      is_enabled: boolean;
      threshold_value: number;
      window_days: number | null;
    }> = [
      {
        alert_type: "CHANGE_PCT",
        is_enabled: form.CHANGE_PCT.enabled,
        threshold_value: form.CHANGE_PCT.threshold,
        window_days: null
      },
      {
        alert_type: "DRAWDOWN",
        is_enabled: form.DRAWDOWN.enabled,
        threshold_value: form.DRAWDOWN.threshold,
        window_days: form.DRAWDOWN.windowDays ?? 60
      }
    ];
    await updateAlertSettings(items);
    ElMessage.success("默认设置已保存");
    emit("saved");
    dialogVisible.value = false;
  } catch {
    ElMessage.error("保存失败，请稍后重试");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="提醒默认设置"
    width="480px"
    append-to-body
  >
    <p class="wa-hint">
      这里设的是「没单独设置过的标的」用的默认口径；单只标的可在「提醒」区块里单独改。
    </p>

    <div v-loading="loading" class="wa-body">
      <div class="wa-row">
        <el-switch v-model="form.CHANGE_PCT.enabled" size="small" />
        <span class="wa-row__label">单日跌幅提醒</span>
        <el-input-number
          v-model="form.CHANGE_PCT.threshold"
          class="wa-row__num"
          size="small"
          :controls="false"
          :min="0.5"
          :max="50"
          :precision="2"
          :disabled="!form.CHANGE_PCT.enabled"
        />
        <span class="wa-row__unit">% 以上</span>
      </div>

      <div class="wa-row">
        <el-switch v-model="form.DRAWDOWN.enabled" size="small" />
        <span class="wa-row__label">自高点回撤提醒</span>
        <el-input-number
          v-model="form.DRAWDOWN.threshold"
          class="wa-row__num"
          size="small"
          :controls="false"
          :min="1"
          :max="90"
          :precision="2"
          :disabled="!form.DRAWDOWN.enabled"
        />
        <span class="wa-row__unit">% 以上</span>
      </div>

      <div class="wa-row wa-row--sub">
        <span class="wa-row__label">回看窗口</span>
        <el-input-number
          v-model="form.DRAWDOWN.windowDays"
          class="wa-row__num"
          size="small"
          :controls="false"
          :min="WINDOW_MIN"
          :max="WINDOW_MAX"
          :precision="0"
        />
        <span class="wa-row__unit">个交易日</span>
      </div>

      <p class="wa-hint wa-hint--foot">
        回撤按「窗口内最高收盘价」计算；同一周内只提醒一次。阈值留空的类型不会提醒。
      </p>
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.wa-hint {
  margin: 0 0 var(--space-3);
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-secondary);
}

.wa-hint--foot {
  margin: var(--space-3) 0 0;
  color: var(--text-tertiary-ink);
}

.wa-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.wa-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.wa-row--sub {
  padding-left: 32px;
}

.wa-row__label {
  min-width: 108px;
  font-size: var(--text-label);
  color: var(--text-primary);
}

.wa-row__num {
  width: 96px;
}

.wa-row__unit {
  font-size: var(--text-label);
  color: var(--text-secondary);
}
</style>
