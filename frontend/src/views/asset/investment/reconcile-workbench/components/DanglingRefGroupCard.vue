<template>
  <article class="df-group">
    <header class="df-group__head">
      <div class="df-group__title">
        <span class="df-group__key">{{
          reconGroupTitle(group.symbol, group.display_name)
        }}</span>
        <span class="df-group__symbol">{{ subtitle }}</span>
      </div>
      <div class="df-group__actions">
        <!-- 唯一动作（漏斗，2026-11-13）：阶段动作名由面板标题说一次，
             按钮只叫「处理」；写操作统一在抽屉执行区，导航层零写入口 -->
        <el-button
          size="small"
          type="primary"
          plain
          @click="emit('openItem', group)"
        >
          处理
        </el-button>
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
      <template v-else> · 暂无现存持仓记录</template>
    </p>

    <!-- 错挂组必须说清「现在挂在哪」：用户点「处理」前要能核对是哪条持仓被污染 -->
    <p v-if="wrongLabels" class="df-group__wrong">
      现在挂在 {{ wrongLabels }} 的持仓上
    </p>

    <!-- flags 是后端枚举，翻译成中文再上屏；无 flags 时整个容器不渲染 -->
    <div v-if="flags.length" class="df-group__flags">
      <span v-for="f in flags" :key="f" class="df-group__flag">{{ f }}</span>
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
  reconQuantity,
  reconRecordRef
} from "../utils/reconDisplay";

/**
 * 域 F 单个分组卡（#2866 → 漏斗 2026-11-13）：只展示扫描结果 + 一个「处理」
 * 导航动作；阶段归属已由上游 bucketByStage 决定，本卡不再自己算第二遍。
 * `group.key` 是 `20|001982` 这种后端复合主键，只作 `:key` / 折叠面板 name，
 * 不进视觉层；内部 ID 降级到明细行末尾的「记录编号」。
 */
const props = defineProps<{ group: DanglingRefGroup }>();
const emit = defineEmits<{ openItem: [group: DanglingRefGroup] }>();

const flags = computed(() => props.group.flags.map(reconFlag));
/**
 * 错挂组：这笔流水**现在**挂在哪条持仓上（错误标的）。空表示不是错挂组
 * （悬空组的 position_id 指向已删除的行，没有可点名的持仓）。
 */
const wrongLabels = computed(() =>
  (props.group.wrong_positions ?? [])
    .map(p => `${p.symbol || "标的代码未填"}（${reconRecordRef(p.id)}）`)
    .join("、")
);
/** 逐笔明细的归属说明：错挂组按「挂在 X 的持仓上」写，其余按悬空口径 */
function noteOf(positionId: number): string | undefined {
  const wrong = (props.group.wrong_positions ?? []).find(
    p => p.id === positionId
  );
  return wrong
    ? `挂在 ${wrong.symbol || "标的代码未填"} 的持仓上（${reconRecordRef(positionId)}）`
    : undefined;
}
const detailLines = computed(() =>
  props.group.transactions.map(t =>
    danglingDetailLine(t, noteOf(t.position_id))
  )
);
const subtitle = computed(() =>
  props.group.mislinked
    ? "挂错标的"
    : reconBatchLabel(props.group.batch_label, props.group.txn_count)
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

.df-group__wrong {
  margin: 0 0 6px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
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
