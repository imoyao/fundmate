<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import DrawerSection from "@/components/ProductDrawer/DrawerSection.vue";
import type { WatchlistItem } from "@/api/watchlist";
import {
  getItemAlerts,
  patchAlert,
  upsertItemAlert,
  type WatchlistAlertEffective,
  type WatchlistAlertType,
  type WatchlistItemAlerts
} from "@/api/watchlistAlerts";
import { pricePrecision } from "@/utils/pricePrecision";
import AlertSettingsDialog from "../AlertSettingsDialog.vue";

/**
 * 「提醒」区块（速览抽屉内）：到价 / 单日跌幅 / 回撤三类规则。
 *
 * 口径约定（与后端一致）：
 * - 到价是**一次性**：触发后后端自动停用，文案里会写明；
 * - 幅度类两层：单标的规则优先，没有则沿用「默认设置」（`AlertSettingsDialog`）；
 *   单标的「关掉」会落一条停用规则，覆盖家庭默认——所以关得掉，不会被默认设置顶回来。
 *
 * 阈值全部由用户在前端填，后端只有默认值（`defaults`），不在代码里写死。
 */
defineOptions({ name: "QuickViewAlertSection" });

const props = defineProps<{ item: WatchlistItem | null }>();

const loading = ref(false);
const saving = ref(false);
const settingsVisible = ref(false);
const detail = ref<WatchlistItemAlerts | null>(null);

const form = reactive({
  priceUp: { enabled: false, value: 0 },
  priceDown: { enabled: false, value: 0 },
  pct: { enabled: false, value: 5 },
  drawdown: { enabled: false, value: 10 }
});

/** 无行情的品类（基金经理 / 投顾组合）不提供提醒 */
const NO_QUOTE_TYPES = ["manager", "portfolio"];

const canAlert = computed(() => {
  const type = (props.item?.asset_type ?? "").toLowerCase();
  return !!props.item && !NO_QUOTE_TYPES.includes(type);
});

const precision = computed(() => pricePrecision(props.item?.asset_type ?? ""));

const quote = computed(() => detail.value?.quote ?? null);
const windowDays = computed(
  () => detail.value?.effective.DRAWDOWN.window_days ?? 60
);

const latestText = computed(() => {
  const q = quote.value;
  if (!q || q.latest == null) return "暂无行情";
  const asOf = q.as_of ? `（截至 ${q.as_of}）` : "";
  return `现价 ${q.latest.toFixed(precision.value)}${asOf}`;
});

const highText = computed(() => {
  const q = quote.value;
  if (!q || q.window_high == null) return "";
  return `近 ${windowDays.value} 日高点 ${q.window_high.toFixed(precision.value)}`;
});

function fillForm(data: WatchlistItemAlerts) {
  const ruleOf = (type: WatchlistAlertType) =>
    data.rules.find(rule => rule.alert_type === type);

  const up = ruleOf("PRICE_UP");
  const down = ruleOf("PRICE_DOWN");
  const latest = data.quote.latest ?? 0;
  form.priceUp.enabled = !!up?.is_active;
  form.priceUp.value = up?.threshold_value ?? latest;
  form.priceDown.enabled = !!down?.is_active;
  form.priceDown.value = down?.threshold_value ?? latest;

  const pct = data.effective.CHANGE_PCT;
  form.pct.enabled = pct.is_enabled;
  form.pct.value = pct.threshold_value;
  const dd = data.effective.DRAWDOWN;
  form.drawdown.enabled = dd.is_enabled;
  form.drawdown.value = dd.threshold_value;
}

