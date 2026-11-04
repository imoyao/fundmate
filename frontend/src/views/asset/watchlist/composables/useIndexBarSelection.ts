/**
 * 指数条「用户个性化选中 + 顺序」状态（#watchlist 指数个性化设置）。
 *
 * 模块级单例：IndexMarketBar（按选中渲染）与 IndexPersonalizationDialog（编辑）共享同一份，
 * 弹窗保存后顶栏即时重算，无需事件回传。
 *
 * 持久化：本机 localforage（key `watchlist-index-bar-selection`），不上云（纯视图偏好）。
 * 加载完成前不回写，避免覆盖持久值；脏 key（不在目录中）落盘前过滤。
 */
import { ref, watch, type Ref } from "vue";
import { localForage } from "@/utils/localforage";
import { MAX_INDEX_COUNT } from "@/views/asset/watchlist/composables/indexBarModel";
import {
  DEFAULT_INDEX_KEYS,
  filterValidKeys,
  INDEX_CATALOG_BY_KEY,
  type IndexCatalogEntry
} from "@/views/asset/watchlist/composables/indexCatalog";

const STORAGE_KEY = "watchlist-index-bar-selection";

/** 截到上限（去脏 key 后）：既挡住新选择，也收敛历史数据 */
function normalize(keys: string[]): string[] {
  return filterValidKeys(keys).slice(0, MAX_INDEX_COUNT);
}

const selected = ref<string[]>([]);
let loadStarted = false;
let hydrated = false;
let watchStarted = false;

function load(): void {
  if (loadStarted) return;
  loadStarted = true;
  localForage()
    .getItem<string[]>(STORAGE_KEY)
    .then(v => {
      selected.value =
        Array.isArray(v) && v.length ? normalize(v) : [...DEFAULT_INDEX_KEYS];
      hydrated = true;
    })
    .catch(() => {
      selected.value = [...DEFAULT_INDEX_KEYS];
      hydrated = true;
    });
}

function ensureWatch(): void {
  if (watchStarted) return;
  watchStarted = true;
  watch(
    selected,
    next => {
      if (!hydrated) return;
      localForage()
        .setItem(STORAGE_KEY, filterValidKeys(next))
        .catch(() => {
          /* 本地写失败不阻塞交互 */
        });
    },
    { deep: true }
  );
}

export interface IndexBarSelection {
  /** 当前选中指数 key（按展示顺序） */
  selected: Ref<string[]>;
  /** 选中 key 对应的目录条目（按 selected 顺序；剔除脏 key） */
  selectedEntries: Ref<IndexCatalogEntry[]>;
  addIndex: (key: string) => void;
  removeIndex: (key: string) => void;
  /** 上移(-1) / 下移(+1)，用于弹窗内的排序 */
  moveIndex: (key: string, dir: -1 | 1) => void;
  /** 整体替换（弹窗「保存」时提交草稿） */
  setSelection: (keys: string[]) => void;
  resetToDefault: () => void;
}

export function useIndexBarSelection(): IndexBarSelection {
  load();
  ensureWatch();

  const selectedEntries = ref<IndexCatalogEntry[]>([]);
  // selected → 目录条目（按序，剔除脏 key），供渲染与弹窗共用
  watch(
    selected,
    val => {
      selectedEntries.value = val
        .map(k => INDEX_CATALOG_BY_KEY[k])
        .filter((e): e is IndexCatalogEntry => Boolean(e));
    },
    { immediate: true }
  );

  function addIndex(key: string): void {
    if (selected.value.length >= MAX_INDEX_COUNT) return;
    if (INDEX_CATALOG_BY_KEY[key] && !selected.value.includes(key)) {
      selected.value = [...selected.value, key];
    }
  }

  function removeIndex(key: string): void {
    selected.value = selected.value.filter(k => k !== key);
  }

  function moveIndex(key: string, dir: -1 | 1): void {
    const arr = [...selected.value];
    const i = arr.indexOf(key);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= arr.length) return;
    [arr[i], arr[j]] = [arr[j], arr[i]];
    selected.value = arr;
  }

  function setSelection(keys: string[]): void {
    selected.value = normalize(keys);
  }

  function resetToDefault(): void {
    selected.value = [...DEFAULT_INDEX_KEYS];
  }

  return {
    selected,
    selectedEntries,
    addIndex,
    removeIndex,
    moveIndex,
    setSelection,
    resetToDefault
  };
}
