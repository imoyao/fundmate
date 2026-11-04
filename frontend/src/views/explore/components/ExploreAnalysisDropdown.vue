<!--
  ExploreAnalysisDropdown · 「分析 ▼」外链下拉
  从 ExploreWatchlistTable 抽出（#980 批 B5）：桌面表格与移动卡片两处都挂它，
  原先两处各写一遍同样的 dropdown 骨架，站点清单还各算一次。

  ⚠️ 站点清单必须走 `watchlistTools.getAvailableTools`：基金 / ETF 多一个天天基金，
  这条规则写在两处就会漂。
-->
<template>
  <el-dropdown @command="(command: string) => emit('command', command)">
    <el-button size="small" type="primary" plain>分析 ▼</el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="tool in tools"
          :key="tool.key"
          :command="tool.key"
        >
          {{ tool.label }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { getAvailableTools } from "./watchlistTools";

defineOptions({ name: "ExploreAnalysisDropdown" });

const props = defineProps<{
  /** 资产类型（stock / fund / etf / bond / index…），决定站点清单 */
  type: string;
}>();

const emit = defineEmits<{ command: [key: string] }>();

const tools = computed(() => getAvailableTools(props.type));
</script>
