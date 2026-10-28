<template>
  <!--
    弱提醒折叠区（从 HoldingOverlapPanel 拆出）。
    「小仓位」不是「不提醒」：默认折叠不占第一屏，但标题常驻条数、可筛选、
    可分页、可逐对看明细——想核对的人随时能看到，不想看的人不会被上千条噪音淹掉。
  -->
  <el-collapse v-model="open" class="overlap-panel__weak">
    <el-collapse-item name="weak">
      <template #title>
        <span class="overlap-panel__weak-head">
          <span class="overlap-panel__weak-title">
            弱提醒 · {{ pairs.length }} 对
          </span>
          <span class="overlap-panel__weak-note">
            金额小或重合度不高，默认折叠
          </span>
        </span>
      </template>

      <p class="overlap-panel__weak-hint">{{ hint }}</p>

      <div class="overlap-panel__weak-tools">
        <el-input
          v-model="keyword"
          class="overlap-panel__weak-search"
          size="small"
          clearable
          placeholder="按基金代码或名称筛选"
          aria-label="筛选弱提醒中的基金"
        />
        <span v-if="keyword" class="overlap-panel__meta">
          筛出 {{ filtered.length }} 对
        </span>
      </div>

      <p v-if="!filtered.length" class="overlap-panel__meta">
        没有匹配「{{ keyword }}」的基金对
      </p>

      <ul v-else class="overlap-panel__list">
        <HoldingOverlapPairItem
          v-for="pair in page.visible"
          :key="pairKey(pair)"
          :pair="pair"
          variant="weak"
        />
      </ul>

      <div v-if="page.hasMore" class="overlap-panel__more">
        <el-button size="small" @click="loadMore">
          再显示 {{ nextBatch }} 对（还有 {{ page.remaining }} 对）
        </el-button>
      </div>
      <p v-else-if="filtered.length" class="overlap-panel__meta">
        已显示全部 {{ filtered.length }} 对
      </p>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import HoldingOverlapPairItem from "./HoldingOverlapPairItem.vue";
import {
  describeWeakHint,
  filterWeakPairs,
  pairKey,
  sliceWeakPairs,
  WEAK_PAGE_SIZE
} from "./holdingOverlapModel";
import type { OverlapPair } from "./holdingOverlapModel";

const props = defineProps<{
  pairs: OverlapPair[];
  /** 分档金额线文案（后端下发，前端不另写一个数） */
  gateText: string;
}>();

/** 空数组 = 收起；用户展开过就记住 */
const open = ref<string[]>([]);
/** 上千对里找一个基金，靠滚动不现实 */
const keyword = ref("");
/** 已加载条数：分页而非一次渲染上千条（DOM 会卡） */
const loaded = ref(WEAK_PAGE_SIZE);

const hint = computed(() => describeWeakHint(props.gateText));
const filtered = computed(() => filterWeakPairs(props.pairs, keyword.value));
const page = computed(() => sliceWeakPairs(filtered.value, loaded.value));
const nextBatch = computed(() =>
  Math.min(WEAK_PAGE_SIZE, page.value.remaining)
);

const loadMore = () => {
  loaded.value += WEAK_PAGE_SIZE;
};

/** 换了关键词就回到第一页，否则「筛出 3 对」却还挂着上次翻到的 150 条 */
watch(keyword, () => {
  loaded.value = WEAK_PAGE_SIZE;
});

/** 换一批数据就把展开/筛选/分页清回初始：旧状态套在新列表上是错的 */
watch(
  () => props.pairs,
  () => {
    open.value = [];
    keyword.value = "";
    loaded.value = WEAK_PAGE_SIZE;
  }
);
</script>

<style scoped lang="scss">
.overlap-panel {
  &__list {
    display: flex;
    flex-direction: column;
    gap: var(--space-standard);
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__meta {
    margin: 4px 0 0;
    font-size: var(--text-small);
    color: var(--text-tertiary-ink);
  }

  &__weak {
    margin-top: var(--space-standard);
    border-top: 1px solid var(--divider-default);
    border-bottom: none;

    :deep(.el-collapse-item__header) {
      height: auto;
      padding: 10px 0;
      line-height: 1.5;
      background: transparent;
      border-bottom: none;
    }

    :deep(.el-collapse-item__wrap) {
      background: transparent;
      border-bottom: none;
    }

    :deep(.el-collapse-item__content) {
      padding-bottom: 4px;
    }
  }

  &__weak-head {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: baseline;
  }

  &__weak-title {
    font-size: var(--text-body);
    color: var(--text-secondary);
  }

  &__weak-note {
    font-size: var(--text-small);
    color: var(--text-tertiary-ink);
  }

  &__weak-hint {
    margin: 0 0 8px;
    font-size: var(--text-small);
    line-height: 1.6;
    color: var(--text-secondary);
  }

  &__weak-tools {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: var(--space-standard);
  }

  &__weak-search {
    max-width: 260px;
  }

  &__more {
    margin-top: var(--space-standard);
    text-align: center;
  }
}
</style>
