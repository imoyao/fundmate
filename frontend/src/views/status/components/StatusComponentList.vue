<!--
  StatusComponentList · 组件清单（#980 批 B9 从 `views/status/index.vue` 抽出）

  每行：状态点 + 名称 + 要点 + 状态文字，异常时再补一行原因。
  状态到文案/色调的映射走 `statusModel.ts`（纯函数，已单测），本组件只负责排版。
-->
<template>
  <CardBlock>
    <SectionHeader title="组件">
      <template #action>
        <el-button :loading="loading" size="small" @click="emit('refresh')">
          刷新
        </el-button>
      </template>
    </SectionHeader>
    <ul class="component-list">
      <li v-for="row in rows" :key="row.name" class="component-row">
        <span
          class="component-row__dot"
          :class="`component-row__dot--${statusTone(row.status)}`"
          aria-hidden="true"
        />
        <span class="component-row__name">{{ row.name }}</span>
        <span class="component-row__detail">{{ row.detail }}</span>
        <span
          class="component-row__status"
          :class="`component-row__status--${statusTone(row.status)}`"
        >
          {{ statusText(row.status) }}
        </span>
        <p v-if="row.hint" class="component-row__hint">{{ row.hint }}</p>
      </li>
    </ul>
  </CardBlock>
</template>

<script setup lang="ts">
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { statusText, statusTone, type ComponentRow } from "./statusModel";

defineOptions({ name: "StatusComponentList" });

defineProps<{ rows: ComponentRow[]; loading: boolean }>();

const emit = defineEmits<{ refresh: [] }>();
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.component-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.component-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 4px var(--space-3);
  align-items: center;
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);

  @include bp.below("md") {
    grid-template-columns: auto minmax(0, 1fr);
  }

  /* 窄屏：状态文字换到第三行，避免「名称 / 要点 / 状态」三列互相挤压 */
  &:first-child {
    border-top: 0;
  }

  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;

    &--ok {
      background: var(--color-success);
    }

    &--warn {
      background: var(--color-warning);
    }

    &--error {
      background: var(--color-danger);
    }

    &--muted {
      background: var(--text-disabled);
    }
  }

  &__name {
    font-size: var(--text-body);
    color: var(--text-primary);
  }

  &__detail {
    grid-column: 3;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
    white-space: nowrap;

    @include bp.below("md") {
      grid-column: 2;
      white-space: normal;
    }
  }

  &__status {
    justify-self: flex-end;
    font-size: var(--text-small);
    font-weight: 600;
    white-space: nowrap;

    @include bp.below("md") {
      justify-self: flex-start;
    }

    &--ok {
      color: var(--color-success-ink);
    }

    &--warn {
      color: var(--color-warning-ink);
    }

    &--error {
      color: var(--color-danger-ink);
    }

    &--muted {
      color: var(--text-tertiary-ink);
    }
  }

  &__hint {
    grid-column: 1 / -1;
    margin: 6px 0 0;
    font-size: var(--text-label);
    line-height: 1.5;
    color: var(--text-secondary);
  }
}
</style>
