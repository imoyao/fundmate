<!--
  账本精灵对话页（2026-11 布局重构）。

  ## 这一版解决什么
  上一版是「页头 + 会浮起来的折叠历史卡 + 居中 hero + 贴底 dock」，实测有四个问题：
  1. **最新回复根本看不见**：`scrollChat()` 写的是 `.chat-list` 的 scrollTop，而那是
     `overflow: visible` 的非滚动元素（#1714 改成页面级滚动时漏迁）——写进去无效。
     实测连问 3 轮后最后一条答案底部在 1404px、dock 顶部在 776px，用户必须自己往下拖。
     现在滚到底用 `bottomRef.scrollIntoView()`（让浏览器自己找滚动祖先，不再假设某层能滚）。
     ⚠️ 2026-11 回退「消息区内部滚动」：内部滚动 = 把滚动私有化，只要外层 el-scrollbar
     还有内容流里的兄弟（页脚 / 对账横幅），就会多出第二条滚动条，且贴底输入区被顶出
     折线。现在回到 design.md 的单一滚动：页面自己滚、dock 用 sticky 贴底。
  2. **空态是营销海报 + 两个重复入口**：大标语「你未曾留意的账 / 账本精灵全部记清」，
     下面 3 个示例块，输入区又挂 3 个同义 chips。现在空态是 8 项能力目录（点即问），
     输入区只留输入框。
  3. **会话列与输入区不等宽**：消息列 820px 居中、dock 满宽，中间大片空白，表格被挤进
     气泡 78% 宽度里。现在消息列吃满可用宽度（上限 760px），结构化块可占满整列。
  4. **历史栏是浮起来的浅蓝卡片**：用的是旧配色族（--bg-muted / --border-light），
     与暖色页面不是一套语言，展开时还把会话列整体右移。现在它是**常驻左栏**
     （≥lg，可收起并记住），窄屏改为抽屉，两者共用同一个 SessionHistory。

  ## 职责划分（勿把状态机搬回本文件）
  - 会话状态机（发送/停止/回放/新对话）→ useAgentChat.ts
  - 消息渲染 → components/AgentMessageItem.vue
  - 空态能力目录 → components/AgentHero.vue
  - 输入 dock → components/AgentComposer.vue
-->
<template>
  <div class="agent-page">
    <PageHeaderBar
      class="agent-page__header"
      title="账本精灵"
      subtitle="查表现、看持仓、问温度"
    >
      <template #action>
        <!-- 页头两个动作已下沉到 AgentHeaderActions（会话记录 + 新对话）：
             「会话记录」一个按钮两种语义（宽屏收/展左栏、窄屏开抽屉），
             可发现性设计与 aria 说明都在该组件头注释里。 -->
        <AgentHeaderActions
          :is-wide="isWide"
          :rail-collapsed="railCollapsed"
          :history-open="historyOpen"
          :show-new="showHeaderNew"
          @toggle-history="onHistoryToggle"
          @new-session="resetSession"
        />
      </template>
    </PageHeaderBar>

    <div class="agent-body">
      <!-- 常驻左栏（≥lg）：新对话 + 历史会话。
           v-if 而不只是 CSS 隐藏：窄屏挂载会白拉一次会话列表（见 useMediaQuery 注释）;
           收起同理——收起后不占宽度、节点不存在，也就不占 Tab 序（宽度归零的
           写法会把一串按钮留在键盘可达范围内，是更糟的可用性）。 -->
      <aside
        v-if="isWide && !railCollapsed"
        id="agent-session-panel"
        class="agent-rail"
        aria-label="会话导航"
      >
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
            :busy="pending"
            @select="switchSession"
            @deleted="onSessionDeleted"
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
        :busy="pending"
        @select="onDrawerSelect"
        @deleted="onSessionDeleted"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Plus } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import AgentHeaderActions from "./components/AgentHeaderActions.vue";
import SessionHistory from "./components/SessionHistory.vue";
import AgentComposer from "./components/AgentComposer.vue";
import AgentHero from "./components/AgentHero.vue";
import AgentMessageItem from "./components/AgentMessageItem.vue";
import { AGENT_CAPABILITIES } from "./agentQuickActions";
import { useAgentChat } from "./useAgentChat";
import { useAgentRail } from "./useAgentRail";
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

/** 左栏收/展偏好（默认展开、收起即记住）：实现与理由见 useAgentRail */
const { railCollapsed, toggle: toggleRail } = useAgentRail();

/** 页头「新对话」：有内容可清，且左栏没有自带入口（收起 / 窄屏）时才补位 */
const showHeaderNew = computed(
  () =>
    (messages.value.length > 0 || pending.value) &&
    (!isWide.value || railCollapsed.value)
);

