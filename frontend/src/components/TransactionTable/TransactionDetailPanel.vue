<script setup lang="ts">
/**
 * 交易流水 · 行展开详情面板（设计 §十二 第 4 条）。
 *
 * ## 数据是「按需请求」的，不是从列表带下来的
 *
 * 面板的 props 里 `detail` 由容器在**行被展开时**单独取一次（`GET /api/transactions/<id>/`），
 * 拿不到时显示加载态。这样做的理由不是省流量，是省「口径」：
 * `import_hash` / `plan_id` / `updated_at` / `position`（当前份额、清仓时间）只有
 * 展开某一行才用得上，把它们并进列表意味着每页 20 行各算一遍，而绝大多数行永远不会
 * 被展开——更要紧的是，列表响应会因为这些「详情字段」不断变胖，成为下一个
 * 「一次全拿到」的入口。
 *
 * ## 为什么不在这里自己取数
 *
 * 面板只渲染。取数、缓存、重试都在容器（`TransactionTableView`）——它同时管着分页与
 * 列表刷新，知道什么时候该让缓存失效（例如刚编辑完某行）。面板自己 `fetch` 会绕开
 * 这条线，出现「编辑完展开行还显示旧备注」。
 *
 * ## 为什么确认日 / 来源 / 备注要单独占位
 *
 * 设计要求里这三项是展开的**主要理由**：表格的备注列被 `show-overflow-tooltip` 截断、
 * 来源根本没有列、确认日在「交易日优先」的口径里被藏起来了。用户展开一行，
 * 九成是在核这三件事。
 */
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { useEnumLabels } from "@/composables/useEnumLabels";
import { formatDate, formatDateTime } from "@/utils/date";
import { formatQuantity } from "@/utils/format";
import type { TransactionDetail } from "@/api/transactions";
import MigrationNoteTag from "./MigrationNoteTag.vue";
import {
  parseMigrationNote,
  positionStateOf,
  type TransactionRow
} from "./model";

const props = withDefaults(
  defineProps<{
    row: TransactionRow;
    /** 按需取回的详情；`null` 且 `loading=false` 表示还没取或取失败（看 `error`） */
    detail: TransactionDetail | null;
    loading: boolean;
    error?: string | null;
    /** 详情面板里的编辑入口（与表格操作列的「编辑」同一个回调） */
    showEdit?: boolean;
  }>(),
  { error: null, showEdit: false }
);

const emit = defineEmits<{
  edit: [row: TransactionRow];
  retry: [row: TransactionRow];
}>();

const { ensure, positionSourceLabel } = useEnumLabels();
// 来源中文 label 的单一真相源在后端 /api/utils/enums（POSITION_SOURCE_LABELS），
// 前端不手抄。拉取失败只会让来源显示原键（如 `manual`），不会显示空白。
void ensure();

const state = computed(() => positionStateOf(props.row));

const confirmDateText = computed(() => {
  const value = props.detail?.confirm_date;
  // 「没填」与「和交易日同一天」是两件事，不能兜底成交易日——那会让用户以为确认日就是 T 日
  return value ? formatDate(value) : "未填（该笔只有交易日）";
});

const sourceText = computed(() => {
  const source = props.detail?.source;
  if (!source) return "未标记来源（历史数据）";
  return positionSourceLabel(source);
});

/** #3089：归置是只读标记，流水仍显示在列表里，只是不再计入账外类现金 */
const coveredPositionText = computed(() => {
  const id = props.detail?.covered_position_id;
  if (!id) return null;
  const name = props.detail?.covered_position_name;
  const label = name ? ` #${id}（${name}）` : ` #${id}`;
  return `已由持仓${label}体现，不再计入账外类现金`;
});

const positionText = computed(() => {
  const brief = props.detail?.position;
  if (state.value === "account") return "资金流水，不关联持仓";
  if (!brief) {
    return state.value === "cleared"
      ? "持仓行已不存在（历史清仓或合并后的流水）"
      : "持仓信息不可用";
  }
  const clearedSuffix = brief.cleared_at
    ? ` · 已于 ${formatDate(brief.cleared_at)} 清仓`
    : "";
  return `${brief.name} · 剩余 ${formatQuantity(brief.quantity)} 份${clearedSuffix}`;
});

/** 费用明细：未拆分时如实说「未拆分」，不要拿合计冒充四列（那会让人以为本来就零佣金） */
const feeParts = computed(() => {
  const breakdown = props.detail?.fee_breakdown;
  if (!breakdown) return null;
  return [
    { label: "佣金", value: breakdown.commission },
    { label: "印花税", value: breakdown.stamp_duty },
    { label: "过户费", value: breakdown.transfer_fee },
    { label: "其他", value: breakdown.other_fee }
  ];
});

const createdText = computed(() =>
  props.detail?.created_at ? formatDateTime(props.detail.created_at) : "未知"
);

const shortHash = computed(() => {
  const hash = props.detail?.import_hash;
  if (!hash) return "";
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash;
});

/** 备注是否为「迁移占位」：是则渲染安静徽标 + 人话，否则原样显示 */
const noteView = computed(() => parseMigrationNote(props.detail?.notes));
</script>

