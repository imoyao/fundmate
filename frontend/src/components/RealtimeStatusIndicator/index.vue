<template>
  <div v-if="status !== 'idle'" class="realtime-status">
    <span class="status-dot" :class="statusClass" />
    <span class="status-text" :style="{ color: 'var(--text-secondary)' }">
      {{ statusText }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { formatDateTime } from "@/utils/date";

const props = withDefaults(
  defineProps<{
    status: string;
    lastUpdateTime?: string;
  }>(),
  {
    lastUpdateTime: ""
  }
);

const statusClass = computed(
  () =>
    ({
      trading: "trading", // 拉取中（红色脉冲）
      success: "success", // 拉取成功（静态绿色）
      closed: "closed", // 休市（静态灰色）
      error: "error", // 接口降级/报错（静态橙色）
      idle: ""
    })[props.status] || ""
);

const statusText = computed(() => {
  // 统一格式：2026-07-18 14:30（不带秒），ISO 字符串由公共函数幂等收敛
  const time = formatDateTime(props.lastUpdateTime);
  switch (props.status) {
    case "trading":
      return `实时更新中 · ${time}`;
    case "success":
      return `数据更新于 ${time}`; // ✅ 成功时的文案
    case "closed":
      return "已收盘 · 显示昨日净值";
    case "error":
      return "估值服务降级 · 显示最新净值";
    default:
      return "";
  }
});
</script>

<style scoped>
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.3;
  }
}

.realtime-status {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
}

.status-dot {
  width: 8px;
  height: 8px;
  background-color: var(--text-disabled);
  border-radius: 50%;
}

/* 拉取中 (红) */
.status-dot.trading {
  background-color: var(--color-rise);
  animation: pulse 2s infinite;
}

/* ✅ 成功 (绿) */
.status-dot.success {
  background-color: var(
    --color-success
  ); /* 需要你在全局CSS定义 --color-success，或者直接用 #7BC49A */
}

.status-dot.closed {
  background-color: var(--text-disabled);
}

.status-dot.error {
  background-color: var(--color-warning);
}
</style>