/** 页头「历史」：宽屏 = 收/展左栏；窄屏 = 开抽屉 */
function onHistoryToggle(): void {
  if (isWide.value) {
    toggleRail();
    return;
  }
  historyOpen.value = true;
}

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
 * 删除会话后的回落（2026-11）：删掉的正是**当前正在聊的**那一条时，必须把
 * 消息与 sessionId 一起清掉——否则输入框还挂在一条已不存在的会话上，
 * 下一句会先 404、再落回新会话（多一次往返 + 一个错误气泡）。
 *
 * 复用 resetSession 而不是手写清空：它还负责 stopped 提示与历史栏刷新计数。
 * 唯一要保住的是抽屉的开合——用户常常是「连删几条」，删完被弹回对话页很烦。
 */
function onSessionDeleted(id: string): void {
  if (id !== sessionId.value) return;
  const keepDrawerOpen = historyOpen.value;
  resetSession();
  historyOpen.value = keepDrawerOpen;
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
  /* 整屏高，但**让页面自己滚**（design.md「整屏高的页面用单一滚动 + sticky 贴底」）。
     ⚠️ 不能写 height —— 钉死视口高等于把「滚动」私有化给 `.chat-list`，外层 el-scrollbar
     若还有任何内容流里的兄弟（对账横幅、页脚、地址栏收起时的 dvh 差），就立刻多出一条
     滚动条，且贴底的输入区会被顶到折线以下（实测有横幅时下沉 40px）。
     min-height 只保证「内容少也占满一屏」，多则交给外层唯一那条滚动条；
     dock 用 sticky 贴底（见 AgentComposer），所以消息再长输入框也不会滚走。

     三个减数：页脚与横幅都在 el-scrollbar 的**内容流**里，不在视口高预算内。
     - 页脚走 `--layout-footer-height` 静态令牌（lay-footer 同源）；
     - 横幅走 `--app-banner-height`：它由 lay-content 用 ResizeObserver 实测后挂上来，
       横幅不出现时是 0px。漏减它就是「横幅一出现、外层又多一条滚动条」——
       2026-11 实测横幅 59px、外层溢出 56px，输入区被顶到折线以下。

     先算出「视口内可用高度」再减横幅：两段 calc 各自都在一行内，
     不必让 prettier 把 var() 折成跨行。 */
  --agent-h: calc(
    100dvh - var(--layout-topbar-height) - var(--layout-footer-height)
  );

  display: flex;
  flex-direction: column;
  max-width: var(--layout-content-width);
  min-height: calc(var(--agent-h) - var(--app-banner-height, 0px));
  padding: 0 0 var(--space-standard);
  margin: 0 auto;
}

/* 页头自带 margin: 0 auto —— flex 子项的 auto 交叉轴外边距会让 align-items: stretch
   失效，页头收缩成内容宽并被居中，与下方内容左边缘错开（PageHeaderBar 注释点名的坑，
   本页实测标题中心比卡片中心偏左约 170px）。这里让它撑满并交出自己的外边距；
   横向内边距由页头自带，所以 `.agent-page` 横向 padding 为 0、由 body 承担，
   两段文字才会落在同一条竖线上。 */
.agent-page__header {
  align-self: stretch;
  margin-inline: 0;
}

.agent-body {
  display: flex;
  flex: 1;
  gap: var(--space-6);
  align-items: stretch;
  min-height: 0;
  padding: 0 var(--space-standard);
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

  /* 120px = 「新对话」按钮 + 上下留白（不参与视口计算的那部分）；
     横幅（--agent-h 里已算进预算）与它一起决定左栏上限 */
  max-height: calc(var(--agent-h) - var(--app-banner-height, 0px) - 120px);
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

/* 消息列：**不滚动**（滚动交给外层唯一那条）。
   历史版本在此处 overflow-y:auto，与外层 el-scrollbar 叠加成双滚动条
   （用户反馈「下拉滚动条太多」的直接来源之一）。滚动定位由 useAgentChat 的
   scrollChat() 负责，它滚的是 bottomRef（让浏览器自己找滚动祖先）。

   ⚠️ `flex: 1 0 auto` 不是可选优化（2026-11-26 用户反馈「输入框位置随时漂移」）：
   去掉 grow 后本块高度严格等于消息内容高，dock 紧跟其后、下方留出整片空白——
   空态（hero 高 518px）时 dock 顶在 781px，发出一条后内容只剩 170px、dock 跳到 433px，
   实测上移 348px，输入框直接跑到屏幕中间。grow 吃掉剩余空间后 dock 才恒定贴底。
   shrink 必须为 0：内容超出一屏时本块要正常长高（页面滚动），不能被压回视口内。 */
.chat-list {
  flex: 1 0 auto;
  padding: var(--space-compact) 0 0;
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
  /* 窄屏页脚会折成两行（免责文案长），不参与高度预算 —— 与宽屏同一套
     「min-height + 页面自己滚」，所以这里只补一个不含页脚的下限即可。
     横幅要减：窄屏文案更容易折行（实测 55 → 80+），减漏了就是多一条滚动条。 */
  .agent-page {
    /* 窄屏页脚折成两行，不进预算 ⇒ 只减顶栏，再减横幅 */
    --agent-h: calc(100dvh - var(--layout-topbar-height));
  }

  .agent-body {
    gap: 0;
  }

  .chat-stream {
    max-width: none;
  }
}
</style>
