<!--
  账本精灵对话页（2026-11 布局重构）。

  ## 这一版解决什么
  上一版是「页头 + 会浮起来的折叠历史卡 + 居中 hero + 贴底 dock」，实测有四个问题：
  1. **最新回复根本看不见**：`scrollChat()` 写的是 `.chat-list` 的 scrollTop，而那是
     `overflow: visible` 的非滚动元素（#1714 改成页面级滚动时漏迁）——写进去无效。
     实测连问 3 轮后最后一条答案底部在 1404px、dock 顶部在 776px，用户必须自己往下拖。
     现在 `.chat-list` 重新成为**唯一滚动容器**，滚到底用 `bottomRef.scrollIntoView()`
     （让浏览器自己找滚动祖先，不再假设某层能滚）。
  2. **空态是营销海报 + 两个重复入口**：大标语「你未曾留意的账 / 账本精灵全部记清」，
     下面 3 个示例块，输入区又挂 3 个同义 chips。现在空态是 8 项能力目录（点即问），
     输入区只留输入框。
  3. **会话列与输入区不等宽**：消息列 820px 居中、dock 满宽，中间大片空白，表格被挤进
     气泡 78% 宽度里。现在消息列吃满可用宽度（上限 760px），结构化块可占满整列。
  4. **历史栏是浮起来的浅蓝卡片**：用的是旧配色族（--bg-muted / --border-light），
     与暖色页面不是一套语言，展开时还把会话列整体右移。现在它是**常驻左栏**
     （≥lg），窄屏改为抽屉，两者共用同一个 SessionHistory。

  ## 职责划分（勿把状态机搬回本文件）
  - 会话状态机（发送/停止/回放/新对话）→ useAgentChat.ts
  - 消息渲染 → components/AgentMessageItem.vue
  - 空态能力目录 → components/AgentHero.vue
  - 输入 dock → components/AgentComposer.vue
-->
<template>
  <div class="agent-page">
    <PageHeaderBar title="账本精灵" subtitle="查表现、看持仓、问温度">
      <template #action>
        <!-- 窄屏（无左栏）才出现在页头：≥lg 时左栏自带这两件事，页头再放就是重复入口 -->
        <el-button
          text
          size="small"
          class="agent-page__narrow"
          :aria-expanded="historyOpen ? 'true' : 'false'"
          @click="historyOpen = true"
        >
          <el-icon><Clock /></el-icon>
          历史
        </el-button>
        <el-button
          v-if="messages.length > 0 || pending"
          text
          size="small"
          class="agent-page__narrow"
          @click="resetSession"
        >
          新对话
        </el-button>
      </template>
    </PageHeaderBar>

    <div class="agent-body">
      <!-- 常驻左栏（≥lg）：新对话 + 历史会话。
           v-if 而不只是 CSS 隐藏：窄屏挂载会白拉一次会话列表（见 useMediaQuery 注释） -->
      <aside v-if="isWide" class="agent-rail" aria-label="会话导航">
        <div class="agent-rail__inner">
          <!-- 无对话可清空时不渲染（不是禁用）：首屏一个灰着的「新对话」像坏掉的输入框 -->
          <el-button
            v-if="messages.length > 0 || pending"
            class="agent-rail__new"
            @click="resetSession"
          >
            <el-icon><Plus /></el-icon>
            新对话
          </el-button>
          <SessionHistory
            :active-session-id="sessionId"
            :refresh-token="historyRefreshToken"
            @select="switchSession"
          />
        </div>
      </aside>

      <section class="chat-main">
        <div ref="listRef" class="chat-list">
          <div class="chat-stream">
            <AgentHero
              v-if="messages.length === 0 && !pending"
              :capabilities="AGENT_CAPABILITIES"
              @ask="onAsk"
            />

            <AgentMessageItem
              v-for="(m, index) in messages"
              :key="index"
              :message="m"
            />

            <AgentMessageItem v-if="pending" pending />

            <!-- 滚动锚点：新内容进来后滚到这里（浏览器自己找滚动祖先） -->
            <div ref="bottomRef" class="chat-bottom" aria-hidden="true" />
          </div>
        </div>

        <AgentComposer
          ref="composerRef"
          v-model="input"
          :pending="pending"
          :send-disabled="sendDisabled"
          :status-text="statusText"
          @submit="onSubmit"
          @stop="stopPending"
        />
      </section>
    </div>

    <!-- 窄屏历史：抽屉，内容用 v-if 只在打开时挂载（不打开就不发列表请求） -->
    <el-drawer
      v-model="historyOpen"
      title="会话记录"
      direction="rtl"
      size="320px"
      class="agent-drawer"
    >
      <SessionHistory
        v-if="historyOpen"
        :active-session-id="sessionId"
        :refresh-token="historyRefreshToken"
        @select="onDrawerSelect"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Clock, Plus } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SessionHistory from "./components/SessionHistory.vue";
