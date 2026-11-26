<!--
  历史会话列表：
  - 读 GET /api/agent/sessions/（分页 + 标题关键词 q，服务端已按 user_id 过滤，跨用户不可见）；
  - 点击某条 → emit select 由父组件拉详情回放；
  - 本组件**只管列表**：外壳（常驻左栏 / 抽屉）、显隐、请求时机都由父组件控制。
    窄屏抽屉用 v-if 挂载，故「不打开就不发请求」这条仍然成立。

  2026-11：去掉自带的卡片外壳与旧配色族（--bg-muted / --border-light / --color-primary），
  那套色是上一代界面语言，嵌在暖色页面里像一个浮起来的浅蓝方块。
  现在条目用暖色 hover/active，容器由父级（左栏 / 抽屉）负责。

  2026-11-23 可检索：行首改为**标题**（首条用户输入，服务端创建时固化），末条输入退为
  第二行（「聊到哪儿了」），并加标题搜索框（防抖 250ms + 请求序号防串台）。
  标题不能在前端从 messages 取：messages 会被服务端压缩裁剪，首条早就没了。
-->
<template>
  <div class="session-history">
    <div class="session-history__head">
      <span class="session-history__title">历史会话</span>
      <span class="session-history__total">{{ total }} 条</span>
    </div>

    <el-input
      v-model="keyword"
      class="session-history__search"
      size="small"
      clearable
      placeholder="搜索会话标题"
      aria-label="搜索历史会话"
      :prefix-icon="Search"
    />

    <p v-if="loading && items.length === 0" class="session-history__empty">
      正在加载
    </p>
    <p
      v-else-if="items.length === 0 && keyword.trim()"
      class="session-history__empty"
    >
      没有标题包含「{{ keyword.trim() }}」的会话。
    </p>
    <p v-else-if="items.length === 0" class="session-history__empty">
      还没有历史会话，发出第一条消息后会出现在这里。
    </p>
    <ul v-else class="session-history__list">
      <li v-for="it in items" :key="it.session_id" class="session-history__row">
        <button
          type="button"
          class="session-history__item"
          :class="{
            'session-history__item--active': it.session_id === activeSessionId
          }"
          :title="it.preview || it.title"
          :aria-current="it.session_id === activeSessionId ? 'true' : undefined"
          @click="emit('select', it.session_id)"
        >
          <span class="session-history__item-title">
            {{ it.title || "未命名会话" }}
          </span>
          <span
            v-if="it.preview && it.preview !== it.title"
            class="session-history__item-preview"
          >
            {{ it.preview }}
          </span>
          <span class="session-history__item-meta">
            {{ formatTime(it.updated_at) }} · {{ it.turn_count }} 轮
          </span>
        </button>
        <!-- 删除入口（2026-11 用户反馈「历史记录无法删除」）：
             放在条目右上角、hover / 键盘聚焦时才显现——常显会在每行都挂一个红色
             图标，把「浏览列表」这件事压成「一排删除按钮」。
             不可见时同时 pointer-events:none，避免误点；用 Tab 聚焦时 :focus-visible
             会把它显出来，键盘用户依然可达。
             触摸端没有 hover（@media (hover: none)）故常显。 -->
        <button
          type="button"
          class="session-history__del"
          :aria-label="`删除会话：${it.title || '未命名会话'}`"
          :title="
            busy
              ? '分析进行中，结束后可删除'
              : `删除会话：${it.title || '未命名会话'}`
          "
          :disabled="busy || deletingId === it.session_id"
          @click.stop="onDelete(it)"
        >
          <el-icon><Delete /></el-icon>
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { Delete, Search } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import { deleteAgentSession, listAgentSessions } from "@/api/agent";
import type { AgentSessionItem } from "@/api/agent";

defineOptions({ name: "SessionHistory" });

const props = defineProps<{
  /** 当前正在续聊的会话 id（用于高亮，可为 null = 尚未建立会话） */
  activeSessionId: string | null;
  /** 父组件每完成一轮对话 / 新对话就 +1，触发本组件重拉列表 */
  refreshToken: number;
  /** 有一轮分析在跑：此时禁止删除（删掉进行中的会话，服务端那轮的收尾会写回已删行） */
  busy?: boolean;
}>();

const emit = defineEmits<{
  (e: "select", sessionId: string): void;
  /** 已成功删除某会话：父级据此在「删的是当前会话」时回落新对话 */
  (e: "deleted", sessionId: string): void;
}>();

/** 输入防抖：每敲一个字都请求会打满后端（它还要 count 一次做分页） */
const SEARCH_DEBOUNCE_MS = 250;

