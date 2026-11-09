/**
 * 指数条「用户个性化选中 + 顺序」状态（#watchlist 指数个性化设置）。
 *
 * 模块级单例：IndexMarketBar（按选中渲染）与 IndexPersonalizationDialog（编辑）共享同一份，
 * 弹窗保存后顶栏即时重算，无需事件回传。
 *
 * 持久化：本机 localforage（key `watchlist-index-bar-selection`），不上云（纯视图偏好）。
 *
 * ## 为什么写盘放在 mutator 里，而不是 `watch(selected)`
 *
 * 旧版把落盘写成 `watch(selected, …)`，而那个 watcher 是在**组件 setup() 里**创建的
 * ——它绑在第一个调用方（IndexMarketBar）的 effect scope 上，**组件卸载时被一起 stop**。
 * 于是「关页签 / 右键刷新 / 登出清缓存」让自选页重挂载后，模块级状态还在（顶栏照常显示
 * 用户选的列表），但**再没有任何人把改动写进 IndexedDB**：保存看起来成功，刷新后回到旧值。
 * 这就是「指数设置存不住、很快被重置成默认列表」的根因。
 *
 * 现在写盘只发生在**用户动作**里（add/remove/move/setSelection/reset），与组件生命周期
 * 无关；读盘只负责「显示什么」，不再有第三个写入者。
 *
 * ## 读不到 ≠ 用户选了默认
 *
 * 读盘失败（IndexedDB 被清 / 被拦截 / 驱动降级）时只回落默认列表**用于显示**，
 * **不写盘**——把默认值落盘会把用户真实设置永久覆盖掉，且下一次读取再也拿不回来。
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
/**
 * 用户是否已在本会话内改过选中。
 *
 * 读盘是异步的：若它回来得比用户第一次改动晚，**不得**用旧值覆盖用户刚做的选择
 * （那一笔已经在 commit 里落盘了）。
 */
let userTouched = false;

/**
 * 落盘。失败必须可见——旧版这里是空 catch，导致「保存成功但没落盘」完全无声，
 * 排查时既无日志也无从复现。
 */
function persist(next: string[]): void {
  localForage()
    .setItem(STORAGE_KEY, next)
    .catch((err: unknown) => {
      console.warn("[index-bar] 指数条选择落盘失败", err);
    });
}

/** 用户动作的唯一写入口：改内存 + 落盘（与组件是否挂载、是否重挂载无关） */
function commit(next: string[]): void {
  userTouched = true;
  selected.value = next;
  persist(next);
}

function load(): void {
  if (loadStarted) return;
  loadStarted = true;
  localForage()
    .getItem<string[]>(STORAGE_KEY)
    .then(v => {
      if (userTouched) return;
      // 空 / 非数组 = 没存过：只回落显示，不写盘（写盘会固化成「用户选择」）
      selected.value =
        Array.isArray(v) && v.length ? normalize(v) : [...DEFAULT_INDEX_KEYS];
    })
    .catch((err: unknown) => {
      if (userTouched) return;
      selected.value = [...DEFAULT_INDEX_KEYS];
      console.warn(
        "[index-bar] 指数条选择读取失败，本次回落默认列表（不落盘）",
        err
      );
    });
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

  const selectedEntries = ref<IndexCatalogEntry[]>([]);
  // selected → 目录条目（按序，剔除脏 key），供渲染与弹窗共用。
  // 这个 watcher 只做**派生显示**（脏了顶多渲染少一项），
  // 与写盘无关，故随组件卸载一并消失也无副作用。
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
      commit([...selected.value, key]);
    }
  }

  function removeIndex(key: string): void {
    if (!selected.value.includes(key)) return;
    commit(selected.value.filter(k => k !== key));
  }

  function moveIndex(key: string, dir: -1 | 1): void {
    const arr = [...selected.value];
    const i = arr.indexOf(key);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= arr.length) return;
    [arr[i], arr[j]] = [arr[j], arr[i]];
    commit(arr);
  }

  function setSelection(keys: string[]): void {
    commit(normalize(keys));
  }

  function resetToDefault(): void {
    commit([...DEFAULT_INDEX_KEYS]);
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