<template>
  <div class="txn-detail" :aria-busy="loading">
    <p v-if="loading" class="txn-detail__hint">正在读取这条流水的详情…</p>

    <div v-else-if="error" class="txn-detail__error">
      <span>详情没能读出来：{{ error }}</span>
      <el-button text size="small" @click="emit('retry', row)">重试</el-button>
    </div>

    <div v-else-if="detail" class="txn-detail__body">
      <!-- 交易信息：确认日 / 来源 / 定投计划 / 持仓现状 -->
      <section class="txn-detail__group">
        <h4 class="txn-detail__group-title">交易信息</h4>
        <dl class="txn-detail__fields">
          <div class="txn-detail__field">
            <dt>确认日</dt>
            <dd>{{ confirmDateText }}</dd>
          </div>
          <div class="txn-detail__field">
            <dt>来源</dt>
            <dd>{{ sourceText }}</dd>
          </div>
          <div v-if="detail.plan_id" class="txn-detail__field">
            <dt>定投计划</dt>
            <dd>#{{ detail.plan_id }}</dd>
          </div>
          <div
            v-if="coveredPositionText"
            class="txn-detail__field txn-detail__field--wide"
          >
            <dt>归置</dt>
            <dd>{{ coveredPositionText }}</dd>
          </div>
          <div class="txn-detail__field txn-detail__field--wide">
            <dt>持仓现状</dt>
            <dd>{{ positionText }}</dd>
          </div>
        </dl>
      </section>

      <!-- 费用明细 -->
      <section class="txn-detail__group">
        <h4 class="txn-detail__group-title">费用明细</h4>
        <dl class="txn-detail__fields">
          <div class="txn-detail__field txn-detail__field--wide">
            <dd class="txn-detail__fee-list">
              <template v-if="feeParts">
                <span
                  v-for="(part, index) in feeParts"
                  :key="part.label"
                  class="txn-detail__fee"
                >
                  <span v-if="index > 0" class="txn-detail__sep">·</span>
                  {{ part.label }}
                  <MoneyDisplay
                    :value="part.value"
                    :show-sign="false"
                    :show-currency="false"
                    :auto-color="false"
                    size="xs"
                  />
                </span>
              </template>
              <span v-else>
                未拆分（只有合计
                <MoneyDisplay
                  :value="detail.fee"
                  :show-sign="false"
                  :auto-color="false"
                  size="xs"
                />
                ）
              </span>
            </dd>
          </div>
        </dl>
      </section>

      <!-- 备注：迁移占位渲染成安静徽标 + 人话，不再把内部标记甩给用户 -->
      <section class="txn-detail__group">
        <h4 class="txn-detail__group-title">备注</h4>
        <div class="txn-detail__notes-block">
          <MigrationNoteTag v-if="noteView.isMigration" :note="noteView" />
          <p v-else class="txn-detail__notes">{{ detail.notes || "无备注" }}</p>
        </div>
      </section>

      <!-- 记录：导入哈希 / 创建 / 最后修改 -->
      <section class="txn-detail__group">
        <h4 class="txn-detail__group-title">记录</h4>
        <dl class="txn-detail__fields">
          <div class="txn-detail__field txn-detail__field--wide">
            <dd class="txn-detail__meta">
              <span v-if="detail.import_hash" :title="detail.import_hash">
                由导入写入（哈希 {{ shortHash }}）
              </span>
              <span>创建于 {{ createdText }}</span>
              <span
                v-if="
                  detail.updated_at && detail.updated_at !== detail.created_at
                "
              >
                · 最后修改 {{ formatDateTime(detail.updated_at) }}
              </span>
            </dd>
          </div>
        </dl>
      </section>

      <div v-if="showEdit" class="txn-detail__actions">
        <el-button text size="small" @click="emit('edit', row)">
          编辑这笔流水
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 展开区底色比页面浅一档：它属于行内部，不该看起来像又一张卡片 */
.txn-detail {
  padding: var(--space-2) var(--space-standard) var(--space-standard);
  background: var(--bg-soft);
}

.txn-detail__hint {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.txn-detail__error {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  font-size: var(--text-small);
  color: var(--color-danger-ink);
}

.txn-detail__body {
  max-width: 760px;
}

/* 把堆在一起的字段拆成带小标题的分组：标签在上、值在下的「指标块」，
   比「标签—值同行空格分隔」更不挤，也更容易扫读（#2749 关联反馈：详情页太粗糙）。 */
.txn-detail__group {
  padding: var(--space-2) 0;
  border-top: 1px solid var(--border-light);
}

.txn-detail__group:first-child {
  padding-top: 0;
  border-top: none;
}

.txn-detail__group-title {
  margin: 0 0 var(--space-1);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-tertiary-ink);
}

.txn-detail__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2) var(--space-standard);
  margin: 0;
}

.txn-detail__field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.txn-detail__field--wide {
  grid-column: 1 / -1;
}

.txn-detail__field dt {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.txn-detail__field dd {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

/* 备注：保留用户自己敲的换行，超长可滚（不截断——展开的意义就是看全文） */
.txn-detail__notes-block {
  min-width: 0;
}

.txn-detail__notes {
  margin: 0;
  line-height: 1.7;
  color: var(--text-primary);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.txn-detail__fee-list {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-primary);
}

.txn-detail__fee {
  white-space: nowrap;
}

.txn-detail__sep {
  margin: 0 4px;
  color: var(--text-tertiary-ink);
}

.txn-detail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.txn-detail__actions {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--space-2);
  margin-top: var(--space-2);
  border-top: 1px solid var(--border-light);
}
</style>
