<script setup lang="ts">
import { computed } from "vue";
import type { WatchlistItem } from "@/api/watchlist";

defineOptions({ name: "WatchlistRemoveDialog" });

const props = defineProps<{
  modelValue: boolean;
  removingItem: WatchlistItem | null;
  removeScope: "current" | "all";
  currentIsCustom: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "update:removeScope", value: "current" | "all"): void;
  (e: "confirm"): void;
}>();

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value)
});

const scope = computed({
  get: () => props.removeScope,
  set: (value: "current" | "all") => emit("update:removeScope", value)
});

const itemName = computed(
  () => props.removingItem?.display_name || props.removingItem?.symbol || ""
);
</script>

<template>
  <el-dialog v-model="dialogVisible" title="移除自选" width="400px">
    <p>
      确定要移除
      <strong>{{ itemName }}</strong>
      吗？
    </p>
    <div
      v-if="
        removingItem &&
        removingItem.group_ids &&
        removingItem.group_ids.length > 0
      "
      class="mt-4"
    >
      <el-radio-group v-model="scope">
        <el-radio value="all">从所有分组移除并删除</el-radio>
        <el-radio value="current" :disabled="!currentIsCustom"
          >仅从当前分组移除</el-radio
        >
      </el-radio-group>
    </div>
    <template #footer>
      <el-button size="large" @click="dialogVisible = false">取消</el-button>
      <el-button size="large" type="danger" @click="emit('confirm')"
        >确定</el-button
      >
    </template>
  </el-dialog>
</template>
