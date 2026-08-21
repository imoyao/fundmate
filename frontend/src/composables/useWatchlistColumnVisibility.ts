/**
 * 自选表格列显隐偏好（issue #993）
 *
 * 职责：维护「哪些列被用户隐藏」，经 localforage（IndexedDB 优先，降级
 * localStorage）持久化到本机。纯前端零后端（2026-08-20 决策：
 * 后端暂无 user_preferences 表，上云待该基建落地后再迁移）。
 *
 * 设计要点：
 * - 模块级单例状态：自选页 index.vue 与 SettingsDrawer 共享同一份，
 *   抽屉内勾选即时反映到表格，无需事件往返；
 * - 只持久化「被隐藏的列 key」而非全量配置：新增列默认可见，
 *   避免老用户升级后新列被旧缓存吃掉；
 * - #992（列顺序拖拽）落地时在本存储结构上扩展 order 字段，不动本文件 API。
 */
import { computed, ref, type ComputedRef } from "vue";
import { localForage } from "@/utils/localforage";
import {
  watchlistColumnDefs,
  type ColumnDef
} from "@/views/asset/watchlist/columnDefs";

const STORAGE_KEY = "watchlist-column-settings";

/** 列设置持久化结构：#993 只存 hidden；#992 扩展 order */
interface ColumnSettings {
  hidden: string[];
}

/** 模块级单例：页面与抽屉共享同一份状态 */
const hiddenKeys = ref<Set<string>>(new Set());
let loadStarted = false;

/** 启动时异步恢复本地偏好；失败静默回退全可见（缓存损坏不应锁死表格） */
async function loadSettings(): Promise<void> {
  try {
    const saved = await localForage().getItem<ColumnSettings>(STORAGE_KEY);
    if (saved && Array.isArray(saved.hidden)) {
      hiddenKeys.value = new Set(saved.hidden);
    }
  } catch {
    /* 读取失败按无偏好处理 */
  }
}

function persistSettings(): void {
  localForage()
    .setItem<ColumnSettings>(STORAGE_KEY, {
      hidden: [...hiddenKeys.value]
    })
    .catch(() => {
      /* 持久化失败不影响会话内生效（IndexedDB 不可用时降级由库内部处理） */
    });
}

export interface WatchlistColumnVisibility {
  /** 可被用户隐藏的列（hideable=true），供设置面板渲染勾选项 */
  hideableColumns: ComputedRef<ColumnDef[]>;
  /** 实际参与表格渲染的列：非 hideable 列恒可见，hideable 列按隐藏集过滤 */
  visibleColumns: ComputedRef<ColumnDef[]>;
  isHidden: (key: string) => boolean;
  toggleColumn: (key: string, visible: boolean) => void;
  resetColumns: () => void;
}

export function useWatchlistColumnVisibility(): WatchlistColumnVisibility {
  if (!loadStarted) {
    loadStarted = true;
    void loadSettings();
  }

  const hideableColumns = computed(() =>
    watchlistColumnDefs.filter(d => d.hideable)
  );

  const visibleColumns = computed(() =>
    watchlistColumnDefs.filter(d => !d.hideable || !hiddenKeys.value.has(d.key))
  );

  function isHidden(key: string): boolean {
    return hiddenKeys.value.has(key);
  }

  function toggleColumn(key: string, visible: boolean): void {
    const next = new Set(hiddenKeys.value);
    if (visible) next.delete(key);
    else next.add(key);
    hiddenKeys.value = next;
    persistSettings();
  }

  function resetColumns(): void {
    hiddenKeys.value = new Set();
    persistSettings();
  }

  return {
    hideableColumns,
    visibleColumns,
    isHidden,
    toggleColumn,
    resetColumns
  };
}