const keyword = ref("");
const items = ref<AgentSessionItem[]>([]);
const total = ref(0);
const loading = ref(false);
/** 请求序号：慢请求后到不能覆盖新结果（连打搜索框必现的串台） */
let seq = 0;
let timer: ReturnType<typeof setTimeout> | null = null;

async function load(): Promise<void> {
  const mine = ++seq;
  loading.value = true;
  try {
    const res = await listAgentSessions({
      page: 1,
      per_page: 50,
      q: keyword.value.trim() || undefined
    });
    if (mine !== seq) return; // 已被更新的请求取代，丢弃这份结果
    items.value = res.data;
    total.value = res.total;
  } catch {
    // 401/403 等由全局拦截器统一提示；这里**不清空已有列表**——
    // 一次刷新失败不该把用户看到的历史抹掉（降级优于闪烁）。
  } finally {
    if (mine === seq) loading.value = false;
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

watch(keyword, () => {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    void load();
  }, SEARCH_DEBOUNCE_MS);
});

/** 正在删除的会话 id（禁用重复点击；同一时刻只允许一个删除在飞） */
const deletingId = ref<string | null>(null);

/**
 * 删除一条会话（2026-11 用户反馈「历史记录无法删除」）。
 *
 * 二次确认要说清代价（不可恢复），而不是泛泛的「确定删除？」——会话里存的是
 * 用户自己写的追问原文，误删的损失是「一整段对话没了」。取消走 ElMessageBox 的
 * reject，catch 后静默返回。
 *
 * 成功只做**本地移除**、不整表重拉：重拉会让刚删的那条闪一下再消失。
 * 失败（404 / 网络）才重拉——那是「列表与库可能不一致」的唯一信号。
 */
async function onDelete(it: AgentSessionItem): Promise<void> {
  const name = it.title || "未命名会话";
  try {
    await ElMessageBox.confirm(
      `「${name}」的对话记录将永久删除，无法恢复。`,
      "删除会话",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return; // 用户取消
  }
  deletingId.value = it.session_id;
  try {
    await deleteAgentSession(it.session_id);
    items.value = items.value.filter(x => x.session_id !== it.session_id);
    total.value = Math.max(0, total.value - 1);
    emit("deleted", it.session_id);
  } catch {
    // 404 / 网络失败由全局拦截器提示；重拉一次，避免列表与库不一致
    void load();
  } finally {
    deletingId.value = null;
  }
}

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
@use "@/style/scrollbar" as sb;

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

/* 输入框自带内边距，横向留白交给它，这里不再套 padding（否则左右缩进双份） */
.session-history__search {
  width: 100%;
}

.session-history__list {
  flex: 1;
  min-height: 0;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  list-style: none;

  @include sb.thin;
}

.session-history__row {
  position: relative;
}

.session-history__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;

  /* 右侧让出 30px 给删除按钮：不给的话，末行的「MM-DD HH:mm · n 轮」
     会被按钮压住——meta 是最先被吃掉的文字 */
  padding: 8px 30px 8px var(--space-2);
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

/* 删除按钮：平时隐形（每个条目常挂一个危险图标，会把「浏览列表」读成一排删除键），
   指向本行或键盘聚焦时才显形；隐形时 pointer-events:none，避免盲点。
   触摸端没有 hover 语义，@media (hover: none) 下常显。 */
.session-history__del {
  position: absolute;
  top: 5px;
  right: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  color: var(--text-tertiary);
  pointer-events: none;
  cursor: pointer;
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  opacity: 0;
  transition:
    opacity 0.15s ease,
    color 0.15s ease,
    background-color 0.15s ease;

  @media (hover: none) {
    pointer-events: auto;
    opacity: 1;
  }

  &:hover:not(:disabled) {
    color: var(--color-danger);
    background-color: var(--bg-soft);
  }

  /* 键盘聚焦必须显形，否则 Tab 到一个看不见的按钮 */
  &:focus-visible {
    pointer-events: auto;
    outline: none;
    box-shadow: var(--focus-ring);
    opacity: 1;
  }

  &:disabled {
    cursor: not-allowed;
  }
}

.session-history__row:hover .session-history__del,
.session-history__row:focus-within .session-history__del {
  pointer-events: auto;
  opacity: 1;
}

.session-history__item--active {
  background-color: var(--bg-soft);

  .session-history__item-title {
    font-weight: 600;
    color: var(--brand-700);
  }
}

.session-history__item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  color: var(--text-primary);
  white-space: nowrap;
}

.session-history__item-preview {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-disabled);
  white-space: nowrap;
}

.session-history__item-meta {
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
