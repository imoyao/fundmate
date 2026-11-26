<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getAdvisorAdjusts, type AdvisorAdjustGroup } from "@/api/funds";
import {
  ADJUST_LIMIT,
  adjustEmptyHint,
  derivedFromSnapshots
} from "./advisorAdjustModel";
import AdvisorAdjustEntry from "./AdvisorAdjustEntry.vue";

/**
 * 投顾组合 · 主理人调仓（重设计 §04，平铺改时间轴）。
 *
 * ## 为什么改成时间轴
 *
 * 旧版把每次调仓的「日期 / 理由 / 逐只明细」平铺成三段，二十次调仓把页面拉到
 * 七千像素，而用户真正要看的是「最近几次动过什么、为什么」。现在按调仓日聚成
 * 时间轴：日期轴点 + 加/减仓计数 + 两栏「前 → 后」明细，理由默认两行截断，
 * 更早的记录折叠在「查看更早」后面。
 *
 * ## 本文件只管「批次」，单节交子件
 *
 * 取数、折叠批次（`TL_INITIAL`）、空态解释、底部口径声明在这里；
 * 每一节的日期轴点 / 加减轻仓 / 明细 / 「调仓理由」按钮在 `AdvisorAdjustEntry`。
 * 拆开的直接收益是**逐条状态消失**：原先宿主为了「谁的理由被裁掉了」要维护
 * 三份按日期索引的状态（`openReasons` / `clampedDates` / `reasonEls`），
 * 而那是每一节自己的私有事实。
 *
 * ## 口径
 *
 * - 只渲染，不判定「该不该跟着动」：合规红线（与对比区块一致）；
 * - 只要有任一组来自快照推导，就必须挂声明——不写就等于冒充官方数据
 *   （判据见 `advisorAdjustModel.derivedFromSnapshots`）。
 */
const props = defineProps<{
  /** 平台组合码 */
  code: string;
  /** 平台码，仅用于空态解释「为什么没有调仓记录」 */
  platform: string;
}>();

/** 首屏展示的调仓组数；其余折叠（10 组上限下通常只剩 6 组，长度刚好） */
const TL_INITIAL = 4;

const loading = ref(false);
const failed = ref(false);
const groups = ref<AdvisorAdjustGroup[]>([]);
const showAll = ref(false);

const visible = computed(() =>
  showAll.value ? groups.value : groups.value.slice(0, TL_INITIAL)
);

const derived = computed(() => derivedFromSnapshots(groups.value));
const emptyHint = computed(() => adjustEmptyHint(props.platform));

const summary = computed(() => {
  if (!groups.value.length) return "";
  return `${groups.value.length} 次 · 最近 ${groups.value[0].adjust_date}`;
});

async function load(): Promise<void> {
  if (!props.code) return;
  loading.value = true;
  failed.value = false;
  groups.value = [];
  showAll.value = false;
  try {
    const res = await getAdvisorAdjusts(props.code, ADJUST_LIMIT);
    // 后端已按调仓日倒序；前端**不重排**（两处各排一次必然不一致）
    groups.value = res.data?.adjusts ?? [];
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.code, load, { immediate: true });
</script>

<template>
  <CardBlock class="advisor-timeline">
    <SectionHeader title="主理人调仓">
      <template #action>
        <span v-if="summary" class="advisor-timeline__summary">{{
          summary
        }}</span>
      </template>
    </SectionHeader>

    <p v-if="loading" class="advisor-timeline__hint">正在读取主理人调仓…</p>
    <p v-else-if="failed" class="advisor-timeline__hint">
      主理人调仓暂时取不到，稍后再看。
    </p>
    <p v-else-if="!groups.length" class="advisor-timeline__hint">
      {{ emptyHint }}
    </p>

    <template v-else>
      <div class="tl">
        <AdvisorAdjustEntry
          v-for="(group, index) in visible"
          :key="group.adjust_date"
          :group="group"
          :latest="index === 0"
        />
      </div>

      <button
        v-if="groups.length > TL_INITIAL"
        type="button"
        class="link-more link-more--all"
        :aria-expanded="showAll"
        @click="showAll = !showAll"
      >
        {{
          showAll
            ? "收起更早的调仓"
            : `查看更早的调仓（${groups.length - TL_INITIAL} 次）`
        }}
        <span class="link-more__chev" aria-hidden="true">›</span>
      </button>

      <p v-if="derived" class="advisor-timeline__caveat">
        标记为「快照推导」的记录由持仓快照序列算出（该组合不在平台官方调仓接口的覆盖范围内），
        时点与幅度可能与实际调仓存在差异。
      </p>
    </template>
  </CardBlock>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;
@use "./link-more";

.advisor-timeline__summary {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.advisor-timeline__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.advisor-timeline__caveat {
  padding-top: var(--space-3);
  margin: var(--space-3) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
  border-top: 1px solid var(--border-light);
}

/* 时间轴：左侧 104px 留给日期，轴线画在 84px 处（与原型同一套几何）。
   轴点是每一节自己的（子件里的 `.tl__item::before`），轴线是整条轴的（这里）。 */
.tl {
  position: relative;
  padding-left: 104px;

  @include bp.below("md") {
    padding-left: 0;

    &::before {
      display: none;
    }
  }

  &::before {
    position: absolute;
    top: 6px;
    bottom: 10px;
    left: 84px;
    width: 1px;
    content: "";
    background: var(--border-default);
  }
}

.link-more--all {
  margin-top: var(--space-4);
  margin-left: 104px;

  @include bp.below("md") {
    margin-left: 0;
  }
}
</style>
