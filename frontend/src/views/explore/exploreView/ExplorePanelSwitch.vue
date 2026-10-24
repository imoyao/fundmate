<script setup lang="ts">
import { nextTick, ref } from "vue";
import {
  PANEL_HINTS,
  PANEL_TABS,
  nextTabIndex,
  type PanelKey
} from "./usePanelSwitch";

/**
 * 档位切换条（2026-10 拆分自 views/explore/index.vue）。
 *
 * ARIA tabs 模式（#1549 T4.4）：容器 role=tablist、子项 role=tab + aria-selected +
 * roving tabindex（只有选中项可被 Tab 键到达），←/→/Home/End 切换并把焦点交给新选中项。
 * Enter / Space 不在此绑定：`<button>` 原生 click 已覆盖，重复绑定会触发两次切换。
 *
 * 键盘与焦点属于「切换条自己的事」，所以留在组件内；选哪一档要写回 URL，
 * 属于页面编排，故通过 `switch` 事件抛上去。
 */
const props = defineProps<{ activePanel: PanelKey }>();
const emit = defineEmits<{ (e: "switch", key: PanelKey): void }>();

/** Tab 按钮元素引用表：roving tabindex 下用于把焦点交给新选中项 */
const tabRefs = ref<HTMLButtonElement[]>([]);

const setTabRef = (el: unknown, index: number) => {
  if (el instanceof HTMLButtonElement) tabRefs.value[index] = el;
};

const onTabKeydown = (event: KeyboardEvent, index: number) => {
  const next = nextTabIndex(event.key, index, PANEL_TABS.length);
  if (next < 0) return;
  event.preventDefault();
  emit("switch", PANEL_TABS[next].key);
  nextTick(() => tabRefs.value[next]?.focus());
};
</script>

<template>
  <nav class="panel-switch">
    <div class="panel-switch__inner" role="tablist" aria-label="探市视图切换">
      <button
        v-for="(tab, index) in PANEL_TABS"
        :id="`panel-tab-${tab.key}`"
        :key="tab.key"
        :ref="el => setTabRef(el, index)"
        type="button"
        role="tab"
        class="panel-tab"
        :class="{ 'panel-tab--active': props.activePanel === tab.key }"
        :aria-selected="props.activePanel === tab.key ? 'true' : 'false'"
        :aria-controls="`panel-${tab.key}`"
        :tabindex="props.activePanel === tab.key ? 0 : -1"
        @click="emit('switch', tab.key)"
        @keydown="onTabKeydown($event, index)"
      >
        {{ tab.label }}
      </button>
      <span class="panel-switch__hint">{{
        PANEL_HINTS[props.activePanel]
      }}</span>
    </div>
  </nav>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* ============================================================
   档位切换：分组胶囊 Tab（design.md「分组胶囊 Tab」规范）
   选中态 = 软按钮语义（brand 底 + brand 字），非涨跌色
   ============================================================ */
.panel-switch {
  max-width: var(--layout-content-width);
  padding: var(--space-standard) 24px 0;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 8px;
    align-items: center;
    padding-bottom: 12px;
    overflow-x: auto;
    border-bottom: 1px solid var(--border-subtle);
  }

  &__hint {
    margin-left: auto;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
    white-space: nowrap;
  }
}

.panel-tab {
  flex-shrink: 0;
  height: 32px;
  padding: 0 16px;
  font-family: inherit;
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;

  &:hover {
    background: var(--bg-hover);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }

  &--active {
    color: var(--color-rise-ink);
    background: var(--brand-100);
    border-color: var(--brand-400);

    &:hover {
      background: var(--brand-200);
    }
  }
}

@include bp.below("md") {
  .panel-switch {
    padding: 16px 16px 0;

    &__hint {
      display: none;
    }
  }
}
</style>
