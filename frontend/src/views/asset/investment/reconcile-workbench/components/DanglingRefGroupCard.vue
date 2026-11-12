<template>
  <article class="df-group">
    <header class="df-group__head">
      <div class="df-group__title">
        <span class="df-group__key">{{ reconGroupTitle(group.symbol) }}</span>
        <span class="df-group__symbol">{{ subtitle }}</span>
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
          <!-- 重建持仓：按流水建回被删掉的持仓行（与补字段 / 删数据是三件独立的事） -->
          <el-button
            v-if="canRebuild"
            size="small"
            plain
            @click="emit('rebuild', group)"
          >
            重建持仓
          </el-button>
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
      {{ reconCount(group.txn_count) }} · 净额
      {{ reconQuantity(group.net_units) }}
      <template v-if="group.live_position">
        · 现存持仓 {{ reconQuantity(group.live_position.quantity) }}（{{
          reconOwnership(group.live_position.ownership_status)
        }}）
      </template>
      <template v-else> · 对应持仓记录已删除</template>
    </p>

    <!-- flags 是后端枚举，翻译成中文再上屏；不把 has_candidate 这类码给用户 -->
    <div class="df-group__flags">
      <span v-for="f in flags" :key="f" class="df-group__flag">{{ f }}</span>
      <span v-if="!flags.length" class="df-group__noflag">没有附加异常</span>
    </div>

    <el-collapse class="df-collapse">
      <el-collapse-item :name="group.key">
        <template #title
          >查看 {{ group.transactions.length }} 条交易明细</template
        >
        <ul class="df-txns">
          <li v-for="(line, i) in detailLines" :key="i" class="df-txn">
            <span>{{ line.date }}</span>
            <span>{{ line.type }}</span>
            <span>{{ line.quantity }}</span>
            <span>{{ line.amount }}</span>
            <span class="df-txn__ref">{{ line.note }}</span>
          </li>
        </ul>
      </el-collapse-item>
    </el-collapse>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { DanglingRefGroup } from "@/api/reconciliation";
import { danglingDetailLine } from "../utils/reconQueue";
import {
  reconBatchLabel,
  reconCount,
  reconFlag,
  reconGroupTitle,
  reconOwnership,
  reconQuantity
} from "../utils/reconDisplay";

/**
 * 域 F 单个分组卡（#2866）：只展示扫描结果，写动作一律上抛。
 * `group.key` 是 `20|001982` 这种后端复合主键，只作 `:key` / 折叠面板 name，
 * 不进视觉层；内部 ID 降级到明细行末尾的「记录编号」。
 */
const props = defineProps<{ group: DanglingRefGroup }>();
const emit = defineEmits<{
  fix: [group: DanglingRefGroup];
  enrich: [group: DanglingRefGroup];
  remove: [group: DanglingRefGroup];
  rebuild: [group: DanglingRefGroup];
}>();

const flags = computed(() => props.group.flags.map(reconFlag));
/** 缺代码的组连建哪个持仓都不知道，不显示重建入口 */
const canRebuild = computed(() => !!props.group.symbol.trim());
const detailLines = computed(() =>
  props.group.transactions.map(danglingDetailLine)
);
const subtitle = computed(() =>
  reconBatchLabel(props.group.batch_label, props.group.txn_count)
);
</script>

<style scoped>
.df-group {
  padding: 12px 14px;
  background: var(--bg-card);
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
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.df-group__key {
  font-size: var(--text-body);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.df-group__symbol {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.df-group__meta {
  margin: 6px 0;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}

.df-group__block {
  padding: 6px 10px;
  margin: 6px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-sm);
}

.df-group__flags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.df-group__flag {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
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
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  border-bottom: 1px dashed var(--border-light);
}

.df-txn__ref {
  color: var(--text-tertiary-ink);
}
</style>
