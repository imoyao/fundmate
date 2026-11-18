<!--
  历史会话列表：
  - 读 GET /api/agent/sessions/（分页，服务端已按 user_id 过滤，跨用户不可见）；
  - 点击某条 → emit select 由父组件拉详情回放；
  - 本组件**只管列表**：外壳（常驻左栏 / 抽屉）、显隐、请求时机都由父组件控制。
    窄屏抽屉用 v-if 挂载，故「不打开就不发请求」这条仍然成立。

  2026-11：去掉自带的卡片外壳与旧配色族（--bg-muted / --border-light / --color-primary），
  那套色是上一代界面语言，嵌在暖色页面里像一个浮起来的浅蓝方块。
  现在条目用暖色 hover/active，容器由父级（左栏 / 抽屉）负责。
-->
<template>
  <div class="session-history">
    <div class="session-history__head">
      <span class="session-history__title">历史会话</span>
      <span class="session-history__total">{{ total }} 条</span>
    </div>

    <p v-if="loading && items.length === 0" class="session-history__empty">
      正在加载
    </p>
    <p v-else-if="items.length === 0" class="session-history__empty">
      还没有历史会话，发出第一条消息后会出现在这里。
    </p>
    <ul v-else class="session-history__list">
      <li v-for="it in items" :key="it.session_id">
        <button
          type="button"
          class="session-history__item"
          :class="{
            'session-history__item--active': it.session_id === activeSessionId
          }"
          :title="it.preview"
          @click="emit('select', it.session_id)"
        >
          <span class="session-history__preview">
            {{ it.preview || "未命名会话" }}
          </span>
          <span class="session-history__meta">
            {{ formatTime(it.updated_at) }} · {{ it.turn_count }} 轮
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { listAgentSessions } from "@/api/agent";
import type { AgentSessionItem } from "@/api/agent";

defineOptions({ name: "SessionHistory" });

const props = defineProps<{
  /** 当前正在续聊的会话 id（用于高亮，可为 null = 尚未建立会话） */
  activeSessionId: string | null;
  /** 父组件每完成一轮对话 / 新对话就 +1，触发本组件重拉列表 */
  refreshToken: number;
}>();

const emit = defineEmits<{
  (e: "select", sessionId: string): void;
}>();

const items = ref<AgentSessionItem[]>([]);
const total = ref(0);
const loading = ref(false);

async function load(): Promise<void> {
  loading.value = true;
  try {
    const res = await listAgentSessions({ page: 1, per_page: 50 });
    items.value = res.data;
    total.value = res.total;
  } catch {
    // 401/403 等由全局拦截器统一提示；这里**不清空已有列表**——
    // 一次刷新失败不该把用户看到的历史抹掉（降级优于闪烁）。
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void load();
});

watch(
  () => props.refreshToken,
  () => {
    void load();
  }
);

/** ISO（东八区）→ 本地 "MM-DD HH:mm"；解析失败返回空串，不抛错 */
function formatTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(
    d.getMinutes()
  )}`;
}
</script>

<style lang="scss" scoped>
.session-history {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-2);
  min-height: 0; /* 列表自身滚动（容器给高度时） */
}

.session-history__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  padding: 0 var(--space-2);
}

.session-history__title {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.session-history__total {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.session-history__list {
  flex: 1;
  min-height: 0;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  list-style: none;
}

.session-history__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 8px var(--space-2);
  margin-bottom: 2px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  background: none;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;

  &:hover {
    background-color: var(--bg-soft);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
}

.session-history__item--active {
  background-color: var(--bg-soft);

  .session-history__preview {
    font-weight: 600;
    color: var(--brand-700);
  }
}

.session-history__preview {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  color: var(--text-primary);
  white-space: nowrap;
}

.session-history__meta {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.session-history__empty {
  padding: 0 var(--space-2);
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary);
}
</style>
