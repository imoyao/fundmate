<template>
  <article class="olg-group">
    <header class="olg-group__head">
      <div class="olg-group__title">
        <span class="olg-group__key">{{ title }}</span>
        <span class="olg-group__sub">
          {{ group.txn_count }} 条流水 · {{ batchLabel }}
        </span>
      </div>
      <el-button
        size="small"
        type="primary"
        plain
        :disabled="!fixable"
        @click="emit('fix', group)"
      >
        核对 {{ group.txn_count }} 笔并归入账本
      </el-button>
    </header>

    <!-- 不可回填必须说清「差什么」，不能只把按钮置灰让用户猜 -->
    <p v-if="group.block_reason" class="olg-group__block">
      {{ group.block_reason }}
    </p>

    <p v-if="group.resolved_ledger" class="olg-group__meta">
      拟归入：{{ ledgerName }}
    </p>

    <el-collapse class="olg-collapse">
      <el-collapse-item :name="group.key">
        <template #title>
          查看 {{ group.transactions.length }} 条流水明细
        </template>
        <ul class="olg-txns">
          <li v-for="(line, i) in lines" :key="i" class="olg-txn">
            <span>{{ line.date }}</span>
            <span>{{ line.type }}</span>
            <span>{{ line.account }}</span>
            <span>{{ line.amount }}</span>
            <span :class="line.blocked ? 'olg-txn__block' : 'olg-txn__ok'">
              {{ line.result }}
            </span>
          </li>
        </ul>
        <!-- 内部 ID 收进「技术详情」：需要找客服定位时查得到，但不占主视觉 -->
        <details class="olg-tech">
          <summary>查看记录编号（定位用）</summary>
          <span
            v-for="t in group.transactions"
            :key="t.id"
            class="olg-tech__id"
          >
            记录编号 {{ t.id }}
          </span>
        </details>
      </el-collapse-item>
    </el-collapse>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { OrphanLedgerGroup } from "@/api/reconciliation";
import { orphanDetailLine } from "../utils/reconQueue";
import { reconBatchTime, reconLedgerName } from "../utils/reconDisplay";

/**
 * 域 G 单个归属分组卡（#2875）：只展示后端扫描结果，写动作交给弹窗。
 * 旧版把 `#3029 dividend_tax ... -17.5 元 → #12` 和「按账户名精确同名唯一判定」
 * 直接印在页面上——那是后端实现说明，不是用户要做的事。现在全部走翻译层。
 */
const props = defineProps<{ group: OrphanLedgerGroup }>();
const emit = defineEmits<{ fix: [group: OrphanLedgerGroup] }>();

/** 组级与逐条两级都看，避免组级概括说明把 blocked 行藏起来 */
const fixable = computed(
  () =>
    props.group.block_reason === null &&
    props.group.transactions.length > 0 &&
    props.group.transactions.every(t => t.block_reason === null)
);

const ledgerName = computed(() =>
  reconLedgerName(props.group.resolved_ledger?.name)
);
const title = computed(
  () => props.group.resolved_ledger?.name?.trim() || "无法归属"
);
const batchLabel = computed(() => reconBatchTime(props.group.batch_label));

const lines = computed(() =>
  props.group.transactions.map(t => {
    const line = orphanDetailLine(t);
    return {
      ...line,
      // 用账本名代替「→ #12」：用户要确认的是归到哪个账本，不是数据库主键
      result: line.blocked ? line.result : `可归入 ${ledgerName.value}`
    };
  })
);
</script>

<style scoped>
.olg-group {
  padding: 12px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.olg-group__head {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.olg-group__title {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.olg-group__key {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.olg-group__sub,
.olg-group__meta {
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}

.olg-group__meta {
  margin: 6px 0;
}

.olg-group__block {
  padding: 6px 10px;
  margin: 6px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-sm);
}

.olg-txns {
  padding: 0;
  margin: 6px 0 0;
  list-style: none;
}

.olg-txn {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding: 3px 0;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  line-height: 1.7;
  color: var(--text-secondary);
}

.olg-txn__block {
  color: var(--color-warning-ink);
}

.olg-txn__ok {
  color: var(--color-success-ink);
}

.olg-tech {
  margin-top: 8px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.olg-tech summary {
  cursor: pointer;
}

.olg-tech__id {
  display: inline-block;
  margin: 4px 8px 0 0;
}
</style>
