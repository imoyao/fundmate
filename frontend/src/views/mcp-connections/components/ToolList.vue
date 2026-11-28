<!--
  能力清单（S5g）：已采样到的上游工具列表 + Fund Mate 能力标注。

  自 ServiceCard 拆出（#3303）：ServiceCard 要给「即将过期」续期入口腾体量
  余量（400 行门禁），工具清单自成一体也顺带满足 #3303 UI 反馈的「工具墙
  独立成块」。折叠态由本组件自己持有——卡片其余部分不因展开/收起重渲染。
-->
<template>
  <div class="mcp-tool-list">
    <button type="button" class="mcp-tool-list__toggle" @click="open = !open">
      {{ toggleLabel }}
    </button>
    <ul v-if="open" class="mcp-tool-list__items">
      <li
        v-for="tool in tools"
        :key="tool.name"
        class="mcp-tool-list__tool"
        :data-mapped="tool.capabilities.length > 0"
      >
        <div class="mcp-tool-list__line">
          <code class="mcp-tool-list__name">{{ tool.name }}</code>
          <span v-if="tool.capabilities.length" class="mcp-tool-list__cap">
            {{ toolCapLabel(tool.capabilities) }}
          </span>
        </div>
        <p v-if="tool.description" class="mcp-tool-list__desc">
          {{ tool.description }}
        </p>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { McpToolInfo } from "@/api/mcp";
import { toolCapLabel, toolsToggleLabel } from "../mcpServices";

defineOptions({ name: "McpToolList" });

const props = defineProps<{
  tools: McpToolInfo[];
}>();

const open = ref(false);
const toggleLabel = computed(() =>
  toolsToggleLabel(open.value, props.tools.length)
);
</script>

<style scoped>
.mcp-tool-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mcp-tool-list__toggle {
  align-self: flex-start;
  padding: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background: none;
  border: none;
}

.mcp-tool-list__toggle:hover {
  color: var(--el-color-primary);
}

.mcp-tool-list__items {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  margin: 0;
  list-style: none;
  background-color: var(--bg-subtle);
  border-radius: 10px;
}

.mcp-tool-list__tool {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mcp-tool-list__line {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.mcp-tool-list__name {
  font-family: var(--font-mono);
  font-size: var(--text-label);
  color: var(--text-primary);
}

.mcp-tool-list__cap {
  padding: 1px 8px;
  font-size: var(--text-label);
  color: var(--el-color-primary);
  background-color: color-mix(
    in srgb,
    var(--el-color-primary) 10%,
    transparent
  );
  border: 1px solid var(--el-color-primary);
  border-radius: 10px;
}

.mcp-tool-list__desc {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
