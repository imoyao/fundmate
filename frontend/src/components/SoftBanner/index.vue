<!--
  SoftBanner · 柔性提示条通用组件（#2716，设计文档 docs/spec/soft-banner.md）

  收敛全仓「有底色/边框的非阻断警示条」：此前 DiscrepancyBanner、GhostDuplicateBanner、
  WorkbenchBanner、EaccountDraftBanner、RealtimeWarningBanner 各自手写一份几乎相同的
  `flex + icon + border + radius` 壳，间距、圆角、a11y 语义（role/tabindex）持续漂移。

  职责边界（刻意做薄）：
  - 管：壳布局、variant 配色（全令牌，暗色经 dark.scss 同名覆盖自动成立）、
        role="alert"、可点击交互（hover 提亮 + Enter）、统一关闭按钮、紧凑档。
  - 不管：dismiss 显隐状态（Discrepancy/Ghost 是会话级 sessionStorage、Realtime 是
        localStorage 持久——语义不同，只 emit('close') 交消费方自理）；
        正文排版（default slot 自由内容）。

  class/attrs 透传根元素：消费方可保留 e2e 锚点类名（如 class="recon-banner"）。
-->
<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";

defineOptions({ name: "SoftBanner" });

const props = withDefaults(
  defineProps<{
    /** 色族：info=中性信息（bg-soft）/ warning=暖沙金 / danger=警示红 */
    variant?: "info" | "warning" | "danger";
    /** iconify 图标名（图标语义由消费方定，组件不猜） */
    icon: string;
    /** 整条可点击：cursor + hover 提亮 + Enter 触发 click */
    clickable?: boolean;
    /** 显示右侧关闭按钮；点击仅 emit('close')，显隐状态由消费方管理 */
    dismissible?: boolean;
    /** 紧凑档：单行一次性告知条（padding 4px 12px、margin-bottom 4px） */
    dense?: boolean;
  }>(),
  { variant: "info", clickable: false, dismissible: false, dense: false }
);

const emit = defineEmits<{
  (e: "click"): void;
  (e: "close"): void;
}>();

function onClick(): void {
  if (props.clickable) emit("click");
}
</script>

<template>
  <div
    class="soft-banner"
    :class="[
      `soft-banner--${props.variant}`,
      {
        'soft-banner--clickable': props.clickable,
        'soft-banner--dense': props.dense
      }
    ]"
    role="alert"
    :tabindex="props.clickable ? 0 : undefined"
    @click="onClick"
    @keydown.enter="onClick"
  >
    <IconifyIconOffline
      :icon="props.icon"
      class="soft-banner__icon"
      aria-hidden="true"
    />
    <div class="soft-banner__body">
      <slot />
    </div>
    <div v-if="$slots.actions" class="soft-banner__actions">
      <slot name="actions" />
    </div>
    <button
      v-if="props.dismissible"
      type="button"
      class="soft-banner__close"
      title="关闭提示"
      aria-label="关闭提示"
      @click.stop="emit('close')"
    >
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none">
        <path
          d="M6 6l12 12M18 6L6 18"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
        />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.soft-banner {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: var(--radius-sm);
}

/* ===== variant 配色（全令牌；文字/图形分离遵循 -ink 体系，#1545/#1599） ===== */

/* info：中性信息（原 WorkbenchBanner/EaccountDraftBanner 族） */
.soft-banner--info {
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
}

.soft-banner--info .soft-banner__icon {
  color: var(--color-info-ink);
}

/* warning：暖沙金（原 DiscrepancyBanner 族）。--color-warning 仅作底/边框（白底
   1.68:1 禁作前景），文字走 --color-warning-ink */
.soft-banner--warning {
  color: var(--text-primary);
  background: var(--color-warning-20);
  border: 1px solid var(--color-warning);
}

.soft-banner--warning .soft-banner__icon {
  color: var(--color-warning-ink);
}

/* danger：警示红（原 GhostDuplicateBanner 族）。ink 用 --color-danger-ink
   （白底 4.74:1），不再借「涨」语义的 --color-rise-ink（设计文档 §4 决策） */
.soft-banner--danger {
  color: var(--color-danger-ink);
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger-30);
}

.soft-banner--danger .soft-banner__icon {
  color: var(--color-danger-ink);
}

/* ===== 结构位 ===== */

.soft-banner__icon {
  flex: none;
  font-size: var(--text-body);
}

.soft-banner__body {
  flex: 1 1 auto;
  min-width: 0;
}

.soft-banner__actions {
  display: flex;
  flex: none;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

/* ===== 可点击（原 WorkbenchBanner 交互归一：hover 同族加深一档） ===== */

.soft-banner--clickable {
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.soft-banner--clickable:hover {
  border-color: var(--border-default);
}

.soft-banner--info.soft-banner--clickable:hover {
  background: var(--bg-hover);
}

.soft-banner--warning.soft-banner--clickable:hover {
  background: color-mix(in srgb, var(--color-warning) 32%, transparent);
}

.soft-banner--danger.soft-banner--clickable:hover {
  background: color-mix(in srgb, var(--color-danger) 16%, transparent);
}

.soft-banner--clickable:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* ===== 关闭按钮（原 Discrepancy/Ghost 的 24×24 透明按钮归一） ===== */

.soft-banner__close {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;
}

.soft-banner__close:hover {
  background: var(--bg-hover);
}

/* ===== 紧凑档（原 RealtimeWarningBanner：一次性告知，只占约 30px） ===== */

.soft-banner--dense {
  gap: 12px;
  align-items: center;
  padding: 4px 12px;
  margin-bottom: 4px;
  font-size: var(--text-label);
}

.soft-banner--dense .soft-banner__icon {
  font-size: var(--text-small);
}
</style>
