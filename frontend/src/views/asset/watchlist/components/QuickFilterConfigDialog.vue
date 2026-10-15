<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { assetTypeLabel } from "@/composables/useEnumLabels";
import { useWatchlistQuickFilters } from "@/composables/useWatchlistQuickFilters";
import {
  PINNED_QUICK_TYPES,
  WATCHLIST_ASSET_TYPE_OPTIONS
} from "@/views/asset/watchlist/watchlistAssetTypes";

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

// 与筛选条共享同一单例：保存后快捷胶囊栏（QuickTypePills）即时重算，无需事件回传
const { quickFilters, setQuickFilters } = useWatchlistQuickFilters();

const PINNED: readonly string[] = PINNED_QUICK_TYPES;

/**
 * 展示顺序：常驻项（股票 / 基金，#2199 用户拍板恒外显）置顶成组，
 * 其余按类型池原序——锁定项与可勾选项分区可见，用户一眼看懂谁不能取消。
 */
const displayTypes = computed(() => {
  const pinned = WATCHLIST_ASSET_TYPE_OPTIONS.filter(t => PINNED.includes(t));
  const rest = WATCHLIST_ASSET_TYPE_OPTIONS.filter(t => !PINNED.includes(t));
  return [...pinned, ...rest];
});

/** 勾选草稿：每次打开以当前生效值重建（上次未保存的勾选不带入），常驻项恒在最前 */
const draft = ref<string[]>(buildDraft(quickFilters.value));

/** 重建草稿：常驻项强制置顶注入（composable 侧已保证生效值含 pinned，此处防御旧值） */
function buildDraft(filters: string[]): string[] {
  const rest = filters.filter(t => !PINNED.includes(t));
  return [...PINNED, ...rest];
}

watch(
  () => props.modelValue,
  visible => {
    if (visible) draft.value = buildDraft(quickFilters.value);
  }
);

/** 常驻锁定（#2199）：股票 / 基金 disabled 恒勾选，全选 / 取消全选均不放开 */
function isPinned(type: string): boolean {
  return PINNED.includes(type);
}

/**
 * 唯一勾选项锁定：快捷切换器除「全部」外至少保留 1 个类型，
 * 允许清空会得到只剩「全部」的空切换器（配置项 disabled 而非保存时报错）。
 */
function isLastLocked(type: string): boolean {
  return draft.value.length === 1 && draft.value.includes(type);
}

function isDisabled(type: string): boolean {
  return isPinned(type) || isLastLocked(type);
}

/** 全选（#2199）：一键勾选类型池全部 10 项；常驻项本就恒勾选，自然包含 */
const allSelected = computed(
  () => draft.value.length === WATCHLIST_ASSET_TYPE_OPTIONS.length
);

function selectAll(): void {
  draft.value = [...WATCHLIST_ASSET_TYPE_OPTIONS];
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
      勾选的类型会外露到主界面的类型快捷胶囊；未勾选的类型仍可在「筛选」面板中多选组合。
    </p>
    <!-- 常驻说明（#2199）：与下方置顶的 disabled 勾选项呼应，解释「为何取消不掉」 -->
    <p class="qf-hint">股票、基金为常用类型，始终显示。</p>
    <!-- 全选操作（#2199）：标题行 hint 区右上，已全选时置灰 -->
    <div class="qf-toolbar">
      <span class="qf-toolbar__spacer" />
      <el-button
        size="small"
        text
        type="primary"
        :disabled="allSelected"
        @click="selectAll"
      >
        {{ allSelected ? "已全选" : "全选" }}
      </el-button>
    </div>
    <el-checkbox-group v-model="draft" class="qf-list">
      <el-checkbox
        v-for="type in displayTypes"
        :key="type"
        :value="type"
        :disabled="isDisabled(type)"
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
/* hint 段：两行说明（外露语义 + 常驻语义）纵向排列，行距交给段落默认 margin */
.qf-hint {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

/* 工具行：左侧弹性占位把「全选」推到右缘，与网格右缘对齐 */
.qf-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}

.qf-toolbar__spacer {
  flex: 1;
}

/* 三列网格：类型池最多 10 项，两列会顶到 440px 宽之外的换行节奏不齐。
   常驻项（股票 / 基金）经 displayTypes 置顶排在第一行前两格（#2199） */
.qf-list {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 8px;
}
</style>
