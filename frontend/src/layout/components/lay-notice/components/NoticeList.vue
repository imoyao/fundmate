<script setup lang="ts">
import { PropType } from "vue";
import { ListItem } from "../data";
import NoticeItem from "./NoticeItem.vue";

defineProps({
  list: {
    type: Array as PropType<Array<ListItem>>,
    default: () => []
  },
  emptyText: {
    type: String,
    default: ""
  }
});

// 点击条目不是「选中」而是「标记已读」，故事件语义命名为 read 而非 select：
// 上层接到后直接打已读接口，不需要额外的意图分支。
const emit = defineEmits<{ read: [item: ListItem] }>();
</script>

<template>
  <div v-if="list.length">
    <!-- key 用后端通知 id：列表会被「未读优先」重排、也会因局部已读而更新，
         用数组下标会让 Vue 就地复用错位的 DOM（标题对着别人的时间戳）。 -->
    <NoticeItem
      v-for="item in list"
      :key="item.id"
      :notice-item="item"
      @read="emit('read', item)"
    />
  </div>
  <el-empty v-else :description="emptyText" />
</template>
