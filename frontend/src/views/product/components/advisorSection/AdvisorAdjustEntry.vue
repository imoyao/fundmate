<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { AdvisorAdjustGroup, AdvisorAdjustItem } from "@/api/funds";
import { advisorOpTone, advisorRatioText } from "@/utils/advisorAdjust";
import { countByTone, sourceLabelOf } from "./advisorAdjustModel";

/**
 * 投顾组合 · 主理人调仓的**单次调仓**（时间轴上的一节）。
 *
 * ## 为什么把「理由截断」的判断下放到这里
 *
 * 理由按钮的显隐必须实测：理由文本宽度随视口变化，宽屏 130 字正好排两行、根本没被
 * 裁掉，此时若固定显示「调仓理由」，点下去什么都不会发生——用户会以为功能坏了。
 * 那段测量原先写在宿主里，要靠 `:ref` 回调把每个 DOM 节点收进一张 Map、再按日期
 * 集合追状态（三份状态：`openReasons` / `clampedDates` / `reasonEls`）。
 * 「这一节自己的理由有没有被裁掉」本来就是这一节的私有事实，下放后宿主不再需要
 * 任何逐条状态，子件自己量、自己判、自己收放。
 *
 * ## 口径
 *
 * - 只渲染，不判定「该不该跟着动」：合规红线；
 * - 日期轴点：最近一次实心、其余空心（「哪里是现在」不需要额外标签）。
 */
const props = defineProps<{
  group: AdvisorAdjustGroup;
  /** 是否最近一次调仓（实心轴点） */
  latest: boolean;
}>();

const reasonOpen = ref(false);
/** 理由**实际被截断**才给按钮（实测得来，不猜） */
const clamped = ref(false);
const reasonEl = ref<HTMLElement>();

/**
 * 量一次「这段理由有没有被裁掉」。
 *
 * 已展开的项保持「可收起」——它曾经被裁掉过，若按当前（已展开）高度重算会被判为
 * 没溢出，按钮随即消失、再也收不回去。
 */
function measure(): void {
  const el = reasonEl.value;
  if (!el) {
    clamped.value = false;
    return;
  }
  clamped.value = reasonOpen.value || el.scrollHeight > el.clientHeight + 1;
}

async function syncMeasure(): Promise<void> {
  await nextTick();
  measure();
}

const tones = () => countByTone(props.group);

function opClass(item: AdvisorAdjustItem): string {
  return `chg__op--${advisorOpTone(item.op_name)}`;
}

function nameOf(item: AdvisorAdjustItem): string {
  return item.fund_name || item.fund_code;
}

watch(() => props.group, syncMeasure);
watch(reasonOpen, () => void syncMeasure());
onMounted(() => {
  void syncMeasure();
  window.addEventListener("resize", measure);
});
onBeforeUnmount(() => window.removeEventListener("resize", measure));
</script>

<template>
  <article class="tl__item" :data-latest="latest">
    <p class="tl__date">
      {{ group.adjust_date }}
      <small>{{ group.items.length }} 笔</small>
    </p>
    <div class="tl__body">
      <div class="tl__sum">
        <span class="chip chip--in">
          加仓 <b>{{ tones().add }}</b>
        </span>
        <span class="chip chip--out">
          减仓 <b>{{ tones().cut }}</b>
        </span>
        <span class="tl__source">{{ sourceLabelOf(group.source) }}</span>
      </div>

      <div class="chg">
        <div
          v-for="item in group.items"
          :key="`${group.adjust_date}-${item.fund_code}`"
          class="chg__row"
        >
          <span class="chg__name">
            <span class="chg__op" :class="opClass(item)">
              {{ item.op_name || "调整" }}
            </span>
            <span :title="nameOf(item)">{{ nameOf(item) }}</span>
          </span>
          <span v-if="advisorRatioText(item)" class="chg__ratio">
            {{ advisorRatioText(item) }}
          </span>
        </div>
      </div>

      <template v-if="group.reason">
        <p ref="reasonEl" class="reason" :class="{ 'is-clamp': !reasonOpen }">
          {{ group.reason }}
        </p>
        <button
          v-if="clamped"
          type="button"
          class="link-more"
          :aria-expanded="reasonOpen"
          @click="reasonOpen = !reasonOpen"
        >
          {{ reasonOpen ? "收起理由" : "调仓理由" }}
          <span class="link-more__chev" aria-hidden="true">›</span>
        </button>
      </template>
    </div>
  </article>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;
@use "./link-more";

.tl__item {
  position: relative;
  padding-bottom: var(--space-5);

  @include bp.below("md") {
    padding-top: var(--space-2);

    &::before {
      display: none;
    }
  }

  &:last-child {
    padding-bottom: 0;
  }

  &::before {
    position: absolute;
    top: 7px;
    left: -24px;
    width: 9px;
    height: 9px;
    content: "";
    background: var(--bg-card);
    border: 2px solid var(--border-default);
    border-radius: 50%;
  }

  /* 最近一次用实心点：时间轴上「哪里是现在」不需要额外标签 */
  &[data-latest="true"]::before {
    background: var(--color-primary);
    border-color: var(--color-primary);
  }
}

.tl__date {
  position: absolute;
  top: 5px;
  left: -104px;
  width: 76px;
  margin: 0;
  font-family: var(--font-number);
  font-size: var(--text-label);
  color: var(--text-secondary);
  text-align: right;
}

.tl__date small {
  display: block;
  color: var(--text-tertiary-ink);
}

/* 窄屏：日期从轴左竖排改为正文第一行，时间轴退化成普通列表 */
@include bp.below("md") {
  .tl__date {
    position: static;
    width: auto;
    margin-bottom: var(--space-1);
    text-align: left;
  }
}

.tl__body {
  min-width: 0;
}

.tl__sum {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: var(--space-2);
}

.chip {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
  padding: 0 7px;
  font-size: var(--text-label);
  line-height: 18px;
  border-radius: var(--radius-pill);
}

.chip--in {
  color: var(--color-rise-ink);
  background: color-mix(in srgb, var(--color-rise) 13%, transparent);
}

.chip--out {
  color: var(--color-fall-ink);
  background: color-mix(in srgb, var(--color-fall) 14%, transparent);
}

.chip b {
  font-family: var(--font-number);
  font-weight: 600;
}

.tl__source {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 明细两栏：窄屏自动退成一栏（不做横向滚动——调仓行是阅读材料，不是表格） */
.chg {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 var(--space-5);

  @include bp.below("md") {
    grid-template-columns: minmax(0, 1fr);
  }
}

.chg__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-3);
  align-items: center;
  padding: 5px 0;
  font-size: var(--text-label);
  border-bottom: 1px dashed var(--border-light);
}

.chg__name {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  min-width: 0;

  > span:last-child {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.chg__op {
  flex: 0 0 auto;
  font-weight: 600;

  &--add {
    color: var(--color-rise-ink);
  }

  &--cut {
    color: var(--color-fall-ink);
  }

  &--neutral {
    color: var(--text-tertiary-ink);
  }
}

.chg__ratio {
  font-family: var(--font-number);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.reason {
  margin: var(--space-3) 0 0;
  font-size: var(--text-label);
  line-height: 1.75;
  color: var(--text-tertiary-ink);

  &.is-clamp {
    display: -webkit-box;
    overflow: hidden;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
  }
}
</style>
