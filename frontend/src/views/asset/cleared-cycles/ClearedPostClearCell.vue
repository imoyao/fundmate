<!--
  ClearedPostClearCell · 「清仓后」单元格（#2773）

  为什么单独成文件：状态码 → 文案/颜色的映射已经在 `helpers.postClearCell` 里定死，
  这里只负责渲染。模板里若直接写 `postClearCell(row)` 三次（判空 / 取值 / title），
  同一行会算三遍；拆成组件后 `computed` 只算一次，也让明细表少一层嵌套。

  `title` 是**必需**的，不是装饰：算不出有四种原因（早期清仓无净值 / 净值停更 /
  场内不支持 / 本次未请求），对用户的含义完全不同，都画成一个 `--` 而不解释，
  用户只能猜是数据坏了还是自己操作错了。
-->
<template>
  <span :title="cell.title">
    <RiseFallText v-if="cell.pct !== null" :value="cell.pct" size="sm" />
    <span v-else class="post-clear-na">{{ cell.placeholder }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import type { ClearedCycle } from "@/api/summary";
import { postClearCell } from "./helpers";

defineOptions({ name: "ClearedPostClearCell" });

const props = defineProps<{
  /** 一个已清仓周期（`post_clear_*` 字段由接口按 include_post_clear 下发） */
  cycle: ClearedCycle;
}>();

const cell = computed(() => postClearCell(props.cycle));
</script>

<style scoped>
.post-clear-na {
  color: var(--text-tertiary-ink);
}
</style>
