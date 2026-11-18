<!--
  导入预览 · 源文件行数对账条（#2854 的口径，本组件只负责呈现）

## 为什么单独一个组件

原来是 PreviewStep 里的一段内联文案，把「N 行 = a + b + c」压成一行顺读的长句：
数字与标签同字号、同等权重，用户要逐字读才能确认「到底丢没丢行」。而这一屏恰恰是
**用户唯一能发现「有行没进来」的地方**，信息必须一眼可扫。

拆出来后职责也清楚了：
- 数据口径（哪几项相加、何时返回 null）在 `useImportWizard.rowReconciliation`；
- 本组件只做「三段计数 + 未登记操作名 + 补救方式」的呈现，不含任何判据。

## 视觉口径（用户 2026-10-19 定稿的数字规范）

数字是本条的主角：走 `--text-num-strong` + `font-weight: 600` + `tabular-nums`，
标签降到 `--text-label` 次级墨色。颜色克制——只有「未能识别 > 0」这一个关键数字
上语义色（`--color-warning-ink`），其余保持 `--text-primary`，不靠染色抢注意力。
外壳沿用 SoftBanner（variant=warning），不自己再造一层底色/边框。
-->
<script setup lang="ts">
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import SoftBanner from "@/components/SoftBanner/index.vue";
import type { ImportParseError } from "@/api/importer";

defineOptions({ name: "RowReconciliationBanner" });

interface RowReconciliation {
  source: number;
  imported: number;
  ignored: number;
  failed: number;
  balanced: boolean;
  ops: string[];
  reasons: string[];
  hasUnknownOp: boolean;
}

const props = defineProps<{
  reconciliation: RowReconciliation;
  /** 解析失败逐条明细（带行号与券商原文操作名），用于把行号挂到具体操作名上 */
  parseErrors?: ImportParseError[];
}>();

/** 操作名 → 涉及行号：合并同类项，用户按名字定位比按一串行号猜更快 */
const opRows = computed(() => {
  const byOp = new Map<string, number[]>();
  for (const err of props.parseErrors ?? []) {
    const key = err.raw_value || err.message;
    if (!key) continue;
    byOp.set(key, [...(byOp.get(key) ?? []), err.line]);
  }
  return [...byOp.entries()].map(([op, lines]) => ({
    op,
    lines: [...new Set(lines)].sort((a, b) => a - b)
  }));
});

const stats = computed(() => [
  { key: "imported", label: "可导入", value: props.reconciliation.imported },
  { key: "ignored", label: "有意忽略", value: props.reconciliation.ignored },
  { key: "failed", label: "未能识别", value: props.reconciliation.failed }
]);
</script>

<template>
  <SoftBanner class="recon-banner" variant="warning" icon="ep:warning-filled">
    <div class="recon__head">
      <p class="recon__title">
        源文件
        <span class="recon__title-num">{{ reconciliation.source }}</span> 行
      </p>
      <span
        class="recon__pill"
        :class="reconciliation.balanced ? 'is-ok' : 'is-bad'"
      >
        <IconifyIconOffline
          :icon="
            reconciliation.balanced
              ? 'ep:circle-check-filled'
              : 'ep:warning-filled'
          "
        />
        {{ reconciliation.balanced ? "行数已对齐" : "行数对不平" }}
      </span>
    </div>

    <dl class="recon__stats">
      <div
        v-for="item in stats"
        :key="item.key"
        class="recon__stat"
        :class="{ 'is-alert': item.key === 'failed' && item.value > 0 }"
      >
        <dt class="recon__stat-label">{{ item.label }}</dt>
        <dd class="recon__stat-num">{{ item.value }}</dd>
      </div>
    </dl>

    <p v-if="!reconciliation.balanced" class="recon__equation">
      {{ reconciliation.imported }} + {{ reconciliation.ignored }} +
      {{ reconciliation.failed }} ≠
      {{ reconciliation.source }}，请检查源文件是否有合并行或空行
    </p>

    <div v-if="opRows.length" class="recon__unknown">
      <p class="recon__unknown-title">
        未登记的操作名
        <span class="recon__unknown-count">{{ opRows.length }} 类</span>
      </p>
      <div class="recon__chips">
        <span v-for="row in opRows" :key="row.op" class="recon__chip">
          <span class="recon__chip-op">{{ row.op }}</span>
          <span class="recon__chip-lines"
            >第 {{ row.lines.join("、") }} 行</span
          >
        </span>
      </div>
    </div>

    <!-- 逐条原因：新股中签这类「已识别但不支持」的行，后端已给出补救方式，
         只显示业务名等于让用户自己猜下一步。 -->
    <ul v-if="reconciliation.reasons.length" class="recon__reasons">
      <li
        v-for="(reason, index) in reconciliation.reasons"
        :key="index"
        class="recon__reason"
      >
        {{ reason }}
      </li>
    </ul>

    <p v-if="reconciliation.hasUnknownOp" class="recon__hint">
      <IconifyIconOffline icon="ep:info-filled" class="recon__hint-icon" />
      补登记映射后重新导入即可；不要手工编造标的。
    </p>
  </SoftBanner>
</template>

<style scoped>
.recon__head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
}

.recon__title {
  margin: 0;
  font-size: var(--text-body);
  color: var(--text-primary);
}

.recon__title-num {
  font-size: var(--text-num-strong);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.recon__pill {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 1px 8px;
  font-size: var(--text-label);
  line-height: 18px;
  border: 1px solid transparent;
  border-radius: 999px;
}

/* 「已对齐」是中性事实，不是成就：走灰阶，避免成功绿与旁边的「未能识别 N」抢注意力 */
.recon__pill.is-ok {
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-color: var(--border-default);
}

.recon__pill.is-bad {
  color: var(--color-warning-ink);
  background: var(--bg-card);
  border-color: var(--color-warning);
}

.recon__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 0;
}

.recon__stat {
  min-width: 96px;
  padding: 6px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.recon__stat.is-alert {
  border-color: var(--color-warning);
}

.recon__stat-label {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.recon__stat-num {
  margin: 2px 0 0;
  font-size: var(--text-num-strong);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.recon__stat.is-alert .recon__stat-num {
  color: var(--color-warning-ink);
}

.recon__equation {
  margin: 8px 0 0;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--color-warning-ink);
}

.recon__unknown {
  margin-top: 10px;
}

.recon__unknown-title {
  display: flex;
  gap: 6px;
  align-items: baseline;
  margin: 0 0 6px;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.recon__unknown-count {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.recon__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.recon__chip {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  padding: 2px 8px;
  font-size: var(--text-label);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.recon__chip-op {
  font-weight: 600;
  color: var(--text-primary);
}

.recon__chip-lines {
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.recon__reasons {
  padding: 0;
  margin: 8px 0 0;
  list-style: none;
}

.recon__reason {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.recon__hint {
  display: flex;
  gap: 4px;
  align-items: center;
  margin: 8px 0 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.recon__hint-icon {
  color: var(--color-warning-ink);
}
</style>
