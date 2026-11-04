<!--
  SectionHeader · 区块统一标题行（设计系统强制复用，详见 frontend/design.md）
  - 标题 + 可选信息图标（hover/焦点显示 tooltip）+ 右侧操作槽（具名插槽 #action）
  - 禁止各页面再手写 <h2>/<h3> + 分散的图标/操作按钮，统一收口到本组件
  props:
    - title:     区块标题。**传空串表示「宿主已经自带标题」**：此时不渲染 `<h2>`
                 （连同空的 title-group 一起跳过），只留 `#action`。用于本组件被嵌进
                 一个自己画了标题的卡片时——否则会出现两个一模一样的标题
                 （#2035：收益日历在资产总览右卡正是这样撞的车）。
                 不传 `title` 也不显示标题，但**通常不该这么用**：区块标题行缺一个
                 语义化 heading 对读屏是信息损失。
    - info:      信息图标 tooltip 文案（可选；不传则不显示图标）。
                 **按长度自动选载体**（2026-11-02）：≤48 字走深色短语气泡；
                 更长的（约两行以上）自动升格成浅色说明卡，并按句分行。
                 判据与阈值见 utils/tooltipText.ts——调用方只管写清文案，不必判断「这算长算短」。
    - infoLabel: 信息图标的可访问名（可选，默认取 `info`）。
                 **富内容（`#info` 插槽）必须传**：插槽内容读屏读不到「这是什么」，
                 靠它给图标一个说得清的名字。
    - badge:     标题右侧的徽标插槽（可选，#2303 新增）。用于「Pro」这类档位胶囊——
                 跟着标题走（放 title-group 内），不占右侧操作槽；
                 徽章样式由调用方按 design.md Badge 规范自带。
    - icon:      信息图标名（可选，默认 ep:info-filled）
  slots:
    - info:  信息图标的**富内容**（可选）。给了就用插槽、忽略 `info` 字符串，
             并自动挂 `rich-tip` 气泡样式（宽度与排版见 style/el-tooltip.css）。
             用途：口径 + 图例这类「多行结构化」说明——一行字符串塞进去只会变成一堵墙
             （#1942 第三轮反馈：收益日历的口径说明正是这样被吐槽的）。
             ⚠️ 只是「一段话」而非结构化内容时，直接用 `info` 字符串即可：
             长文案现在会自动升格成说明卡并按句分行，不必为此写插槽。
    - action: 右侧操作槽。**窄容器下本槽会收缩**（#2039），因此槽内若有多枚控件，
              请自行套一个 `flex-wrap: wrap` 的容器：收缩时靠它折行，而不是溢出卡片
              （参考 PnlCalendar 的 `#action`——它那排控件宽 588px，是最典型的场景）。
-->
<template>
  <div class="section-header">
    <div
      v-if="title || info || $slots.info"
      class="section-header__title-group"
    >
      <h2 v-if="title" class="section-header__title">{{ title }}</h2>
      <el-tooltip
        v-if="hasInfo"
        :content="useRichTip ? undefined : info"
        placement="top"
        :popper-class="tipClass"
      >
        <span
          class="section-header__info"
          tabindex="0"
          role="img"
          :aria-label="infoLabel || info || title"
        >
          <IconifyIconOffline :icon="icon" />
        </span>
        <template v-if="useRichTip" #content>
          <slot v-if="$slots.info" name="info" />
          <template v-else>
            <p v-for="(paragraph, i) in paragraphs" :key="i">
              {{ paragraph }}
            </p>
          </template>
        </template>
      </el-tooltip>
      <slot name="badge" />
    </div>
    <div v-if="$slots.action" class="section-header__action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, useSlots } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import {
  isRichTipText,
  RICH_TIP_CLASS,
  tipParagraphs,
  tipPopperClass
} from "@/utils/tooltipText";

const props = withDefaults(
  defineProps<{
    title?: string;
    info?: string;
    infoLabel?: string;
    icon?: string;
  }>(),
  {
    title: "",
    info: "",
    infoLabel: "",
    icon: "ep:info-filled"
  }
);

const slots = useSlots();

const hasInfo = computed(() => Boolean(props.info) || Boolean(slots.info));

/* 载体按**文案长度**选，不按调用方自觉选（判据与阈值见 utils/tooltipText.ts）：
   短语 → 深色气泡（限宽由 --tooltip-max-width 兜住）；超过两行 → 浅色说明卡。
   这样 43 处 `info` 一处不用改，长的自动升格，短的不动。 */
const useRichTip = computed(
  () => Boolean(slots.info) || isRichTipText(props.info)
);

/** 说明卡里一句一行；短文案返回空数组（不会渲染） */
const paragraphs = computed(() => tipParagraphs(props.info));

/* 插槽内容自带结构（标题 + 列表），沿用既有 rich-tip 卡片；字符串升格的多挂段落修饰，
   只为给 `<p>` 段间距（见 style/el-tooltip.css），不改变卡片本体样式 */
const tipClass = computed(() =>
  slots.info ? RICH_TIP_CLASS : tipPopperClass(props.info)
);
</script>

<style lang="scss" scoped>
/* 单一来源：frontend/design.md · 区块标题统一规范 */
.section-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 32px; /* 与历史实现 h-8 对齐，保证右侧操作槽垂直居中 */
  margin-bottom: var(--space-3);

  &__title-group {
    display: flex;
    gap: 6px;
    align-items: center;
    min-width: 0;
  }

  &__title {
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-body);
    font-weight: 600;
    line-height: 1.4;
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__info {
    display: inline-flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    font-size: var(--text-body);
    color: var(--text-tertiary-ink);
    cursor: help;
    transition: color 0.15s ease;

    &:hover,
    &:focus-visible {
      color: var(--brand-700);
      outline: none;
    }
  }

  &__action {
    display: inline-flex;

    /* #2039：操作槽必须可收缩。原先 `flex-shrink: 0` 让它恒为 max-content
       （收益日历那排控件实测 588px），窄窗口下负空间只能全压给 `min-width: 0`
       的 title-group——压到 0 之后，整排控件就溢出卡片、叠到左侧的 ⓘ 上。
       `min-width: 0` 是 flex 项能压到自身 min-content 以下的前提；
       调用方 `#action` 内层是 `flex-wrap: wrap` 容器时，随收缩自动折行。
       宽容器的负空间为 0，两条声明都不生效 ⇒ 宽屏排版逐像素不变。 */
    flex-shrink: 1;
    gap: 8px;
    align-items: center;
    min-width: 0;
  }
}
</style>
