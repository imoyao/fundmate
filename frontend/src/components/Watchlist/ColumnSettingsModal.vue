<template>
  <el-dialog
    v-model="visible"
    title="表格列显示"
    width="800px"
    top="6vh"
    append-to-body
    class="column-settings-modal"
  >
    <div class="cs-layout">
      <!-- 左导航：按品类视图分组（通用 + 该产品专属） -->
      <nav class="cs-nav">
        <button
          v-for="grp in groups"
          :key="grp.key"
          type="button"
          class="cs-nav__item"
          :class="{ 'is-active': activeGroup === grp.key }"
          @click="activeGroup = grp.key"
        >
          <span class="cs-nav__label">{{ grp.title }}</span>
          <span v-if="hiddenInGroup(grp)" class="cs-nav__badge">{{
            hiddenInGroup(grp)
          }}</span>
        </button>
      </nav>
      <!-- 右内容：当前品类的列勾选项（通用/专属配色区分） -->
      <div class="cs-content">
        <p class="cs-content__desc">{{ activeGroupMeta?.desc }}</p>
        <div class="flex flex-wrap gap-3">
          <div
            v-for="col in activeCols"
            :key="col.key"
            class="cs-item"
            :class="
              col.scope === 'mixed' ? 'cs-item--general' : 'cs-item--specific'
            "
          >
            <el-checkbox
              :model-value="!columnSettings!.isHidden(col.key)"
              @change="(v: boolean) => columnSettings!.toggleColumn(col.key, v)"
            >
              {{ col.label }}
            </el-checkbox>
          </div>
        </div>
      </div>
    </div>
    <template #footer>
      <div class="flex items-center justify-between">
        <el-button
          v-if="hiddenCount > 0"
          text
          @click="columnSettings!.resetColumns()"
          >恢复默认列</el-button
        >
        <span v-else />
        <el-button type="primary" @click="visible = false">完成</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { WatchlistColumnVisibility } from "@/composables/useWatchlistColumnVisibility";
import type {
  ColumnDef,
  ColumnGroup
} from "@/views/asset/watchlist/columnDefs";

const props = defineProps<{
  modelValue: boolean;
  /** 列显隐偏好实例（#993）：与自选页/抽屉共享同一单例，勾选即时反映到表格 */
  columnSettings?: WatchlistColumnVisibility;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

/** 按品类视图分组的列（通用列 + 该产品专属列，见 composable） */
const groups = computed(
  () => props.columnSettings?.groupedHideableColumns.value ?? []
);
/** 当前选中的品类导航（默认「通用字段」） */
const activeGroup = ref<ColumnGroup>("general");
const activeGroupMeta = computed(() =>
  groups.value.find(g => g.key === activeGroup.value)
);
const activeCols = computed(() => activeGroupMeta.value?.cols ?? []);

/** 某组被隐藏的列数（左导航角标，提示用户哪一组有改动） */
function hiddenInGroup(grp: { cols: ColumnDef[] }): number {
  if (!props.columnSettings) return 0;
  return grp.cols.filter(c => props.columnSettings!.isHidden(c.key)).length;
}

/** 全局隐藏列数（footer「恢复默认列」显隐） */
const hiddenCount = computed(() => {
  if (!props.columnSettings) return 0;
  return groups.value
    .flatMap(g => g.cols)
    .filter(c => props.columnSettings!.isHidden(c.key)).length;
});
</script>

<style scoped>
/* ── 表格列显示：宽模态框 + 左导航（方案三，2026-09-12）── */
.cs-layout {
  display: flex;
  gap: 16px;
  height: 56vh;
  min-height: 420px;
}

.cs-nav {
  flex-shrink: 0;
  width: 168px;
  padding-right: 8px;
  overflow-y: auto;
  border-right: 1px solid var(--border-light);
}

.cs-nav__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 8px;
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.cs-nav__item:hover {
  background-color: var(--bg-soft);
}

.cs-nav__item.is-active {
  font-weight: 600;
  color: var(--brand-700);
  background-color: var(--brand-100);
}

.cs-nav__badge {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 10px;
  line-height: 16px;
  color: #fff;
  text-align: center;
  background-color: var(--color-warning);
  border-radius: 8px;
}

.cs-content {
  flex: 1;
  padding-right: 8px;
  overflow-y: auto;
}

.cs-content__desc {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 通用列 / 专属列配色区分（用户建议：两类字段不应混在一起） */
.cs-item {
  padding: 6px 10px;
  border-radius: 8px;
}

.cs-item--general {
  background-color: var(--bg-soft);
}

.cs-item--specific {
  background-color: var(--brand-100);
}

.cs-item :deep(.el-checkbox__label) {
  font-size: 13px;
}
</style>
