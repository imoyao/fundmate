<!--
  历史会话栏（#1719，方案 A 页内折叠）：
  - 读 GET /api/agent/sessions/（分页，服务端已按 user_id 过滤，跨用户不可见）；
  - 点击某条 → emit select 由父组件拉详情回放，本组件只负责列表与折叠态；
  - 默认折叠：父组件用 v-if 控制显隐，未展开时**不发任何请求**（不给探市/首屏加负担）。
-->
<template>
  <div class="session-history">
    <div class="session-history__head">
      <span class="session-history__title">历史会话</span>
      <span class="session-history__total">{{ total }} 条</span>
      <button
        type="button"
        class="session-history__new"
        @click="emit('newChat')"
      >
        新对话
      </button>
    </div>

    <div v-if="loading && items.length === 0" class="session-history__empty">
      正在加载历史会话
    </div>
    <div v-else-if="items.length === 0" class="session-history__empty">
      还没有历史会话，发出第一条消息后会出现在这里。
    </div>
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
  (e: "newChat"): void;
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
  flex-direction: column;
  max-height: 40vh; // 页内折叠：历史栏自身滚动，不把聊天气泡挤出视口
  padding: var(--space-compact) var(--space-standard);
  background-color: var(--bg-muted);
  border-bottom: 1px solid var(--border-light);
}

.session-history__head {
  display: flex;
  gap: var(--space-compact);
  align-items: center;
  padding-bottom: var(--space-compact);
}

.session-history__title {
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.session-history__total {
  font-size: var(--text-small);
  color: var(--text-tertiary);
}

.session-history__new {
  padding: 0;
  margin-left: auto;
  font-size: var(--text-small);
  color: var(--color-primary);
  cursor: pointer;
  background: none;
  border: none;
}

.session-history__list {
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
  padding: var(--space-compact) var(--space-3);
  text-align: left;
  cursor: pointer;
  background: none;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
}

.session-history__item:hover {
  background-color: var(--bg-card);
  border-color: var(--border-light);
}

.session-history__item--active {
  background-color: var(--bg-card);
  border-color: var(--color-primary);
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
  padding: var(--space-3) 0;
  font-size: var(--text-small);
  color: var(--text-tertiary);
}
</style>
