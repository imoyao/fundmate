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

        <AllocationTargetTable
          :data="data"
          :editing="editing"
          :rows="rows"
          :pending-symbol="pendingSymbol"
          @update-target="onTargetChange"
          @update:pending-symbol="pendingSymbol = $event"
          @remove="removeRow"
          @add="addRow"
        />
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
 *
 * #980 拆分：表格区（行头 / 数据行 / 操作列 / 脚注）→ `AllocationTargetTable`，
 * 派生口径（可见行、可添加标的、保存载荷、百分点格式）→ `allocationTargetModel.ts`。
 * 本文件只保留区块外壳、三态分派与编辑态状态机。
 */
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type {
  AllocationData,
  AllocationTargetInput
} from "@/api/strategyEngine";
import AllocationTargetTable from "./AllocationTargetTable.vue";
import {
  buildSaveItems,
  formatPct,
  sumTargets,
  toEditRows,
  type EditRow
} from "./allocationTargetModel";

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

const editing = ref(false);
const rows = ref<EditRow[]>([]);
const pendingSymbol = ref("");

/** 编辑态顶部提示：目标总和（百分点，不强制 100） */
const targetSum = computed(() => sumTargets(rows.value));

function enterEdit() {
  rows.value = toEditRows(props.data);
  pendingSymbol.value = "";
  editing.value = true;
}

function cancelEdit() {
  editing.value = false;
  pendingSymbol.value = "";
}

/** 表格编辑态回抛：写回本地的编辑行（唯一数据源） */
function onTargetChange(index: number, value: number | null | undefined) {
  rows.value[index].target = value ?? null;
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

/** 保存：只提交填了数字的行（后端整体覆盖语义，留空 ≠ 0%） */
function submitEdit() {
  emit("save", buildSaveItems(rows.value));
}

/** 保存成功后回到只读态：用最新返回值重画列表，避免残留编辑中的临时值 */
watch(
  () => props.saving,
  (now, prev) => {
    if (prev && !now) editing.value = false;
  }
);
</script>

<style lang="scss" scoped>
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
  &__sum {
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

  &__error {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }

  &__error-text {
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  /* 窄屏适配已并入 `AllocationTargetTable` 的 .allocation-card__row 内部
     （媒体查询必须贴着它覆盖的规则放：同特异性下源序即优先级，提到外层块尾会被
     后面的基础规则压掉，详见 stylelint.config.js 的 order/order 注释与
     ExploreDetailPanel 同族注释） */
}
</style>
