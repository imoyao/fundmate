<script setup lang="ts">
import { ListItem } from "../data";
import { ref, PropType, nextTick } from "vue";
import { useNav } from "@/layout/hooks/useNav";
import { deviceDetection } from "@pureadmin/utils";

defineProps({
  noticeItem: {
    type: Object as PropType<ListItem>,
    default: () => {}
  }
});

const titleRef = ref(null);
const titleTooltip = ref(false);
const descriptionRef = ref(null);
const descriptionTooltip = ref(false);
const { tooltipEffect } = useNav();
const isMobile = deviceDetection();

// 点击即「标记已读」，由上层发起 PATCH：本组件只报意图，不好自行发请求——
// 那样同一个弹层里会有多个组件各写一份乐观更新与回滚，状态无从收敛。
const emit = defineEmits<{ read: [] }>();

function hoverTitle() {
  nextTick(() => {
    titleRef.value?.scrollWidth > titleRef.value?.clientWidth
      ? (titleTooltip.value = true)
      : (titleTooltip.value = false);
  });
}

function hoverDescription(event, description) {
  // currentWidth 为文本在页面中所占的宽度，创建标签，加入到页面，获取currentWidth ,最后在移除
  const tempTag = document.createElement("span");
  tempTag.innerText = description;
  tempTag.className = "getDescriptionWidth";
  document.querySelector("body").appendChild(tempTag);
  const currentWidth = (
    document.querySelector(".getDescriptionWidth") as HTMLSpanElement
  ).offsetWidth;
  document.querySelector(".getDescriptionWidth").remove();

  // cellWidth为容器的宽度
  const cellWidth = event.target.offsetWidth;

  // 当文本宽度大于容器宽度两倍时，代表文本显示超过两行
  currentWidth > 2 * cellWidth
    ? (descriptionTooltip.value = true)
    : (descriptionTooltip.value = false);
}
</script>

<template>
  <div
    class="notice-container"
    role="button"
    tabindex="0"
    @click="emit('read')"
    @keydown.enter.prevent="emit('read')"
    @keydown.space.prevent="emit('read')"
  >
    <div class="notice-container__text">
      <div class="notice-container__title">
        <span
          v-if="!noticeItem.isRead"
          class="notice-container__dot"
          aria-label="未读"
        />
        <el-tooltip
          popper-class="notice-title-popper"
          :effect="tooltipEffect"
          :disabled="!titleTooltip"
          :content="noticeItem.title"
          placement="top-start"
          :enterable="!isMobile"
        >
          <div
            ref="titleRef"
            class="notice-container__title-content"
            :class="{ 'is-read': noticeItem.isRead }"
            @mouseover="hoverTitle"
          >
            {{ noticeItem.title }}
          </div>
        </el-tooltip>
        <el-tag
          v-if="noticeItem?.extra"
          :type="noticeItem?.status"
          size="small"
          class="notice-container__extra"
        >
          {{ noticeItem?.extra }}
        </el-tag>
      </div>

      <el-tooltip
        popper-class="notice-title-popper"
        :effect="tooltipEffect"
        :disabled="!descriptionTooltip"
        :content="noticeItem.description"
        placement="top-start"
      >
        <div
          ref="descriptionRef"
          class="notice-container__description"
          @mouseover="hoverDescription($event, noticeItem.description)"
        >
          {{ noticeItem.description }}
        </div>
      </el-tooltip>
      <div class="notice-container__datetime">
        {{ noticeItem.datetime }}
      </div>
    </div>
  </div>
</template>

<style>
.notice-title-popper {
  max-width: 238px;
}
</style>
<style lang="scss" scoped>
.notice-container {
  display: flex;
  align-items: flex-start;
  padding: var(--space-3) 0;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);

  &__text {
    display: flex;
    flex: 1;
    flex-direction: column;
    justify-content: space-between;
  }

  &__title {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    margin-bottom: var(--space-2);
    font-size: var(--text-small);
    font-weight: 400;
    line-height: 1.5715;
  }

  /* 未读圆点：红点是唯一一处用品牌色的地方，刻意不与涨跌红绿混用——
     涨跌色有明确的数据语义，消息层级没有。 */
  &__dot {
    flex: none;
    width: 6px;
    height: 6px;
    background: var(--brand-700);
    border-radius: var(--radius-pill);
  }

  &__title-content {
    flex: 1;
    width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-primary);
    white-space: nowrap;
  }

  /* 已读条目整体降一档，让未读在有限高度里先被看见 */
  &__title-content.is-read {
    color: var(--text-secondary);
  }

  &__extra {
    flex: none;
    font-weight: 400;
  }

  &__description,
  &__datetime {
    font-size: var(--text-label);
    line-height: 1.5715;
  }

  &__description {
    display: -webkit-box;
    overflow: hidden;
    text-overflow: ellipsis;
    -webkit-line-clamp: 2;
    color: var(--text-secondary);
    -webkit-box-orient: vertical;
  }

  &__datetime {
    margin-top: var(--space-1);
    color: var(--text-tertiary-ink);
  }
}
</style>
