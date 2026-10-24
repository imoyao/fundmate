<!--
  账本精灵对话页（#1121 S1-B，2026-09-26 参考竞品截图二次打磨）
  三态渲染：clarify（追问）/ result（结果 + 指标 chips）/ error（服务提示）；
  S2 服务端权威会话：只回带后端下发的 session_id，状态由后端持有（不落地前端）。
  历史会话栏（#1719，方案 A 页内折叠）：见 components/SessionHistory.vue，
  点击历史条目 → 拉 GET /api/agent/sessions/{id}/ 回放并续聊。

  #980 拆分后本文件只剩「页面外壳」：页头操作 + 历史栏开合 + 消息列 + 输入 dock 的接线。
  - 会话状态机（发送/停止/回放/新对话）→ useAgentChat.ts
  - 消息渲染 → components/AgentMessageItem.vue
  - 空态 hero → components/AgentHero.vue
  - 输入 dock（chips + 胶囊输入 + 复合按钮）→ components/AgentComposer.vue
-->
<template>
  <div class="agent-page">
    <PageHeaderBar
      title="账本精灵"
      subtitle="一句话问账户：查表现、看持仓、问温度。只读分析，不改任何数据。"
    >
      <!-- 页面操作收口到页头（#1714 UI 复核）：此前长在对话卡片顶上，
           形成「页头 + 卡片工具栏」双层头部，且「历史」开关离它控制的历史栏很远 -->
      <template #action>
        <el-button
          text
          size="small"
          class="agent-page__history"
          :aria-expanded="historyOpen ? 'true' : 'false'"
          :disabled="pending"
          @click="historyOpen = !historyOpen"
        >
          <el-icon><Clock /></el-icon>
          历史
        </el-button>
        <el-button
          text
          size="small"
          :disabled="pending || messages.length === 0"
          @click="resetSession"
        >
          新对话
        </el-button>
      </template>
    </PageHeaderBar>

    <!-- 页头之下就是对话本身：历史栏（左）+ 会话区（右）。
         不再有「页面里嵌一个聊天卡片」的外壳（#1714 UI 复核） -->
    <div class="chat-shell">
      <!-- 历史栏：页内左栏（#1719 方案 A 的落地形态）。默认折叠时 v-if 不渲染 → 零请求；
           展开时占左列，消息列不会被挤下去（旧实现是插在卡片顶部的折叠块） -->
      <SessionHistory
        v-if="historyOpen"
        :active-session-id="sessionId"
        :refresh-token="historyRefreshToken"
        @select="switchSession"
      />

      <section class="chat-main">
        <div ref="listRef" class="chat-list">
          <div class="chat-stream">
            <!-- 空态：欢迎 hero + 示例问题直达（功能型空态） -->
            <AgentHero
              v-if="messages.length === 0 && !pending"
              :examples="EXAMPLES"
              @ask="onAsk"
            />

            <AgentMessageItem
              v-for="(m, index) in messages"
              :key="index"
              :message="m"
            />

            <AgentMessageItem v-if="pending" pending />
          </div>
        </div>

        <AgentComposer
          ref="composerRef"
          v-model="input"
          :pending="pending"
          :send-disabled="sendDisabled"
          :status-text="statusText"
          :actions="QUICK_ACTIONS"
          @submit="onSubmit"
          @ask="onAsk"
          @stop="stopPending"
        />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Clock } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SessionHistory from "./components/SessionHistory.vue";
import AgentComposer from "./components/AgentComposer.vue";
import AgentHero from "./components/AgentHero.vue";
import AgentMessageItem from "./components/AgentMessageItem.vue";
import { EXAMPLES, QUICK_ACTIONS } from "./agentQuickActions";
import { useAgentChat } from "./useAgentChat";
import {
  agentAskHint,
  agentAskPrefill,
  parseAgentAskQuery
} from "@/utils/agentAsk";

defineOptions({ name: "AgentChat" });

const {
  messages,
  input,
  pending,
  sessionId,
  historyOpen,
  historyRefreshToken,
  listRef,
  sendDisabled,
  statusText,
  send,
  stopPending,
  switchSession,
  resetSession
} = useAgentChat();

const composerRef = ref<InstanceType<typeof AgentComposer> | null>(null);

/** 输入框内容发送（父层清空输入后真正发请求，发完把焦点还给输入框） */
async function onSubmit(): Promise<void> {
  await send();
  composerRef.value?.focus();
}

/** chips / 空态示例直达：发出去，但**不清空**用户已经打好的草稿 */
async function onAsk(text: string): Promise<void> {
  await send(text);
  composerRef.value?.focus();
}

/**
 * 「问这个」上下文接收（#1764）：持仓 / 自选行入口带来的 query。
 * 只预填输入框、**不自动发送**（不发请求、不烧 token，用户可改再发），
 * 并给一句轻提示说明这句话从哪来。
 *
 * **刻意不摘除 query**：本仓 lay-content 以 fullPath 为 router-view 的 key
 * （lay-content/index.vue），任何 query 改写都会重挂载页面、清空会话消息——
 * 与仓内惯例一致（inventory 的 ?tab= 同样只读不摘）。刷新后重预填的是
 * **同一标的**（无「串到别的标的」的错配）；换标的只能来自新入口（新 push）。
 */
const route = useRoute();

onMounted(() => {
  const ctx = parseAgentAskQuery(route.query as Record<string, unknown>);
  if (!ctx) return;
  input.value = agentAskPrefill(ctx);
  ElMessage.info(agentAskHint(ctx));
});
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.agent-page {
  display: flex;
  flex-direction: column;
  max-width: var(--layout-content-width);

  /* 单一滚动条（#1714 复核）：**不再**自算 `height: calc(100vh - 顶栏)` ——
     那种写法把页面高度钉死在视口高，再叠加 Layout（lay-content 的 el-scrollbar）
     自己的滚动容器，右侧就长出两条滚动条（外层 + 聊天区各一条）。
     改为「页面级滚动 + 输入区 sticky 贴底」：min-height 只保证内容少时也占满一屏，
     超出则交给外层那唯一一条滚动条。
     sticky 可用性：el-scrollbar__view 是 `overflow: clip`（不建立滚动容器），
     真正的滚动祖先是 .el-scrollbar__wrap —— 见 lay-content/index.vue 的注释（#1528 同因）。 */
  min-height: calc(100vh - var(--layout-topbar-height));
  padding: 0 var(--space-standard) var(--space-standard);
  margin: 0 auto;
}

/* 页头操作槽里的「历史」开关：文本按钮的轻量观感，与「新对话」同排 */
.agent-page__history {
  gap: var(--space-compact);
  padding: 0 var(--space-3);
  color: var(--text-secondary);
}

/* 页头之下：历史栏（左）+ 会话区（右）。不再有「页面里嵌一个聊天卡片」的外壳——
   去掉卡片的直接收益是页头只剩一层（操作已收进页面头部），聊天区不再像「窗口」 */
.chat-shell {
  display: flex;
  flex: 1;
  gap: var(--space-standard);
}

.chat-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

/* 消息区不再自己滚动（滚动交给外层唯一那条），故去掉 flex:1 + overflow-y:auto */
.chat-list {
  padding: var(--space-compact) 0;
}

/* 消息列限宽居中（阅读行宽约 820px），输入 dock 仍与页面同宽贴底——
   「消息窄、输入宽」是聊天界面的通行比例，整屏铺满的长句难读（#1714 UI 复核） */
.chat-stream {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 820px;
  margin: 0 auto;
}

@include bp.below("md") {
  .agent-page {
    height: auto;
    min-height: calc(100vh - 85px);
  }
}
</style>
