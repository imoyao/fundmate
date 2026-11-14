<!--
  底部输入 dock：胶囊输入 + 发送/停止复合按钮（+ 仅在需要时出现的一行状态文案）。

  2026-11 改版：撤掉能力 chips。原因是空态已经有一份 8 项能力目录，
  再在输入区挂 3 个 chip 等于同一批入口渲染两遍——这正是「像 demo」的来源之一。
  输入区回归单一职责：写一句话，发出去。

  「页面级滚动 + 本块 sticky 贴底」（#1714 复核）：既保住输入区常驻底部，
  又只留一条滚动条（外层 el-scrollbar）。必须给不透明底色，否则消息会从下面透出来。

  两个刻意的设计（改动前先读 index.vue 的历史注释）：
  1. **发送与停止是同一个按钮**：思考中不发禁用、而是就地换成方块停止态，
     aria-label / title 同步（页面任何时刻只有一个「发送|停止」按钮）；
  2. **思考中不锁输入框**：可以先把下一句打好，本轮结束立刻能发。
-->
<template>
  <div class="chat-dock">
    <!-- 内容与消息列同宽同轴（760px 居中）：dock 的底色与上边框仍满宽，
         否则输入框会从消息列左边缘再往外伸 80 多像素，看起来像两套栅格 -->
    <div class="chat-dock__inner">
      <!-- 状态文案只在「进行中 / 刚被停止」时出现：空闲时那句「回车发送 · 信息不全会先确认」
           是常驻噪音，快捷键说明留在 placeholder 里即可 -->
      <p v-if="statusText" class="chat-dock__status" role="status">
        {{ statusText }}
      </p>

      <div class="chat-input-row">
        <div class="chat-input-pill">
          <el-input
            ref="taRef"
            v-model="model"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="问一句账户里的数字，Enter 发送，Shift+Enter 换行"
            aria-label="向账本精灵提问"
            @keydown="onKeydown"
          />
        </div>
        <el-button
          type="primary"
          circle
          class="chat-send"
          :aria-label="pending ? '停止' : '发送'"
          :title="
            pending ? '停止分析（Esc）' : '发送（Enter，Shift+Enter 换行）'
          "
          :disabled="sendDisabled"
          @click="onSendClick"
        >
          <span
            v-if="pending"
            class="chat-send__stop-glyph"
            aria-hidden="true"
          />
          <el-icon v-else><ArrowUp /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ArrowUp } from "@element-plus/icons-vue";

defineOptions({ name: "AgentComposer" });

const model = defineModel<string>({ required: true });

const props = defineProps<{
  /** 思考中：复合按钮换成停止态 */
  pending: boolean;
  /** 复合按钮是否不可点（空闲=输入为空；思考中=abort 收尾间隙防连点） */
  sendDisabled: boolean;
  /** 状态一句话（空闲时为空串 = 不渲染这一行） */
  statusText: string;
}>();

const emit = defineEmits<{
  /** 发送输入框里的内容（父层负责清空输入并真正发请求） */
  (e: "submit"): void;
  /** 停止当前分析 */
  (e: "stop"): void;
}>();

const taRef = ref<{ focus: () => void } | null>(null);

function onKeydown(e: KeyboardEvent): void {
  // 思考中 Esc = 停止（与按钮 title 提示一致）：textarea 里 Esc 无默认行为，不抢任何输入
  if (e.key === "Escape" && props.pending) {
    e.preventDefault();
    emit("stop");
    return;
  }
  if (e.key !== "Enter" || e.shiftKey) return;
  // 中文输入法组词期间的 Enter 是确认候选词，不能当发送
  if (e.isComposing) return;
  e.preventDefault();
  emit("submit");
}

/** 复合按钮点击（#1714 UI 复核）：一按钮两态——思考中点是停止，空闲才是发送 */
function onSendClick(): void {
  if (props.pending) {
    emit("stop");
    return;
  }
  emit("submit");
}

/** 供父层在一轮结束后把焦点还给输入框（原实现写在 send 的 finally 里） */
function focus(): void {
  taRef.value?.focus();
}

defineExpose({ focus });
</script>

<style lang="scss" scoped>
/* 输入 dock：列底的一根横条，**不再 sticky**——消息区改成内部滚动后（见 index.vue），
   它本来就永远停在列底，sticky 已无意义；而叠加的底色反而在暗色下露出色差
   （实测：页面实测底色 != --bg-page，dock 涂 --bg-page 会在列底切出一条亮带）。
   border-top 只画分隔线，底色交给页面。

   ⚠️ 本页在 FAB 隐藏清单内（constants/fab.ts 的 /agent），故不预留 --layout-fab-safe。
   若将来把它从清单摘掉，必须同时恢复 `padding-right: var(--layout-fab-safe)`，
   否则发送按钮会被 FAB 压住（#1773 实测）。 */
.chat-dock {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  padding: var(--space-3) 0 var(--space-standard);
  border-top: 1px solid var(--border-subtle);
}

.chat-dock__inner {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
  max-width: 760px;
  margin: 0 auto;
}

.chat-dock__status {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.chat-input-row {
  display: flex;
  gap: var(--space-2);
  align-items: flex-end;
}

.chat-input-pill {
  /* 胶囊即焦点容器：输入框自身的底色 / 边框全部让位（透明），
     焦点表达完全交给下面的 &:focus-within —— 这样整块只有一个环（#1714 / #1772）。
     视觉参数走 element-plus.scss「输入基线」的 --input-* 令牌，不再 :deep。 */
  --input-bg: transparent;
  --input-border-color: transparent;
  --input-focus-shadow: none;
  --input-radius: var(--radius-pill);
  --input-textarea-padding: 4px 8px;
  --input-textarea-resize: none;

  flex: 1;
  padding: 5px 8px 5px 18px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;

  /* 焦点样式**只画一次**（#1714 复核）：此前是「border 变红 + --focus-ring 双段阴影」叠加，
     视觉上就是内外好几圈线。这里让 border 让位给焦点环（透明），只留干净的一环。
     内部 textarea 的静态描边 / :focus 描边由上面的令牌清空，
     否则 EP 的 `0 0 0 1px … inset` 会在胶囊里再描一圈（「很奇怪的外圈」根因）。 */
  &:focus-within {
    border-color: transparent;
    box-shadow: var(--focus-ring);
  }
}

.chat-send {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;

  // 主按钮物理反馈（design.md「按钮物理反馈」）：按下有「被吸进去」的手感。
  // 发送 / 停止两态共用同一按钮：只换图标，不换底色、不换尺寸、不换位置（#1714 UI 复核）
  &:active {
    transform: translateY(1px);
  }
}

// 停止方块：12px 圆角方块 + currentColor（跟随按钮文字色 --text-inverse，两主题恒为白，
// 落在 --brand-solid 实底 4.92:1，达 WCAG AA 图形 3:1）。不复用图标库的 VideoPause——
// 双竖线是「暂停」语义，方块才是「停止」
.chat-send__stop-glyph {
  width: 12px;
  height: 12px;
  background-color: currentColor;
  border-radius: 2px;
}
</style>
