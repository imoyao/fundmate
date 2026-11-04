<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ArrowDown, ArrowUp, Close, Rank } from "@element-plus/icons-vue";
import { useIndexBarSelection } from "@/views/asset/watchlist/composables/useIndexBarSelection";
import { MAX_INDEX_COUNT } from "@/views/asset/watchlist/composables/indexBarModel";
import IndexBarMotionToggle from "@/views/asset/watchlist/components/IndexBarMotionToggle.vue";
import {
  DEFAULT_INDEX_KEYS,
  INDEX_CATALOG,
  type IndexCatalogEntry,
  type IndexMarketGroup
} from "@/views/asset/watchlist/composables/indexCatalog";

defineOptions({ name: "IndexPersonalizationDialog" });

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ (e: "update:modelValue", value: boolean): void }>();

const dialogVisible = computed({
  get: () => props.modelValue,
  set: value => emit("update:modelValue", value)
});

// 与顶栏共享单例：保存后 IndexMarketBar 即时重算
const { selected, setSelection } = useIndexBarSelection();

/** 编辑草稿：每次打开以当前生效值重建（未保存的改动不带入下次） */
const draft = ref<string[]>([]);
watch(
  () => props.modelValue,
  visible => {
    if (visible) draft.value = [...selected.value];
  }
);

function entryOf(key: string): IndexCatalogEntry | undefined {
  return INDEX_CATALOG.find(e => e.key === key);
}

const GROUP_ORDER: IndexMarketGroup[] = ["CN", "HK", "US"];
function groupLabel(g?: IndexMarketGroup): string {
  if (g === "CN") return "A股";
  if (g === "HK") return "港股";
  if (g === "US") return "美股";
  return "";
}

const available = computed(() =>
  INDEX_CATALOG.filter(e => !draft.value.includes(e.key))
);
function availableByGroup(g: IndexMarketGroup): IndexCatalogEntry[] {
  return available.value.filter(e => e.group === g);
}

/** 至少保留 1 个：最后一个不可删（避免顶栏变空） */
function isLastLocked(key: string): boolean {
  return draft.value.length === 1 && draft.value.includes(key);
}

// ── 拖拽排序（原生 HTML5，零依赖） ──
const dragIndex = ref<number | null>(null);
function onDragStart(i: number): void {
  dragIndex.value = i;
}
function onDrop(i: number): void {
  const from = dragIndex.value;
  dragIndex.value = null;
  if (from === null || from === i) return;
  const arr = [...draft.value];
  const [m] = arr.splice(from, 1);
  arr.splice(i, 0, m);
  draft.value = arr;
}

function moveDraft(i: number, dir: -1 | 1): void {
  const j = i + dir;
  if (j < 0 || j >= draft.value.length) return;
  const arr = [...draft.value];
  [arr[i], arr[j]] = [arr[j], arr[i]];
  draft.value = arr;
}

/** 已满上限：新增按钮禁用（上限口径见 indexBarModel.MAX_INDEX_COUNT） */
const draftFull = computed(() => draft.value.length >= MAX_INDEX_COUNT);

function addDraft(key: string): void {
  if (draftFull.value) return;
  if (!draft.value.includes(key)) draft.value = [...draft.value, key];
}
function removeDraft(key: string): void {
  if (!isLastLocked(key)) draft.value = draft.value.filter(k => k !== key);
}

function resetDraft(): void {
  draft.value = [...DEFAULT_INDEX_KEYS];
}