async function load(itemId: number) {
  loading.value = true;
  try {
    const { data } = await getItemAlerts(itemId);
    detail.value = data;
    fillForm(data);
  } catch {
    detail.value = null;
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.item?.id,
  id => {
    if (id) load(id);
  },
  { immediate: true }
);

function validate(): boolean {
  if (form.priceUp.enabled && !(form.priceUp.value > 0)) {
    ElMessage.warning("请填写有效的「涨到」价格");
    return false;
  }
  if (form.priceDown.enabled && !(form.priceDown.value > 0)) {
    ElMessage.warning("请填写有效的「跌到」价格");
    return false;
  }
  if (form.pct.enabled && !(form.pct.value > 0 && form.pct.value <= 50)) {
    ElMessage.warning("单日跌幅阈值需在 0.5~50% 之间");
    return false;
  }
  if (
    form.drawdown.enabled &&
    !(form.drawdown.value > 0 && form.drawdown.value < 91)
  ) {
    ElMessage.warning("回撤阈值需在 1~90% 之间");
    return false;
  }
  return true;
}

async function savePrice(
  type: WatchlistAlertType,
  state: { enabled: boolean; value: number }
) {
  const itemId = props.item?.id;
  if (!itemId) return;
  const existing = detail.value?.rules.find(rule => rule.alert_type === type);
  if (state.enabled) {
    await upsertItemAlert(itemId, {
      alert_type: type,
      threshold_value: state.value,
      is_active: true
    });
  } else if (existing?.is_active) {
    await patchAlert(existing.id, { is_active: false });
  }
}

async function saveMagnitude(
  type: "CHANGE_PCT" | "DRAWDOWN",
  state: { enabled: boolean; value: number },
  effective: WatchlistAlertEffective
) {
  const itemId = props.item?.id;
  if (!itemId) return;
  const existing = detail.value?.rules.find(rule => rule.alert_type === type);
  if (state.enabled) {
    await upsertItemAlert(itemId, {
      alert_type: type,
      threshold_value: state.value,
      is_active: true
    });
    return;
  }
  if (existing) {
    if (existing.is_active) await patchAlert(existing.id, { is_active: false });
    return;
  }
  // 家庭默认开着、本标的要关：落一条停用规则把它盖掉，否则会被默认设置重新点亮
  if (effective.source === "family" && effective.is_enabled) {
    await upsertItemAlert(itemId, {
      alert_type: type,
      threshold_value: effective.threshold_value,
      is_active: false
    });
  }
}

async function save() {
  if (!props.item?.id || !detail.value || !validate()) return;
  saving.value = true;
  try {
    await savePrice("PRICE_UP", form.priceUp);
    await savePrice("PRICE_DOWN", form.priceDown);
    await saveMagnitude(
      "CHANGE_PCT",
      form.pct,
      detail.value.effective.CHANGE_PCT
    );
    await saveMagnitude(
      "DRAWDOWN",
      form.drawdown,
      detail.value.effective.DRAWDOWN
    );
    ElMessage.success("提醒已保存");
    await load(props.item.id);
  } catch {
    ElMessage.error("保存失败，请稍后重试");
  } finally {
    saving.value = false;
  }
}

function onSettingsSaved() {
  if (props.item?.id) load(props.item.id);
}
</script>

<template>
  <DrawerSection title="提醒">
    <template #action>
      <el-button text size="small" @click="settingsVisible = true">
        默认设置
      </el-button>
    </template>

    <p v-if="!canAlert" class="wqa-hint">该品类没有行情数据，暂不支持提醒。</p>

    <div v-else v-loading="loading" class="wqa-body">
      <p class="wqa-hint">
        {{ latestText }}
        <span v-if="highText" class="wqa-hint__sub">· {{ highText }}</span>
      </p>

      <div class="wqa-row">
        <el-switch v-model="form.priceUp.enabled" size="small" />
        <span class="wqa-row__label">涨到</span>
        <el-input-number
          v-model="form.priceUp.value"
          class="wqa-row__num"
          size="small"
          :controls="false"
          :precision="precision"
          :min="0"
          :disabled="!form.priceUp.enabled"
        />
        <span class="wqa-row__unit">元</span>
      </div>

      <div class="wqa-row">
        <el-switch v-model="form.priceDown.enabled" size="small" />
        <span class="wqa-row__label">跌到</span>
        <el-input-number
          v-model="form.priceDown.value"
          class="wqa-row__num"
          size="small"
          :controls="false"
          :precision="precision"
          :min="0"
          :disabled="!form.priceDown.enabled"
        />
        <span class="wqa-row__unit">元</span>
      </div>

      <div class="wqa-row">
        <el-switch v-model="form.pct.enabled" size="small" />
        <span class="wqa-row__label">单日跌幅</span>
        <el-input-number
          v-model="form.pct.value"
          class="wqa-row__num"
          size="small"
          :controls="false"
          :precision="2"
          :min="0.5"
          :max="50"
          :disabled="!form.pct.enabled"
        />
        <span class="wqa-row__unit">% 以上</span>
      </div>

      <div class="wqa-row">
        <el-switch v-model="form.drawdown.enabled" size="small" />
        <span class="wqa-row__label">自高点回撤</span>
        <el-input-number
          v-model="form.drawdown.value"
          class="wqa-row__num"
          size="small"
          :controls="false"
          :precision="2"
          :min="1"
          :max="90"
          :disabled="!form.drawdown.enabled"
        />
        <span class="wqa-row__unit">% 以上（近 {{ windowDays }} 日）</span>
      </div>

      <div class="wqa-foot">
        <el-button size="small" type="primary" :loading="saving" @click="save">
          保存提醒
        </el-button>
        <span class="wqa-hint wqa-hint--foot">
          到价提醒触发一次后自动关闭；跌幅同一天、回撤同一周各只提醒一次。
        </span>
      </div>
    </div>

    <AlertSettingsDialog v-model="settingsVisible" @saved="onSettingsSaved" />
  </DrawerSection>
</template>

<style scoped lang="scss">
.wqa-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.wqa-hint {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-secondary);
}

.wqa-hint__sub {
  color: var(--text-tertiary-ink);
}

.wqa-hint--foot {
  margin-left: var(--space-3);
  color: var(--text-tertiary-ink);
}

.wqa-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.wqa-row__label {
  min-width: 72px;
  font-size: var(--text-label);
  color: var(--text-primary);
}

.wqa-row__num {
  width: 104px;
}

.wqa-row__unit {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.wqa-foot {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-2);
}
</style>
