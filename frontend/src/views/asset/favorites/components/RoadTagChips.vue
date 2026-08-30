<!--
  RoadTagChips · 胶囊标签组（浏览态只读 / 编辑态可删）

  标签色是用户数据色（design.md「Data Visualization」认可的数据色例外），
  缺色时由调用方回退中性 token，本组件只负责呈现。
-->
<template>
  <div v-if="tags.length" class="road-tags">
    <span
      v-for="tag in tags"
      :key="tag.id"
      class="road-tag"
      :class="{ 'road-tag--removable': removable }"
      :style="{ borderColor: tag.color, color: tag.color }"
    >
      {{ tag.name }}
      <IconifyIconOffline
        v-if="removable"
        icon="ep:close"
        class="road-tag__close"
        :aria-label="`移除标签 ${tag.name}`"
        @click="$emit('remove', tag.id)"
      />
    </span>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
import type { WatchlistTag } from "@/api/watchlist";

defineProps<{
  tags: WatchlistTag[];
  /** 编辑态为 true：显示移除叉号 */
  removable?: boolean;
}>();

defineEmits<{ (e: "remove", tagId: number): void }>();
</script>

<style scoped>
.road-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.road-tag {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 1px 9px;
  font-size: 11px;
  line-height: 18px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}

.road-tag--removable {
  cursor: pointer;
}

.road-tag__close {
  font-size: 10px;
  cursor: pointer;
  opacity: 0.7;
}
</style>
