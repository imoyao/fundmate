<script setup lang="ts">
import { computed } from "vue";
import { barWidth, tone, type AllocPeer } from "./allocModel";

/**
 * 相关性单行（#980 拆分，#2400 画法）。
 *
 * 两个维度分工，不能混：
 * - **方向 = 几何**：以 0 轴为界，正相关向右、负相关向左。原实现一律向右，
 *   −0.26 与 +0.66 同观感、只差一个负号——这是 #2400 指出并修复的误导源。
 * - **档位 = 颜色**：ρ ≥ 0.8 危险色（账面分散、风险集中），0.4~0.8 明显联动，
 *   ≤ −0.4 反向对冲用信息色（它不是问题），|ρ| < 0.4 中性弱化。
 */
const props = defineProps<{
  peer: AllocPeer;
}>();

const tier = computed(() => tone(props.peer.correlation));
const width = computed(() => barWidth(props.peer.correlation));
</script>

<template>
  <li class="pro-alloc__row" :class="`pro-alloc__row--${tier}`">
    <div class="pro-alloc__row-head">
      <span class="pro-alloc__name">{{ peer.name || peer.symbol }}</span>
      <span class="pro-alloc__rho">
        {{ peer.correlation > 0 ? "+" : "" }}{{ peer.correlation.toFixed(2) }}
      </span>
    </div>
    <div class="pro-alloc__track">
      <div class="pro-alloc__track-half">
        <div
          v-if="peer.correlation < 0"
          class="pro-alloc__bar"
          :style="{ width }"
        />
      </div>
      <div class="pro-alloc__axis" aria-hidden="true" />
      <div class="pro-alloc__track-half">
        <div
          v-if="peer.correlation >= 0"
          class="pro-alloc__bar"
          :style="{ width }"
        />
      </div>
    </div>
    <div class="pro-alloc__row-foot">
      <!-- 编码用于「记录」：加自选 / 搜索 / 对账时按码定位，不靠名称认。
           原样展示，不缩写、不补前缀（与身份卡「代码」项同一原则）。 -->
      <span class="pro-alloc__code" :title="`基金代码 ${peer.symbol}`">{{
        peer.symbol
      }}</span>
      <span>{{ peer.overlap_days }} 个同期交易日</span>
    </div>
  </li>
</template>

<style scoped>
.pro-alloc__row {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.pro-alloc__row-head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
}

.pro-alloc__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.pro-alloc__rho {
  flex-shrink: 0;
  font-size: var(--text-mono-small);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

/* ρ ≥ 0.8：账面分散而风险集中——危险语义红（与涨跌红 --color-rise 刻意区分，#1602） */
.pro-alloc__row--danger .pro-alloc__rho {
  color: var(--color-danger-ink);
}

/* 明显联动 / 反向对冲：提到主文字级，让人看见但不过度刺激 */
.pro-alloc__row--warn .pro-alloc__rho,
.pro-alloc__row--hedge .pro-alloc__rho {
  color: var(--text-primary);
}

/* 关联很弱：弱化到辅助级 */
.pro-alloc__row--low .pro-alloc__rho {
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

/* ===== 发散轨道（#2400）：0 轴居中，正右负左 ===== */
.pro-alloc__track {
  display: flex;
  align-items: center;
  height: 10px;
}

.pro-alloc__track-half {
  display: flex;
  flex: 1;
  align-items: center;
  min-width: 0;
  height: 4px;
}

/* 左半轨：条从 0 轴向左生长（右对齐贴轴） */
.pro-alloc__track-half:first-child {
  justify-content: flex-end;
}

.pro-alloc__axis {
  flex-shrink: 0;
  width: 0;
  height: 14px;
  border-left: 1px dashed var(--border-default);
}

.pro-alloc__bar {
  height: 100%;
  background: var(--border-default);
  border-radius: var(--radius-pill);
}

/* 右半轨的条：左端贴 0 轴，圆角留右端 */
.pro-alloc__track-half:last-child .pro-alloc__bar {
  border-radius: var(--radius-pill) 0 0 var(--radius-pill);
}

/* 左半轨的条：右端贴 0 轴，圆角留左端 */
.pro-alloc__track-half:first-child .pro-alloc__bar {
  border-radius: 0 var(--radius-pill) var(--radius-pill) 0;
}

/* 四档配色（#2400）：档位→令牌单一映射，只在此处出现一次 */
.pro-alloc__row--danger .pro-alloc__bar {
  background: var(--color-danger);
}

.pro-alloc__row--warn .pro-alloc__bar {
  background: var(--color-warning-fill);
}

.pro-alloc__row--hedge .pro-alloc__bar {
  background: var(--color-info);
}

.pro-alloc__row--low .pro-alloc__bar {
  background: var(--border-default);
}

.pro-alloc__row-foot {
  display: flex;
  gap: var(--space-2);
  justify-content: space-between;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 编码：等宽 + 辅助级（#2400）。名称是阅读对象、编码是记录对象，视觉权重必须
   低于名称——故不加标签底色、不加边框，只靠等宽字形与弱化色区分。 */
.pro-alloc__code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono, monospace);
  font-size: var(--text-mono-small);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}
</style>
