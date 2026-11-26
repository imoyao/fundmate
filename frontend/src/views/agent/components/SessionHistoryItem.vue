<!--
  历史会话的**单条**（从 SessionHistory 拆出，2026-11-26）。

  拆分动因是规模而非偏好：父组件原本 387 行，加日期分组后必然越过 400 行门禁；
  而条目本身承载三行文字 + 悬停显现的删除按钮，是天然的组件边界。

  职责边界：只管「一条会话长什么样」。列表、分组、加载、删除确认都在父组件——
  条目拿到的是**已格式化好的时间文案**（timeLabel），不自己判断今天/昨天，
  否则同一套日期规则会在两个文件里各写一遍、早晚漂移。
-->
<template>
  <div class="session-history__row">
    <button
      type="button"
      class="session-history__item"
      :class="{ 'session-history__item--active': active }"
      :title="item.preview || item.title"
      :aria-current="active ? 'true' : undefined"
      @click="emit('select')"
    >
      <span class="session-history__item-title">
        {{ item.title || "未命名会话" }}
      </span>
      <span
        v-if="item.preview && item.preview !== item.title"
        class="session-history__item-preview"
      >
        {{ item.preview }}
      </span>
      <span class="session-history__item-meta">
        {{ timeLabel }} · {{ item.turn_count }} 轮
      </span>
    </button>

    <!-- 删除入口：放在条目右上角、hover / 键盘聚焦时才显现——常显会在每行都挂一个
         危险图标，把「浏览列表」这件事压成「一排删除按钮」。
         不可见时同时 pointer-events:none，避免误点；Tab 聚焦时 :focus-visible
         会把它显出来，键盘用户依然可达。触摸端没有 hover（@media (hover: none)）故常显。 -->
    <button
      type="button"
      class="session-history__del"
      :aria-label="`删除会话：${item.title || '未命名会话'}`"
      :title="busy ? '分析进行中，结束后可删除' : `删除会话：${item.title}`"
      :disabled="busy || deleting"
      @click.stop="emit('delete')"
    >
      <el-icon><Delete /></el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import { Delete } from "@element-plus/icons-vue";
import type { AgentSessionItem } from "@/api/agent";

defineOptions({ name: "SessionHistoryItem" });

defineProps<{
  /** 会话摘要（服务端已按 user_id 过滤，跨用户不可见） */
  item: AgentSessionItem;
  /** 是否是当前正在续聊的那条 */
  active: boolean;
  /** 已格式化的时间文案：组内只留 HH:mm，「更早」组带 MM-DD */
  timeLabel: string;
  /** 有一轮分析在跑：禁用删除（那轮收尾会写回已删行） */
  busy?: boolean;
  /** 本条的删除请求正在飞：禁用重复点击 */
  deleting?: boolean;
}>();

const emit = defineEmits<{
  (e: "select"): void;
  (e: "delete"): void;
}>();
</script>

<style lang="scss" scoped>
.session-history__row {
  position: relative;
}

.session-history__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;

  /* 右侧让出 30px 给删除按钮：不给的话，末行的「HH:mm · n 轮」
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

/* 三行文字的颜色分工（2026-11-26 修）：
   - 标题 = --text-primary（可读的第一层）；
   - 预览（聊到哪儿了）原本是 --text-disabled #c9c2b8，实测 1.64:1 —— 几乎不可读，
     等于第三行白写。升到 --text-tertiary-ink（亮 4.96 / 暗 5.40）；
   - 时间与轮次同为辅助正文字级，同一令牌；层级靠位置与 tabular-nums 区分，
     不再靠「一层比一层淡」——那三档里有两档根本达不到 AA。 */
.session-history__item-preview {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.session-history__item-meta {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
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
</style>
