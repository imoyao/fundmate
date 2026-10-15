<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { assetTypeLabel } from "@/composables/useEnumLabels";
import { useWatchlistQuickFilters } from "@/composables/useWatchlistQuickFilters";
import { WATCHLIST_ASSET_TYPE_OPTIONS } from "@/views/asset/watchlist/watchlistAssetTypes";

defineOptions({ name: "QuickFilterConfigDialog" });

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
}>();

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value)
});

// 与筛选条共享同一单例：保存后 TYPE_SEGMENTED_OPTIONS 即时重算，无需事件回传
const { quickFilters, setQuickFilters } = useWatchlistQuickFilters();

/** 勾选草稿：每次打开以当前生效值重建（上次未保存的勾选不带入） */
const draft = ref<string[]>([...quickFilters.value]);

watch(
  () => props.modelValue,
  visible => {
    if (visible) draft.value = [...quickFilters.value];
  }
);

/**
 * 唯一勾选项锁定：快捷切换器除「全部」外至少保留 1 个类型，
 * 允许清空会得到只剩「全部」的空切换器（配置项 disabled 而非保存时报错）。
 */
function isLastLocked(type: string): boolean {
  return draft.value.length === 1 && draft.value.includes(type);
}

function save() {
  setQuickFilters(draft.value);
  dialogVisible.value = false;
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="自定义快捷筛选"
    width="440px"
    append-to-body
  >
    <p class="qf-hint">
      勾选的类型会外露到主界面的类型快捷切换器；未勾选的类型仍可在「筛选」面板中多选组合。
    </p>
    <el-checkbox-group v-model="draft" class="qf-list">
      <el-checkbox
        v-for="type in WATCHLIST_ASSET_TYPE_OPTIONS"
        :key="type"
        :value="type"
        :disabled="isLastLocked(type)"
      >
        {{ assetTypeLabel(type) }}
      </el-checkbox>
    </el-checkbox-group>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.qf-hint {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-secondary);
}

/* 三列网格：类型池最多 10 项，两列会顶到 440px 宽之外的换行节奏不齐 */
.qf-list {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 8px;
}
</style>
