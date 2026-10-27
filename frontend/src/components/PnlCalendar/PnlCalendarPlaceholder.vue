<!--
  PnlCalendarPlaceholder · 收益日历的加载 / 错误 / 空态（#980 从 `index.vue` 抽出，纯搬运）

  三种状态共用一个容器是刻意的：它们在页面上的位置、尺寸、居中方式完全一致，
  状态切换时不会出现「先闪一下矮条再变高」的跳动。

  空态（`kind="empty"`）多两件东西，且都只在**数据缺口**时出现：
  - `ep:info-filled` 图标：说明「这是信息，不是故障」；
  - 「查看 X 有数据」按钮：给出口。用户自己翻区间去试是无穷次尝试，而快照任务
    没跑这件事跟他无关，他真正想看的只是「最近那期长什么样」。

  文案与判据全在 `emptyState.ts`（纯函数，单测直接覆盖），本组件只负责摆放。
-->
<template>
  <div class="pnl-calendar__placeholder">
    <IconifyIconOffline
      v-if="kind === 'empty'"
      icon="ep:info-filled"
      class="text-base"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    />
    <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">
      <template v-if="kind === 'loading'">收益日历加载中…</template>
      <template v-else>{{ text }}</template>
    </span>
    <el-button
      v-if="kind === 'error'"
      size="small"
      text
      type="primary"
      @click="emit('retry')"
    >
      重试
    </el-button>
    <el-button
      v-else-if="kind === 'empty' && jumpText"
      size="small"
      text
      type="primary"
      @click="emit('jump')"
    >
      {{ jumpText }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";

defineOptions({ name: "PnlCalendarPlaceholder" });

defineProps<{
  /** loading：只有一行字；error：多一枚「重试」；empty：多图标与「去有数据那期」 */
  kind: "loading" | "error" | "empty";
  /** 正文（错误态是后端/前端统一后的错误句，空态是解释性长句）；
      `loading` 态用组件内固定文案，无需传 */
  text?: string;
  /** 空态跳转按钮文案；空串 = 不显示（已正在看有数据那一期，跳了也白跳） */
  jumpText?: string;
}>();

const emit = defineEmits<{
  (e: "retry"): void;
  (e: "jump"): void;
}>();
</script>

<style lang="scss" scoped>
.pnl-calendar__placeholder {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  min-height: 140px;
  padding: 16px;
  text-align: center;
}
</style>
