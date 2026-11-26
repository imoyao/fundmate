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

  2026-11-26 按日期分组（用户反馈「历史对话占了这么大空间」）：
  一屏内十几条长一个样的条目，没有任何时间坐标，用户既扫不出「今天聊了什么」，
  也分不清「同一问题出现两次」是 bug 还是两天前真的又问了一遍。现在按
  今天 / 昨天 / 更早 分段，组内时间只留 HH:mm（日期已在组标题上），
  「更早」组保留 MM-DD。搜索态**不分组**——搜索结果是跨时间的，
  再插日期标题只会把命中项切碎。

  单条已拆到 SessionHistoryItem.vue（本文件曾 387 行，加分组必然越过 400 行门禁）。
-->
<template>
  <div class="session-history">
    <!-- 标题与条数相邻成组：上一版用 space-between 把「7 条」推到 232px 栏的最右侧，
         与「历史会话」隔了 160px，读起来是一个孤零零的数字，没有「共」字也不知在数什么。 -->
    <div class="session-history__head">
      <span class="session-history__title">历史会话</span>
      <span class="session-history__total">共 {{ total }} 条</span>
    </div>

    <!-- 不加 size="small"：EP 的 small 只有 24px 高，在 232px 栏里是一条细缝，
         既不像输入框也点不准。默认 32px 是鼠标区的正常尺寸。 -->
    <el-input
      v-model="keyword"
      class="session-history__search"
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
    <div v-else class="session-history__list">
      <section v-for="g in groups" :key="g.key" class="session-history__group">
        <h3 v-if="g.label" class="session-history__group-title">
          {{ g.label }}
        </h3>
        <ul class="session-history__group-list">
          <li v-for="it in g.items" :key="it.session_id">
            <SessionHistoryItem
              :item="it"
              :active="it.session_id === activeSessionId"
              :time-label="formatTime(it.updated_at, g.timeOnly)"
              :busy="busy"
              :deleting="deletingId === it.session_id"
              @select="emit('select', it.session_id)"
              @delete="onDelete(it)"
            />
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Search } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import { deleteAgentSession, listAgentSessions } from "@/api/agent";
import type { AgentSessionItem } from "@/api/agent";
import SessionHistoryItem from "./SessionHistoryItem.vue";

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

type SessionGroup = {
  key: string;
  /** 空串 = 渲染时不出组标题（搜索态） */
  label: string;
  /** true = 组标题已含日期，组内时间只留 HH:mm */
  timeOnly: boolean;
  items: AgentSessionItem[];
};

/**
 * 按「今天 / 昨天 / 更早」分组。
 *
 * 用本地日历日切分（构造函数取年月日，而不是 now - 24h）：后者会把「昨天 23:50」
 * 和「今天 00:10」判成同一组，与用户心智不符。
 * 时间解析失败（脏数据 / null）归入「更早」——它至少是条真会话，不该消失。
 * 搜索态不分组：命中项本就跨时间，插日期标题会把结果切碎。
 */
const groups = computed<SessionGroup[]>(() => {
  const list = items.value;
  if (keyword.value.trim()) {
    return [{ key: "search", label: "", timeOnly: false, items: list }];
  }

  const now = new Date();
  const todayStart = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate()
  ).getTime();
  const yesterdayStart = todayStart - 86_400_000;

  const today: AgentSessionItem[] = [];
  const yesterday: AgentSessionItem[] = [];
  const earlier: AgentSessionItem[] = [];

  for (const it of list) {
    const t = it.updated_at ? new Date(it.updated_at).getTime() : Number.NaN;
    if (Number.isNaN(t) || t < yesterdayStart) earlier.push(it);
    else if (t >= todayStart) today.push(it);
    else yesterday.push(it);
  }

  return (
    [
      { key: "today", label: "今天", timeOnly: true, items: today },
      { key: "yesterday", label: "昨天", timeOnly: true, items: yesterday },
      { key: "earlier", label: "更早", timeOnly: false, items: earlier }
    ] as SessionGroup[]
  ).filter(g => g.items.length > 0);
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

/**
 * ISO（东八区）→ 本地时间文案；解析失败返回空串，不抛错。
 * timeOnly=true 时只给 HH:mm（调用方保证组标题已说明是今天/昨天）。
 */
function formatTime(iso: string | null, timeOnly: boolean): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  const hhmm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (timeOnly) return hhmm;
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hhmm}`;
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
  padding: 0 var(--space-2);
}

/* 两个都是辅助正文字级：--text-tertiary 只有 3.43:1，不到 AA，改用 ink 版 */
.session-history__title {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.session-history__total {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 输入框自带内边距，横向留白交给它，这里不再套 padding（否则左右缩进双份） */
.session-history__search {
  width: 100%;
}

.session-history__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;

  @include sb.thin;
}

/* 组与组之间靠留白分开，不画线：左栏已经很窄，再加三条分隔线就是「表格」了 */
.session-history__group + .session-history__group {
  margin-top: var(--space-3);
}

.session-history__group-title {
  padding: 0 var(--space-2);
  margin: 0 0 var(--space-1);
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-tertiary-ink);
}

.session-history__group-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.session-history__empty {
  padding: 0 var(--space-2);
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
