<template>
  <div class="position-header mb-5 flex items-center justify-between">
    <div>
      <h3 class="text-xl font-bold" :style="{ color: 'var(--text-primary)' }">
        {{ positionData?.name || "--" }}
      </h3>
      <div class="flex items-center gap-2 mt-1">
        <span class="text-sm" :style="{ color: 'var(--text-tertiary-ink)' }"
          ># {{ positionData?.symbol || "--" }}</span
        >
        <el-tag size="small" type="info" round>{{
          positionData?.type_label || "--"
        }}</el-tag>
      </div>
    </div>
    <!-- #1965：新增跳详情入口（持仓抽屉原先只能看流水，没有出口） -->
    <el-button
      text
      size="small"
      :loading="detailLoading"
      @click="emit('detail')"
    >
      查看详情
    </el-button>
  </div>
</template>

<script setup lang="ts">
import type { PositionLike } from "./positionSummaryModel";

/**
 * 持仓抽屉头部（#980 拆分自 `PositionTransactionsDrawer.vue`）。
 *
 * 名称 / 代码 / 品类标签 + 「查看详情」出口。跳转本身留在父组件——
 * 它要动路由并关抽屉，属于页面级副作用。
 */
defineOptions({ name: "PositionDrawerHeader" });

withDefaults(
  defineProps<{
    positionData?: PositionLike | null;
    /** 「查看详情」按钮的 loading（跳转前要先 resolve 品类） */
    detailLoading?: boolean;
  }>(),
  { positionData: null, detailLoading: false }
);

const emit = defineEmits<{ detail: [] }>();
</script>