function save(): void {
  setSelection(draft.value);
  dialogVisible.value = false;
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="指数个性化设置"
    width="480px"
    append-to-body
  >
    <p class="hint">
      已添加的指数会显示在自选页顶部；拖动或用箭头排序，可点击删除。下方点选即可添加。
      最多 <b>{{ MAX_INDEX_COUNT }}</b> 个（每个指数每 30
      秒各取一次分时，超出会明显变慢）。
    </p>

    <!-- 已添加 -->
    <div class="section">
      <div class="section__head">
        <span class="section__title">
          已添加指数
          <em class="section__count" :class="{ 'is-full': draftFull }">
            {{ draft.length }}/{{ MAX_INDEX_COUNT }}
          </em>
        </span>
        <el-button size="small" text type="primary" @click="resetDraft">
          恢复默认
        </el-button>
      </div>
      <ul class="picked-list">
        <li
          v-for="(key, i) in draft"
          :key="key"
          class="picked-item"
          draggable="true"
          @dragstart="onDragStart(i)"
          @dragover.prevent
          @drop="onDrop(i)"
          @dragend="dragIndex = null"
        >
          <span class="picked-item__handle" aria-hidden="true">
            <el-icon><Rank /></el-icon>
          </span>
          <span class="picked-item__name">{{ entryOf(key)?.name }}</span>
          <span class="picked-item__group">{{
            groupLabel(entryOf(key)?.group)
          }}</span>
          <span class="picked-item__actions">
            <button
              type="button"
              class="icon-btn"
              :disabled="i === 0"
              aria-label="上移"
              @click="moveDraft(i, -1)"
            >
              <el-icon><ArrowUp /></el-icon>
            </button>
            <button
              type="button"
              class="icon-btn"
              :disabled="i === draft.length - 1"
              aria-label="下移"
              @click="moveDraft(i, 1)"
            >
              <el-icon><ArrowDown /></el-icon>
            </button>
            <button
              type="button"
              class="icon-btn"
              :disabled="isLastLocked(key)"
              aria-label="删除"
              @click="removeDraft(key)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </span>
        </li>
      </ul>
    </div>

    <!-- 可选 -->
    <div class="section">
      <div class="section__head">
        <span class="section__title">可选指数</span>
      </div>
      <div v-for="g in GROUP_ORDER" :key="g" class="opt-group">
        <div class="opt-group__label">{{ groupLabel(g) }}</div>
        <div class="opt-chips">
          <button
            v-for="e in availableByGroup(g)"
            :key="e.key"
            type="button"
            class="opt-chip"
            :disabled="draftFull"
            :title="
              draftFull ? `已达上限 ${MAX_INDEX_COUNT} 个，请先删除一个` : ''
            "
            @click="addDraft(e.key)"
          >
            + {{ e.name }}
          </button>
        </div>
      </div>
    </div>

    <!-- 显示偏好（即时生效，不参与「保存」） -->
    <div class="section">
      <div class="section__head">
        <span class="section__title">显示</span>
      </div>
      <IndexBarMotionToggle />
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.hint {
  margin-bottom: 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);

  b {
    color: var(--text-primary);
  }
}

.section {
  margin-bottom: 16px;

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  &__title {
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-primary);
  }

  // 已选数量计数：满上限时转品牌墨色，替代 toast 之类的打断式提示
  &__count {
    margin-left: 4px;
    font-size: var(--text-label);
    font-style: normal;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text-disabled, #bbb);

    &.is-full {
      color: var(--brand-ink, #b8361f);
    }
  }
}

.picked-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.picked-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  background: var(--bg-page, #fafafa);
  border: 1px solid var(--border-default, #eee);
  border-radius: 10px;

  &__handle {
    display: inline-flex;
    color: var(--text-disabled, #bbb);
    cursor: grab;
  }

  &__name {
    flex: 1;
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-primary);
  }

  &__group {
    font-size: var(--text-label);
    color: var(--text-disabled, #bbb);
  }

  &__actions {
    display: inline-flex;
    gap: 2px;
  }
}

.icon-btn {
  display: inline-flex;
  padding: 4px;
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 6px;
  transition:
    background-color 150ms ease,
    color 150ms ease;

  &:hover:not(:disabled) {
    color: var(--text-primary);
    background: var(--bg-hover, #f2ede8);
  }

  &:disabled {
    color: var(--text-disabled, #bbb);
    cursor: not-allowed;
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
}

.opt-group {
  margin-bottom: 10px;

  &__label {
    margin-bottom: 6px;
    font-size: var(--text-label);
    color: var(--text-secondary);
  }
}

.opt-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.opt-chip {
  padding: 4px 12px;
  font: inherit;
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-light, #f0ebe4);
  border-radius: var(--radius-pill, 9999px);
  transition:
    background-color 150ms ease,
    color 150ms ease;

  &:hover:not(:disabled) {
    color: var(--text-primary);
    background: var(--bg-hover, #f2ede8);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }

  // 已达上限：星标头提示 + 这里直接禁用，不做 toast 打断
  &:disabled {
    color: var(--text-disabled, #bbb);
    cursor: not-allowed;
    background: var(--bg-page, #fafafa);
  }
}
</style>
