<!--
  TemperatureGaugeCard · 温度环形卡（三页复用）
  纯 SVG 圆环，不引入 echarts。颜色按数值档位取全局 token（单一来源）：
    综合市场温度：<40 → --temp-low（绿·机会），40–60 → --temp-mid（金·平稳），>60 → --temp-high（红·谨慎）
  标题行右侧固定 TemperatureLevelBadge（与设计约束一致）。
  页面差异通过 props 表达：
    - size:  'lg' 温度计页英雄卡（大） / 'sm' 探市页入口卡（小）
    - featured: 温度计页英雄卡渐变底 + 品牌描边
    - clickable: 探市页点击进入温度计
    - #footer 插槽: 探市页在卡内追加进度条 / 跳转提示等额外信息
-->
<template>
  <div
    class="gauge-card"
    :class="[
      `gauge-card--${size}`,
      { 'gauge-card--featured': featured, 'gauge-card--clickable': clickable }
    ]"
    @click="onClick"
  >
    <div class="gauge-ring">
      <svg viewBox="0 0 120 120" class="gauge-svg">
        <circle class="gauge-track" cx="60" cy="60" r="50" fill="none" />
        <circle
          class="gauge-fill"
          cx="60"
          cy="60"
          r="50"
          fill="none"
          :stroke="ringColor"
          :stroke-dasharray="circumference"
          :stroke-dashoffset="dashOffset"
        />
      </svg>
      <div class="gauge-value">
        <span class="gauge-number">{{ displayValue }}</span>
        <sup class="gauge-degree">°</sup>
      </div>
    </div>

    <div class="gauge-info">
      <div class="gauge-title-row">
        <span class="gauge-title">{{ title }}</span>
        <TemperatureLevelBadge
          v-if="level"
          :level="level"
          :size="size === 'sm' ? 'sm' : 'md'"
        />
      </div>
      <div v-if="caption" class="gauge-caption">{{ caption }}</div>
      <div v-if="updatedAt" class="gauge-updated">更新：{{ updatedAt }}</div>
      <div v-if="$slots.footer" class="gauge-footer">
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";

type TemperatureTone = "low" | "mid" | "high";

const props = withDefaults(
  defineProps<{
    /** 温度数值（0-100），null 显示 -- */
    value?: number | null;
    /** 标题，默认「综合市场温度」 */
    title?: string;
    /** 等级文案，传给 TemperatureLevelBadge（如「偏低（机会）」） */
    level?: string;
    /** 说明文案 */
    caption?: string;
    /** 更新时间 */
    updatedAt?: string;
    /** 尺寸：lg 温度计英雄卡 / sm 探市入口卡 */
    size?: "lg" | "sm";
    /** 英雄卡样式（渐变底 + 品牌描边） */
    featured?: boolean;
    /** 是否可点击（探市卡进入温度计） */
    clickable?: boolean;
    /** 显式色调，优先级高于数值推断（用于非综合温度的环形，如可转债） */
    tone?: TemperatureTone;
  }>(),
  {
    value: null,
    title: "综合市场温度",
    level: "",
    caption: "",
    updatedAt: "",
    size: "lg",
    featured: false,
    clickable: false,
    tone: "" as TemperatureTone
  }
);

const emit = defineEmits<{ (e: "click"): void }>();

const RADIUS = 50;
const circumference = 2 * Math.PI * RADIUS;

const displayValue = computed(() => {
  const v = props.value;
  return v !== null && v !== undefined && !Number.isNaN(v)
    ? Math.round(v)
    : "--";
});

const dashOffset = computed(() => {
  const v = props.value;
  const ratio =
    v !== null && v !== undefined && !Number.isNaN(v)
      ? Math.max(0, Math.min(100, v)) / 100
      : 0;
  return circumference * (1 - ratio);
});

// 综合市场温度档位：<40 低，40–60 中，>60 高
const inferredTone = computed<TemperatureTone>(() => {
  const v = props.value;
  if (v === null || v === undefined || Number.isNaN(v)) return "mid";
  if (v < 40) return "low";
  if (v > 60) return "high";
  return "mid";
});

const ringColor = computed(() => `var(--temp-${props.tone || inferredTone.value})`);

const onClick = () => {
  if (props.clickable) emit("click");
};
</script>

<style lang="scss" scoped>
.gauge-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 24px 28px;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.gauge-ring {
  position: relative;
  width: 120px;
  height: 120px;
  flex-shrink: 0;
}

.gauge-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.gauge-track {
  stroke: var(--bg-soft);
  stroke-width: 8;
}

.gauge-fill {
  stroke-width: 8;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.8s ease, stroke 0.6s ease;
}

.gauge-value {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gauge-number {
  font-size: 34px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.gauge-degree {
  position: absolute;
  top: 22%;
  right: 22%;
  font-size: 16px;
  font-weight: 500;
  color: var(--text-secondary);
  line-height: 1;
}

.gauge-info {
  flex: 1;
  min-width: 0;
}

.gauge-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.gauge-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.gauge-caption {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 6px;
}

.gauge-updated {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.gauge-footer {
  margin-top: 10px;
}

/* ===== 小号（探市入口卡） ===== */
.gauge-card--sm {
  gap: 16px;
  padding: 18px 20px;

  .gauge-ring {
    width: 80px;
    height: 80px;
  }

  .gauge-title {
    font-size: 15px;
  }

  .gauge-number {
    font-size: 22px;
  }

  .gauge-degree {
    font-size: 13px;
    top: 16%;
    right: 16%;
  }
}

/* ===== 英雄卡（温度计页） ===== */
.gauge-card--featured {
  background: linear-gradient(135deg, var(--bg-card), var(--brand-100));
  border-color: var(--brand-400);
  max-width: 520px;
}

/* ===== 可点击（探市入口卡） ===== */
.gauge-card--clickable {
  cursor: pointer;

  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-float);
    border-color: var(--brand-400);
  }
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .gauge-card {
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 20px;
  }
  .gauge-card--sm {
    flex-direction: row;
    text-align: left;
  }
}
</style>
