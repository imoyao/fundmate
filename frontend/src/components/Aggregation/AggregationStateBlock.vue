<script setup lang="ts">
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";

/**
 * 聚合视图的错误态 / 空态块（#980 拆分自 `AggregationPage.vue`）。
 *
 * 两种态共用同一套居中排版，差异只在图标与是否给「重试」：
 * 错误态可重试，空态不可（没有可重试的动作）。原实现中两段模板、
 * 一份样式，拆分后仍是同一份样式，只是换了个宿主。
 */
defineOptions({ name: "AggregationStateBlock" });

const props = withDefaults(
  defineProps<{
    /** error = 请求失败（带重试）；empty = 无数据 */
    kind?: "error" | "empty";
    message: string;
    hint?: string;
  }>(),
  { kind: "empty", hint: "" }
);

const emit = defineEmits<{ retry: [] }>();

const icon = computed(() => (props.kind === "error" ? "ep:warning" : "ep:box"));
</script>

<template>
  <div class="state-block">
    <IconifyIconOffline :icon="icon" class="state-icon" />
    <p class="state-text">{{ message }}</p>
    <p v-if="hint" class="state-hint">{{ hint }}</p>
    <el-button
      v-if="kind === 'error'"
      type="primary"
      plain
      @click="emit('retry')"
    >
      重试
    </el-button>
  </div>
</template>

<style scoped>
.state-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  padding: 60px 20px;
  text-align: center;
}

.state-icon {
  font-size: var(--text-display-lg);
  opacity: 0.3;
}

.state-text {
  font-size: var(--text-body);
  color: var(--text-secondary);
}

.state-hint {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
