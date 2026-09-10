<!--
  NotesEditorDialog · 自选行内备注编辑弹窗（#1285）
  - 为单个自选资产编辑备注（watchlist.notes），与 Favorite（未竟之蹊）复盘页
    共享同一字段，写回同一张表。
  - props：modelValue(显隐)、item(当前自选资产)。
  - emits：update:modelValue、saved(保存成功后触发，父组件负责刷新列表)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑备注"
    width="480px"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div class="mb-3">
      <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">
        为
        <strong>{{ item?.display_name || item?.symbol }}</strong>
        编辑备注
      </span>
    </div>
    <el-input
      v-model="localNotes"
      type="textarea"
      :rows="6"
      maxlength="2000"
      show-word-limit
      resize="none"
      placeholder="写下你为什么在意它，以及下一次想验证什么。"
    />

    <template #footer>
      <el-button size="large" @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        size="large"
        :loading="saving"
        @click="saveNotes"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { updateWatchlistItem, type WatchlistItem } from "@/api/watchlist";

const props = defineProps<{
  modelValue: boolean;
  item: WatchlistItem | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const localNotes = ref("");
const saving = ref(false);

watch(
  () => props.modelValue,
  visible => {
    if (visible) {
      localNotes.value = props.item?.notes ?? "";
      saving.value = false;
    }
  }
);

function handleVisibleChange(value: boolean) {
  emit("update:modelValue", value);
}

function handleClose() {
  emit("update:modelValue", false);
}

const saveNotes = async () => {
  if (!props.item || props.item.id == null) return;
  saving.value = true;
  try {
    await updateWatchlistItem(props.item.id, { notes: localNotes.value });
    ElMessage.success("备注已保存");
    handleClose();
    emit("saved");
  } catch (e: unknown) {
    ElMessage.error("保存备注失败");
  } finally {
    saving.value = false;
  }
};
</script>
