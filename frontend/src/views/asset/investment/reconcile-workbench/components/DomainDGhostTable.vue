<template>
  <div class="domain-d-body">
    <!-- 空态判据必须同时看两组：只看未忽略组时，「全部忽略了」会连带把
         下方的撤销入口一起藏掉——用户刚做的事找不到地方回退。 -->
    <el-empty
      v-if="!loading && items.length === 0 && ignoredItems.length === 0"
      description="暂无跨账本重复交易"
      :image-size="80"
    />
    <div v-else class="ghost-groups">
      <article v-for="g in items" :key="g.fingerprint" class="ghost-group">
        <header class="ghost-group__head">
          <div class="ghost-group__title">
            <span class="ghost-group__symbol">{{ g.symbol }}</span>
            <span
              v-if="g.symbol_identity !== g.symbol"
              class="ghost-group__identity"
            >
              {{ g.symbol_identity }}
            </span>
          </div>
          <el-button size="small" text @click="emit('ignore', g)">
            忽略此组
          </el-button>
        </header>

        <p class="ghost-group__meta">
          {{ txnTypeLabel(g.txn_type) }}
          · 金额 {{ g.amount_yuan.toLocaleString() }} 元
          <template v-if="g.confirm_date">
            · {{ formatDate(g.confirm_date) }}</template
          >
          · 出现在 {{ g.ledger_names.join("、") }} 共 {{ g.count }} 笔
        </p>

        <!-- 组内明细：每一笔就是「删一份」的候选。顺序由后端固定为 (ledger_id, id) 升序，
             前端不再排序，避免两处口径漂移。 -->
        <ul class="ghost-txns">
          <li v-for="t in g.transactions" :key="t.id" class="ghost-txn">
            <span class="ghost-txn__ledger">{{ t.ledger_name }}</span>
            <span class="ghost-txn__num">
              {{ formatQty(t.quantity) }} 份 @ {{ t.price }}
            </span>
            <span class="ghost-txn__amount">
              {{ t.amount_yuan.toLocaleString() }} 元
            </span>
            <el-button
              size="small"
              text
              type="danger"
              :loading="deletingId === t.id"
              @click="emit('delete-txn', t)"
            >
              删除这条
            </el-button>
          </li>
        </ul>
      </article>

      <!-- 已忽略组：不静默吞掉，给撤销入口（后端 ignore 幂等，撤销不存在也不报错） -->
      <div v-if="ignoredItems.length > 0" class="ghost-ignored">
        <p class="ghost-ignored__title">
          已忽略 {{ ignoredItems.length }} 组（可撤销）
        </p>
        <ul class="ghost-ignored__list">
          <li
            v-for="it in ignoredItems"
            :key="it.id"
            class="ghost-ignored__item"
          >
            <span class="ghost-ignored__label">
              {{ it.symbol || "—" }}
              <template v-if="it.amount_yuan != null">
                · 金额 {{ it.amount_yuan.toLocaleString() }} 元
              </template>
              <template v-if="it.ledger_names.length">
                · {{ it.ledger_names.join("、") }}
              </template>
            </span>
            <el-button
              size="small"
              text
              :loading="undoingId === it.id"
              @click="emit('undo-ignore', it)"
            >
              撤销忽略
            </el-button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatDate } from "@/utils/date";
import { txnTypeLabel } from "@/constants";
import type {
  GhostDuplicateGroupItem,
  GhostDuplicateIgnore,
  GhostDuplicateTxn
} from "@/api/reconciliation";

/**
 * 域 D 跨账本重复交易表（#2151）。
 *
 * WHY 不复用 `DomainBDiscTable`：域 B 的行是「一个标的一条差异」，列是
 * 理论/实际/差异；域 D 的行是「**一组**跨账本重复」，信息形态是
 * 「账本名列表 + 组内 N 条明细」，硬套 B 的三列会把「账本集合」塞进某个格子里。
 * 这里只复用色类与格式化习惯，不套 B 的列结构（`components.md` 的强制复用清单
 * 里没有表格组件）。
 */
defineProps<{
  items: GhostDuplicateGroupItem[];
  ignoredItems: GhostDuplicateIgnore[];
  loading: boolean;
  /** 正在删除的流水 id（用于按钮 loading 态，避免重复点击） */
  deletingId: number | null;
  /** 正在撤销的忽略记录 id */
  undoingId: number | null;
}>();

const emit = defineEmits<{
  ignore: [group: GhostDuplicateGroupItem];
  "undo-ignore": [item: GhostDuplicateIgnore];
  "delete-txn": [txn: GhostDuplicateTxn];
}>();

/** 份额格式：后端已转成可读份额（4 位小数），这里只去掉尾随 0 */
function formatQty(q: number): string {
  return Number.isInteger(q)
    ? String(q)
    : q.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}
</script>

<style scoped>
.domain-d-body {
  padding: 4px 0;
}

.ghost-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ghost-group {
  padding: 12px 14px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm, 8px);
}

.ghost-group__head {
  display: flex;
  gap: 12px;
  align-items: baseline;
  justify-content: space-between;
}

.ghost-group__title {
  display: flex;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.ghost-group__symbol {
  font-size: var(--text-body, 14px);
  font-weight: 600;
  color: var(--text-primary);
}

.ghost-group__identity {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.ghost-group__meta {
  margin: 4px 0 8px;
  font-size: var(--text-label, 13px);
  color: var(--text-secondary);
}

.ghost-txns {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.ghost-txn {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
  padding: 4px 0;
  font-size: var(--text-label, 13px);
  color: var(--text-secondary);
  border-top: 1px dashed var(--border-light);
}

.ghost-txn__ledger {
  min-width: 90px;
  font-weight: 600;
  color: var(--text-primary);
}

.ghost-txn__num,
.ghost-txn__amount {
  color: var(--text-tertiary-ink);
}

.ghost-ignored {
  padding-top: 8px;
  margin-top: 4px;
  border-top: 1px solid var(--border-light);
}

.ghost-ignored__title {
  margin: 0 0 6px;
  font-size: var(--text-label, 13px);
  font-weight: 600;
  color: var(--text-secondary);
}

.ghost-ignored__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.ghost-ignored__item {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
  justify-content: space-between;
  font-size: var(--text-label, 13px);
  color: var(--text-tertiary-ink);
}
</style>
