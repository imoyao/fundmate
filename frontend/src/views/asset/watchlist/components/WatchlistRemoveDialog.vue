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

/** 持仓资产：彻底删除被产品语义禁止（持仓即自选，删了仍会回来），仅允许从分组移除 */
const holding = computed(() => props.removingItem?.status === "HOLDING");
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
        <!-- 持仓资产禁用「彻底删除」：仅能从分组摘除，见执行端 useWatchlistData 防御闸门 -->
        <el-radio value="all" :disabled="holding"
          >从所有分组移除并删除</el-radio
        >
        <el-radio value="current" :disabled="!currentIsCustom"
          >仅从当前分组移除</el-radio
        >
      </el-radio-group>
      <p v-if="holding && scope !== 'all'" class="remove-scope-hint">
        持仓资产不可从自选彻底删除，只能从分组移除
      </p>
    </div>
    <!-- 「从所有分组移除并删除」的二次确认警示：破坏性后果必须在点「确定」前可见。
         范围单选被隐藏（该自选不属于任何自定义分组）时 scope 恒为 all，同样要提示。 -->
    <p v-if="scope === 'all'" class="remove-scope-warn">
      将从所有分组移除并<b>彻底删除</b>该自选记录（含标签与备注，不可恢复）
    </p>
    <template #footer>
      <el-button size="large" @click="dialogVisible = false">取消</el-button>
      <el-button size="large" type="danger" @click="emit('confirm')"
        >确定</el-button
      >
    </template>
  </el-dialog>
</template>

<style scoped>
/* 「彻底删除」二次确认警示：危险文字级语义色（--color-danger-ink，明暗两端已调对比度），
   禁止硬编码 hex（design.md 设计语言）。 */
.remove-scope-warn {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-danger-ink);
}

/* 持仓禁删的能力边界说明：不是错误态，用中性弱化文字与上方警示区分。 */
.remove-scope-hint {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}
</style>
