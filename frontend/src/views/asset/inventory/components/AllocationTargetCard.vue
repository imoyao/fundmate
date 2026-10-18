<template>
  <!--
    目标配比卡（#2237）：当前占比 vs 你自己定的目标占比。
    纯展示 + 编辑态表单，请求与保存全部由页面数据层 `useStrategyInsight` 承担。
  -->
  <div class="allocation-card">
    <SectionHeader
      title="目标配比"
      info="目标占比是你自己定的线。当前占比与目标的差距达到阈值时，可以用区块右上角的「立即检查提醒」生成站内提醒。"
      info-label="目标配比口径说明"
    >
      <template #action>
        <div class="allocation-card__actions">
          <template v-if="editing">
            <el-button size="small" @click="cancelEdit">取消</el-button>
            <el-button
              size="small"
              type="primary"
              :loading="saving"
              @click="submitEdit"
              >保存</el-button
            >
          </template>
          <!-- 立即检查提醒：只在只读态出现。编辑态隐藏是有意的——
               扫描用的是后端已存目标，编辑中的 buffer 还没生效，
               此刻提醒会让人以为「改了但没变」 -->
          <template v-else>
            <el-button
              size="small"
              :loading="reminderRefreshing"
              @click="emit('refresh-reminders')"
              >立即检查提醒</el-button
            >
            <el-button size="small" @click="enterEdit">编辑</el-button>
          </template>
        </div>
      </template>
    </SectionHeader>

    <CardBlock>
      <!-- 加载中 -->
      <p v-if="loading" class="allocation-card__hint" role="status">
        目标配比加载中…
      </p>

      <!-- 失败态：不显示任何 0 值——0 会被读成「没有偏离」，而实际是「取不到」 -->
      <div v-else-if="error" class="allocation-card__error" role="alert">
        <span class="allocation-card__error-text">目标配比加载失败</span>
        <el-button text size="small" @click="emit('retry')">重试</el-button>
      </div>

      <!-- 数据态：没有任何持仓 -->
      <p v-else-if="!data?.items?.length" class="allocation-card__hint">
        还没有持仓。录入持仓后，就可以给它们定目标占比了。
      </p>

      <template v-else>
        <!-- 空态引导（#2237）：一个目标都没设过时，先讲清楚「设了有什么用」 -->
        <p v-if="data.configured_count === 0" class="allocation-card__guide">
          给核心持仓定个目标占比，占比漂移超过
          {{ formatPct(data.threshold_pct) }} 个百分点时提醒你。
        </p>

        <!-- 编辑态：顶部给出目标总和，只是提示，不强制 100 -->
        <p v-if="editing" class="allocation-card__sum">
          目标总和 {{ formatPct(targetSum) }}%（不要求凑满 100）
        </p>

        <div class="allocation-card__rows">
          <div
            class="allocation-card__row allocation-card__row--head"
            :class="{ 'allocation-card__row--readonly': !editing }"
          >
            <span class="allocation-card__cell">标的</span>
            <span class="allocation-card__cell allocation-card__cell--num"
              >当前</span
            >
            <span class="allocation-card__cell allocation-card__cell--num"
              >目标</span
            >
            <span class="allocation-card__cell allocation-card__cell--num"
              >偏离</span
            >
            <span v-if="editing" class="allocation-card__cell--op" />
          </div>

          <div
            v-for="(row, index) in visibleRows"
            :key="row.symbol"
            class="allocation-card__row"
            :class="{
              'allocation-card__row--breached': row.breached,
              'allocation-card__row--readonly': !editing
            }"
          >
            <span class="allocation-card__cell allocation-card__name">
              <span class="allocation-card__title">{{ row.name }}</span>
              <span class="allocation-card__symbol">{{ row.symbol }}</span>
            </span>

            <span class="allocation-card__cell allocation-card__cell--num">
              {{ formatPct(row.weight_pct) }}%
            </span>

            <!-- 编辑态：数字输入（0~100，步长 0.5）；留空 = 不设目标。
                 必须绑 `rows[index]` 而不是 computed 里的 `row`——后者是每次重算
                 产出的新对象，写进去不会落回数据源，输入框会「打完字就跳回原值」。 -->
            <span v-if="editing" class="allocation-card__cell--input">
              <el-input-number
                v-model="rows[index].target"
                size="small"
                :min="0"
                :max="100"
                :step="0.5"
                :precision="2"
                :aria-label="`${row.name} 的目标占比`"
                controls-position="right"
              />
            </span>
            <span
              v-else
              class="allocation-card__cell allocation-card__cell--num"
              :class="{
                'allocation-card__cell--muted': row.target_pct === null
              }"
            >
              {{
                row.target_pct === null
                  ? "未设"
                  : formatPct(row.target_pct) + "%"
              }}
            </span>

            <span
              class="allocation-card__cell allocation-card__cell--num"
              :class="{
                'allocation-card__cell--breached': row.breached,
                'allocation-card__cell--muted': row.deviation_pct === null
              }"
            >
              {{
                row.deviation_pct === null
                  ? "—"
                  : signedPct(row.deviation_pct) + "%"
              }}
            </span>

            <span v-if="editing" class="allocation-card__cell--op">
              <el-button
                text
                size="small"
                :aria-label="`移除 ${row.name}`"
                @click="removeRow(row.symbol)"
                >移除</el-button
              >
            </span>
          </div>
        </div>

        <!-- 编辑态：把移除掉的标的加回来（只能选当前持仓，不能凭空造 code） -->
        <div v-if="editing" class="allocation-card__add">
          <el-select
            v-model="pendingSymbol"
            size="small"
            placeholder="添加标的"
            :disabled="addableSymbols.length === 0"
            aria-label="添加标的"
          >
            <el-option
              v-for="opt in addableSymbols"
              :key="opt.symbol"
              :label="opt.name"
              :value="opt.symbol"
            />
          </el-select>
          <el-button size="small" :disabled="!pendingSymbol" @click="addRow"
            >添加</el-button
          >
        </div>

        <p class="allocation-card__footnote">
          当前 {{ data.configured_count }} 个标的设有目标，其中
          {{ data.breached_count }} 个偏离达到阈值
          {{ formatPct(data.threshold_pct) }} 个百分点。
        </p>
      </template>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