import AgentComposer from "./components/AgentComposer.vue";
import AgentHero from "./components/AgentHero.vue";
import AgentMessageItem from "./components/AgentMessageItem.vue";
import { AGENT_CAPABILITIES } from "./agentQuickActions";
import { useAgentChat } from "./useAgentChat";
import { useMediaQuery } from "@/composables/useMediaQuery";
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
  bottomRef,
  sendDisabled,
  statusText,
  send,
  stopPending,
  switchSession,
  resetSession
} = useAgentChat();

const composerRef = ref<InstanceType<typeof AgentComposer> | null>(null);

/** ≥lg 才有常驻左栏（与 _breakpoints.scss 的 lg 同值 64rem） */
const isWide = useMediaQuery("(min-width: 64rem)");

/** 输入框内容发送（父层清空输入后真正发请求，发完把焦点还给输入框） */
async function onSubmit(): Promise<void> {
  await send();
  composerRef.value?.focus();
}

/** 能力目录直达：发出去，但**不清空**用户已经打好的草稿 */
async function onAsk(text: string): Promise<void> {
  await send(text);
  composerRef.value?.focus();
}

/** 抽屉里选历史：回放后必须收起抽屉，否则用户回不到对话本身 */
async function onDrawerSelect(id: string): Promise<void> {
  await switchSession(id);
  historyOpen.value = false;
}

/**
 * 「问这个」上下文接收（#1764）：持仓 / 自选行入口带来的 query。
 * 只预填输入框、**不自动发送**（不发请求、不烧 token，用户可改再发），
 * 并给一句轻提示说明这句话从哪来。
 *
 * **刻意不摘除 query**：本仓 lay-content 以 fullPath 为 router-view 的 key
 * （lay-content/index.vue），任何 query 改写都会重挂载页面、清空会话消息——
 * 与仓内惯例一致（inventory 的 ?tab= 同样只读不摘）。
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

  /* 高度钉在视口内（减去顶栏）：这是「消息区自己滚、输入区永远在下面」的前提。
     ⚠️ 不能写成 min-height —— 那只是下限，内容一多页面就跟着长高，`.chat-list` 永远撑开、
     不产生滚动，最后一条答案被 sticky 的 dock 压住（本轮实测：内容底部 879 / dock 顶 819）。
     钉死会否引入第二条滚动条？不会：`.agent-page` 加上下留白后仍在外层 el-scrollbar 的
     可视高之内，外层不滚（实测 scrollHeight === clientHeight，见 PR 走查记录）。 */
  height: calc(100vh - var(--layout-topbar-height));
  padding: 0 var(--space-standard) var(--space-standard);
  margin: 0 auto;
}

/* 页头两个按钮只在窄屏出现（≥lg 由左栏承担） */
.agent-page__narrow {
  display: none;

  @include bp.below("lg") {
    display: inline-flex;
  }
}

.agent-body {
  display: flex;
  flex: 1;
  gap: var(--space-6);
  align-items: stretch;
  min-height: 0;
}

/* 左栏：外壳拉满高度（竖线才有尽头），内容 sticky 停留 */
.agent-rail {
  display: flex;
  flex: 0 0 232px;
  padding-right: var(--space-compact);
  border-right: 1px solid var(--border-subtle);

  @include bp.below("lg") {
    display: none;
  }
}

.agent-rail__inner {
  position: sticky;
  top: var(--space-compact);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  max-height: calc(100vh - var(--layout-topbar-height) - 120px);
}

.agent-rail__new {
  width: 100%;
}

.chat-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

/* 唯一滚动容器：发送/停止/回放后由 useAgentChat 的 scrollChat 滚到底。
   min-height: 0 必写——flex 子项的默认 min-height:auto 会让它按内容撑高、不产生滚动 */
.chat-list {
  flex: 1;
  min-height: 0;
  padding: var(--space-compact) 0 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

/* 消息列吃满可用宽度，只设上限（760px ≈ 44 汉字/行）；输入 dock 同宽，两者对齐 */
.chat-stream {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 760px;
  margin: 0 auto;
}

.chat-bottom {
  height: 1px;
}

@include bp.below("md") {
  .agent-page {
    min-height: calc(100vh - 85px);
  }

  .agent-body {
    gap: 0;
  }

  .chat-stream {
    max-width: none;
  }
}
</style>
