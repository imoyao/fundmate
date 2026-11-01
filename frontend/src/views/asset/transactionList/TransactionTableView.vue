<script setup lang="ts">
// 交易流水·表格视图（含分页与空态）。状态与取数都在父层，这里只渲染 + 上抛翻页与编辑。
//
// #2712 收编：此前这里是**第四套**交易表格 —— 表头「操作」既指交易类型又指行操作、
// 日期原样打印接口值（`2026-06-03T00:00:00`）、金额/手续费的对齐与账本 Tab 各写各的。
// 用户看到的是「同一批流水在不同页面长得不一样」。现在表格骨架、列序、对齐、
// 日期与价格精度全部交给 `components/TransactionTable`，本组件只留容器职责。
//
// 行展开详情（设计 §十二-4）：**按需请求**。展开一行才取一行，取过就缓存；
// 不在列表里预取，也不把详情字段并进列表接口。缓存的生命周期挂在本组件上——
// 换页 / 换筛选时表格重建，缓存自然清空（旧页的详情在新页没有意义）。
import { computed, ref } from "vue";
import type { TransactionDetail, TransactionRecord } from "@/api/transactions";
import { getTransactionDetail } from "@/api/transactions";
import { IconifyIconOffline } from "@/components/ReIcon";
import TransactionTable from "@/components/TransactionTable/index.vue";
import type { TransactionRow } from "@/components/TransactionTable/model";
import type { TransactionDetailState } from "@/components/TransactionTable/model";

const props = defineProps<{
  transactions: TransactionRecord[];
  loading: boolean;
  total: number;
  currentPage: number;
  pageSize: number;
}>();

const emit = defineEmits<{
  "page-change": [page: number];
  "size-change": [size: number];
  edit: [row: TransactionRow];
}>();

/**
 * 行适配：`/api/transactions` 的字段名与 `TransactionRow` 同名（type / trade_date /
 * price / quantity / amount / fee / status / notes / symbol / position_state），只把
 * `null` 归一成 `undefined`（`TransactionRow.symbol` 是可选字符串，
 * ProductDisplay 收到 null 会渲染 `# --`）。
 * 页面已由后端按「交易日优先、确认日兜底」排序，这里不再重排。
 */
const rows = computed<TransactionRow[]>(() =>
  props.transactions.map(t => ({ ...t, symbol: t.symbol ?? undefined }))
);

/** 行 id → 详情三态。取一次就够，展开/收起不再重复请求。 */
const details = ref<Record<number, TransactionDetailState>>({});

function detailOf(id: number): TransactionDetailState | undefined {
  return details.value[id];
}

function setDetail(id: number, state: TransactionDetailState) {
  // 整体替换而不是原地改属性：`detailOf` 是被 `el-table` 的作用域插槽读的，
  // 原地改不会触发那一层重渲染（Vue 追踪的是 ref 的值，不是它的内部字段）。
  details.value = { ...details.value, [id]: state };
}

async function loadDetail(id: number) {
  const existing = details.value[id];
  // 已有数据 / 正在取 → 不重复请求。失败态（error 非空）**允许**重进，
  // 但入口是面板上的「重试」，不是再次展开——避免收起再展开变成无限打接口。
  if (existing && (existing.loading || existing.data)) return;

  setDetail(id, { loading: true, data: null, error: null });
  try {
    const res = await getTransactionDetail(id);
    const data = (res as unknown as { data: TransactionDetail }).data;
    setDetail(id, { loading: false, data, error: null });
  } catch (e: any) {
    // 界面上不甩原始异常：后端 404（流水已被别处删掉）与网络抖动对用户是同一句话
    // 「读不出来」，区别只在重试有没有用——所以给重试入口，不给堆栈。
    setDetail(id, {
      loading: false,
      data: null,
      error: e?.message || "网络或服务异常"
    });
  }
}

function onExpand(row: TransactionRow) {
  void loadDetail(row.id);
}

function onRetryDetail(row: TransactionRow) {
  setDetail(row.id, { loading: false, data: null, error: null });
  void loadDetail(row.id);
}

/**
 * 清空详情缓存（父层在「编辑保存成功」后调用）。
 *
 * 不清的后果很具体：编辑弹窗保存后列表行被 `Object.assign` 更新，但已展开的详情面板
 * 还拿着旧的 `notes` / `amount` —— 用户改完备注，展开行里显示的还是改之前那句。
 */
function clearDetails() {
  details.value = {};
}

defineExpose({ clearDetails });

/** 编辑弹窗需要原始记录（含 ledger_id / source 等），按 id 回查 */
function onEdit(row: TransactionRow) {
  const original = props.transactions.find(t => t.id === row.id);
  emit("edit", (original ?? row) as unknown as TransactionRow);
}
</script>

<template>
  <!-- 加载态留在容器（原表格自带 v-loading，收编到共享组件后不能丢）。
       外层卡片由页面统一提供：筛选卡头与列表同处一张卡（设计 §六），
       这里再包一层 el-card 就会变成「卡中卡」。 -->
  <div v-loading="loading" class="txn-table-view">
    <TransactionTable
      :rows="rows"
      mode="full"
      show-asset
      show-account
      show-expand
      show-fee
      show-status
      show-notes
      show-edit
      sortable
      :detail-of="detailOf"
      @edit="onEdit"
      @expand="onExpand"
      @retry-detail="onRetryDetail"
    />

    <!-- 分页 -->
    <div v-if="total > 0" class="flex justify-end mt-4">
      <el-pagination
        background
        layout="prev, pager, next, sizes, total"
        :total="total"
        :current-page="currentPage"
        :page-size="pageSize"
        :page-sizes="[5, 10, 20, 50]"
        @current-change="page => emit('page-change', page)"
        @size-change="size => emit('size-change', size)"
      />
    </div>

    <div
      v-if="!loading && transactions.length === 0"
      class="txn-table-view__empty"
    >
      <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
      <p>没有符合条件的流水</p>
      <p class="txn-table-view__empty-hint">
        当前筛选下没有任何记录。放宽时间范围，或清空筛选重新看。
      </p>
    </div>
  </div>
</template>

<style scoped>
.txn-table-view {
  padding: var(--space-2) var(--space-compact) var(--space-compact);
}

.txn-table-view__empty {
  padding: var(--space-section) 0;
  color: var(--text-tertiary-ink);
  text-align: center;
}

.txn-table-view__empty-hint {
  margin-top: 4px;
  font-size: var(--text-small);
}
</style>