/**
 * 目标配比卡（#2237）。
 *
 * 三态（加载 / 失败 / 数据）由外部传入，本组件不做请求；
 * 编辑态把「标的 → 目标占比」整理成后端 PUT 需要的 `items` 交回页面。
 *
 * 合规：只陈列后端算好的事实（当前 / 目标 / 偏离），不产出任何「该加该减」的措辞。
 */
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type {
  AllocationData,
  AllocationTargetInput
} from "@/api/strategyEngine";

defineOptions({ name: "AllocationTargetCard" });

const props = defineProps<{
  /** GET /api/strategy/allocation/ 的 data；null = 尚未取到 */
  data: AllocationData | null;
  loading?: boolean;
  error?: boolean;
  /** 保存中：只锁「保存」按钮，不遮挡列表 */
  saving?: boolean;
  /** 「立即检查提醒」进行中：只锁该按钮本身 */
  reminderRefreshing?: boolean;
}>();

const emit = defineEmits<{
  save: [items: AllocationTargetInput[]];
  retry: [];
  /** 请求跑一次偏离扫描并写站内通知（页面层调 `refreshReminders`） */
  "refresh-reminders": [];
}>();

/** 编辑行：target 为 null 表示「这一行不设目标」，保存时会被剔除 */
interface EditRow {
  symbol: string;
  name: string;
  target: number | null;
}

const editing = ref(false);
const rows = ref<EditRow[]>([]);
const pendingSymbol = ref("");

/** 每行展示所需：把编辑行的目标值合并回后端返回的事实行 */
const visibleRows = computed(() => {
  const items = props.data?.items ?? [];
  if (!editing.value) {
    return items.map(item => ({
      symbol: item.symbol,
      name: item.name || item.symbol,
      weight_pct: item.weight_pct,
      target_pct: item.target_pct,
      deviation_pct: item.deviation_pct,
      breached: item.breached,
      target: item.target_pct
    }));
  }
  return rows.value.map(row => {
    const item = items.find(i => i.symbol === row.symbol);
    return {
      symbol: row.symbol,
      name: row.name,
      weight_pct: item?.weight_pct ?? 0,
      // 编辑态下「目标」以用户输入为准，但仍用后端事实判断越线以外的展示
      target_pct: row.target,
      deviation_pct:
        row.target === null ? null : (item?.weight_pct ?? 0) - row.target,
      breached: item?.breached ?? false,
      target: row.target
    };
  });
});

/** 编辑态顶部提示：目标总和（百分点，不强制 100） */
const targetSum = computed(() =>
  rows.value.reduce((sum, row) => sum + (row.target ?? 0), 0)
);

/** 可添加的标的 = 当前持仓里还没出现在编辑行里的 */
const addableSymbols = computed(() => {
  const taken = new Set(rows.value.map(row => row.symbol));
  return (props.data?.items ?? [])
    .filter(item => !taken.has(item.symbol))
    .map(item => ({ symbol: item.symbol, name: item.name || item.symbol }));
});

function enterEdit() {
  rows.value = (props.data?.items ?? []).map(item => ({
    symbol: item.symbol,
    name: item.name || item.symbol,
    target: item.target_pct
  }));
  pendingSymbol.value = "";
  editing.value = true;
}

function cancelEdit() {
  editing.value = false;
  pendingSymbol.value = "";
}

