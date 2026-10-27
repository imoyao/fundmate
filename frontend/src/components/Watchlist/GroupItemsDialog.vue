<!--
  GroupItemsDialog · 自定义分组「组内产品增删」抽屉（issue #987 / #1449）

  与 GroupManagerDialog 的分工：
  - GroupManagerDialog 管理「分组本身」（新建 / 改名 / 改色 / 删除）；
  - 本抽屉管理「某个自定义分组里有哪些产品」，二者语义不同，不合并。

  交互演进（#1449）：原上下两区弹窗改为右侧抽屉双栏——左「本组产品」、
  右「全部自选」picker，空间大、可搜索、不挡表格，适合产品较多的场景。

  Bug 2 根因修复（#1449）：「本组产品」不再依赖 _enrich_item 填的 group_ids，
  而是直接调 getWatchlistItems({group_id})——与主列表同源（后端 SQL JOIN
  group_links），杜绝「主列表有、弹窗空」的数据源不一致。「全部自选」池翻页
  以「本页行数 < per_page」为终止条件，不依赖 res.total，避免 total 缺失时
  只拉第一页导致候选不全。

  #980 拆分：数据层 → `useGroupItems.ts`，单栏列表与样式 → `GroupItemColumn.vue`。
  本文件只保留抽屉外壳与双栏栅格。

  props：modelValue(显隐)、group(目标自定义分组，null 时不展示内容)。
  emits：update:modelValue、changed(增删成功后触发，父组件刷新分组与列表)。
-->
<template>
  <el-drawer
    :model-value="modelValue"
    :title="title"
    direction="rtl"
    size="760px"
    class="group-items-drawer"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div v-loading="loading" class="group-items">
      <el-input
        v-model="keyword"
        aria-label="搜索代码或名称"
        placeholder="搜索代码或名称（同时过滤左右两栏）..."
        clearable
        class="gi-search"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <div class="gi-cols">
        <!-- 左栏：本组产品（与列表同源：后端按 group_id SQL JOIN 取数） -->
        <GroupItemColumn
          title="本组产品"
          :count-label="`${inGroup.length} 项`"
          :empty-text="
            keyword
              ? '本组无匹配的产品'
              : '本组暂无产品，可从右侧「全部自选」中添加'
          "
          :items="inGroup"
          variant="member"
          @remove="removeItem"
        />

        <!-- 右栏：全部自选 picker（搜索 + 勾选/点击即加入本组） -->
        <GroupItemColumn
          title="全部自选"
          :count-label="`${candidates.length} 项可添加`"
          :empty-text="
            keyword ? '未找到匹配的自选产品' : '全部自选均已在本组中'
          "
          :items="candidates"
          variant="candidate"
          @add="addItem"
        />
      </div>
    </div>

    <template #footer>
      <el-button type="primary" @click="close">完成</el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, watch } from "vue";
import { Search } from "@element-plus/icons-vue";
import type { WatchlistGroup } from "@/api/watchlist";
import GroupItemColumn from "@/components/Watchlist/GroupItemColumn.vue";
import { useGroupItems } from "@/components/Watchlist/useGroupItems";

const props = defineProps<{
  modelValue: boolean;
  group: WatchlistGroup | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "changed"): void;
}>();

const title = computed(() =>
  props.group ? `管理分组 · ${props.group.name}` : "管理分组"
);

const { loading, keyword, inGroup, candidates, reload, addItem, removeItem } =
  useGroupItems(
    () => props.group,
    () => emit("changed")
  );

// 每次打开重新拉取（分组名单可能在本抽屉外被改动），并清空搜索词
watch([() => props.modelValue, () => props.group?.id], ([visible]) => {
  if (visible) reload();
});

function handleVisibleChange(value: boolean): void {
  emit("update:modelValue", value);
}

function close(): void {
  emit("update:modelValue", false);
}
</script>

<style scoped>
.group-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
}

.gi-search {
  flex-shrink: 0;
}

/* 双栏：左右等宽，间距统一用 --space-compact（design.md 间距令牌，禁硬编码） */
.gi-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-compact);
  min-height: 0;
}
</style>
