<template>
  <article class="df-group">
    <header class="df-group__head">
      <div class="df-group__title">
        <span class="df-group__key">{{ group.key }}</span>
        <span class="df-group__symbol">{{ group.symbol || "缺标的代码" }}</span>
      </div>
      <div class="df-group__actions">
        <el-button
          v-if="group.fixable"
          size="small"
          type="primary"
          plain
          @click="emit('fix', group)"
        >
          去处理
        </el-button>
        <template v-else>
          <el-button size="small" @click="emit('enrich', group)">
            补全信息
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            @click="emit('remove', group)"
          >
            删除
          </el-button>
        </template>
      </div>
    </header>

    <!-- 不能处理时必须说清「差什么」，不能只把按钮置灰让用户猜 -->
    <p v-if="group.block_reason" class="df-group__block">
      {{ group.block_reason }}
    </p>

    <p class="df-group__meta">
      {{ group.txn_count }} 条交易 · 净额 {{ group.net_units }}
      <template v-if="group.live_position">
        · 现存持仓 #{{ group.live_position.id }}（{{
          group.live_position.quantity
        }}
        份，{{ group.live_position.ownership_status }}）
      </template>
      <template v-else> · 对应持仓记录已删除</template>
      · {{ group.batch_label }}
    </p>

    <div class="df-group__flags">
      <el-tag
        v-for="f in group.flags"
        :key="f"
        size="small"
        type="warning"
        effect="plain"
      >
        {{ f }}
      </el-tag>
      <span v-if="!group.flags.length" class="df-group__noflag"
        >无附加标记</span
      >
    </div>

    <!-- 展开看逐条交易：每条都还带着那个已删除的持仓编号 -->
    <el-collapse class="df-collapse">
      <el-collapse-item :name="group.key">
        <template #title
          >查看 {{ group.transactions.length }} 条交易明细</template
        >
        <ul class="df-txns">
          <li v-for="t in group.transactions" :key="t.id" class="df-txn">
            <span class="df-txn__id">#{{ t.id }} {{ t.txn_type }}</span>
            <span>{{ t.trade_date || "缺交易日期" }}</span>
            <span>{{ t.quantity }} 份 / {{ t.amount }} 元</span>
            <span>原持仓编号 #{{ t.position_id }}</span>
          </li>
        </ul>
      </el-collapse-item>
    </el-collapse>
  </article>
</template>

<script setup lang="ts">
import type { DanglingRefGroup } from "@/api/reconciliation";

/** 域 F 单个分组卡（#2866）：只展示扫描结果；可处理的交给「去处理」，
 *  其余交给「补全信息 / 删除」两个入口，动作一律上抛给主视图。 */
defineProps<{ group: DanglingRefGroup }>();
const emit = defineEmits<{
  fix: [group: DanglingRefGroup];
  enrich: [group: DanglingRefGroup];
  remove: [group: DanglingRefGroup];
}>();
</script>

<style scoped>
.df-group {
  padding: 12px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.df-group__head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.df-group__actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

.df-group__title {
  display: flex;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.df-group__key {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-primary-ink);
}

.df-group__symbol {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.df-group__meta {
  margin: 6px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.df-group__block {
  padding: 6px 10px;
  margin: 6px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: color-mix(in srgb, var(--color-warning-ink) 10%, transparent);
  border-radius: var(--radius-sm);
}

.df-group__flags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.df-group__noflag {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.df-collapse {
  border-top: 1px solid var(--border-light);
}

.df-txns {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.df-txn {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 4px 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  border-bottom: 1px dashed var(--border-light);
}

.df-txn__id {
  font-weight: 600;
  color: var(--color-info-ink);
}
</style>