function removeRow(symbol: string) {
  rows.value = rows.value.filter(row => row.symbol !== symbol);
}

function addRow() {
  const symbol = pendingSymbol.value;
  if (!symbol) return;
  const item = (props.data?.items ?? []).find(i => i.symbol === symbol);
  if (!item) return;
  rows.value = [
    ...rows.value,
    { symbol, name: item.name || symbol, target: item.target_pct }
  ];
  pendingSymbol.value = "";
}

/**
 * 保存：只提交填了数字的那些行。
 *
 * 后端是**整体覆盖**语义——没提交就等于「这个标的没有目标」，
 * 所以留空的行不能带上 0（0% 是一个合法目标，会被当成真目标写进去）。
 */
function submitEdit() {
  const items: AllocationTargetInput[] = rows.value
    .filter(row => row.target !== null)
    .map(row => ({ symbol: row.symbol, target_weight: row.target as number }));
  emit("save", items);
}

/** 保存成功后回到只读态：用最新返回值重画列表，避免残留编辑中的临时值 */
watch(
  () => props.saving,
  (now, prev) => {
    if (prev && !now) editing.value = false;
  }
);

/**
 * 百分点展示：最多两位小数、去掉无意义的尾零。
 * 阈值「5」显示成「5」比「5.00」更像人话；占比 46.2 仍保留一位。
 */
function formatPct(value: number | null | undefined): string {
  return String(Number((value ?? 0).toFixed(2)));
}

/** 偏离带正负号：正号要显式补出来，负数自带符号（且不得取绝对值） */
function signedPct(value: number): string {
  return value > 0 ? `+${formatPct(value)}` : formatPct(value);
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.allocation-card {
  display: flex;
  flex-direction: column;

  /* 标题行右侧可能放两枚按钮（取消 / 保存），窄容器下靠它折行而不是溢出卡片 */
  &__actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }

  &__hint,
  &__guide,
  &__sum,
  &__footnote {
    margin: 0;
    font-size: var(--text-label);
    line-height: 1.6;
    color: var(--text-tertiary-ink);
  }

  &__guide,
  &__sum {
    margin-bottom: var(--space-3);
  }

  /* 目标总和用品牌文字级突出：它是编辑时唯一需要盯住的合成数字 */
  &__sum {
    font-weight: 600;
    color: var(--brand-ink);
  }

  &__footnote {
    margin-top: var(--space-3);
  }

  &__error {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }

  &__error-text {
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  &__rows {
    display: flex;
    flex-direction: column;
    max-height: 320px;
    overflow-y: auto;
  }

  &__row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 72px 72px 80px 56px;
    gap: var(--space-2);
    align-items: center;
    padding: var(--space-2) var(--space-2);
    border-bottom: 1px solid var(--border-light);
    border-radius: var(--radius-sm);

    /* 窄屏：压缩数字列宽，让标的名占满剩余空间。
       放在 &--readonly 之前是有意的级联顺序：同特异性下源序即优先级，
       只读态的窄屏列宽在 &--readonly 内再压一档，见下方注释。 */
    @include bp.below("md") {
      grid-template-columns: minmax(0, 1fr) 64px 64px 72px 48px;
      gap: var(--space-1);
    }

    /* 越线：整行给一层暖沙金底纹——它是「你定的线被越过了」，
       用告警色而非涨跌色，避免被读成「亏了」 */
    &--breached {
      background: var(--color-warning-20);
    }

    &--head {
      padding-top: 0;
      font-size: 12px;
      color: var(--text-tertiary-ink);
      border-bottom-color: var(--border-default);
    }

    /* 只读态没有「移除」列：收掉列宽，否则行尾空出 56px */
    &--readonly {
      grid-template-columns: minmax(0, 1fr) 72px 72px 80px;

      @include bp.below("md") {
        grid-template-columns: minmax(0, 1fr) 64px 64px 72px;
      }
    }
  }

  &__cell {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-label);
    color: var(--text-secondary);
    white-space: nowrap;

    &--num {
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
      text-align: right;
    }

    &--muted {
      color: var(--text-tertiary-ink);
    }

    /* 偏离值越线：文字级告警色（底色级令牌作正文不足 4.5:1） */
    &--breached {
      font-weight: 600;
      color: var(--color-warning-ink);
    }

    &--op {
      text-align: right;
    }
  }

  &__name {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__title {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-label);
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__symbol {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-tertiary-ink);
  }

  &__add {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    margin-top: var(--space-3);
  }

  /* 窄屏适配已并入 &__row / &__row--readonly 内部（媒体查询必须贴着它覆盖的
     规则放：同特异性下源序即优先级，提到外层块尾会被后面的基础规则压掉，
     详见 stylelint.config.js 的 order/order 注释与 ExploreDetailPanel 同族注释） */
}
</style>
