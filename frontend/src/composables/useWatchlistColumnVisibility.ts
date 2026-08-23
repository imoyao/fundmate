/**
 * 自选表格列显隐 + 顺序偏好（issue #993 / #992）
 *
 * 职责：维护「哪些列被用户隐藏」与「可拖拽列的自定义顺序」，经 localforage
 * （IndexedDB 优先，降级 localStorage）持久化到本机。纯前端零后端
 * （2026-08-20 决策：后端暂无 user_preferences 表，上云待该基建落地后再迁移）。
 *
 * 设计要点：
 * - 模块级单例状态：自选页 index.vue 与 SettingsDrawer 共享同一份，
 *   抽屉内勾选即时反映到表格，无需事件往返；
 * - 只持久化「被隐藏的列 key」+「可拖拽列的顺序」，而非全量配置：
 *   新增列默认可见且落在默认位置，避免老用户升级后新列被旧缓存吃掉；
 * - 顺序只记录 draggable=true 的中段列：固定列（marker/product 左固定、
 *   actions 右固定）不参与拖拽，重建时按默认定义归位。
 */
import { computed, ref, type ComputedRef } from "vue";
import { localForage } from "@/utils/localforage";
import {
  watchlistColumnDefs,
  type ColumnDef
} from "@/views/asset/watchlist/columnDefs";

const STORAGE_KEY = "watchlist-column-settings";

/** 列设置持久化结构 */
interface ColumnSettings {
  hidden: string[];
  /** 可拖拽列的自定义顺序（key 数组）；缺省 = 默认定义顺序（#992） */
  order?: string[];
}

/** 模块级单例：页面与抽屉共享同一份状态 */
const hiddenKeys = ref<Set<string>>(new Set());
const customOrder = ref<string[]>([]);
let loadStarted = false;

/** 启动时异步恢复本地偏好；失败静默回退默认（缓存损坏不应锁死表格） */
async function loadSettings(): Promise<void> {
  try {
    const saved = await localForage().getItem<ColumnSettings>(STORAGE_KEY);
    if (saved && Array.isArray(saved.hidden)) {
      hiddenKeys.value = new Set(saved.hidden);
    }
    if (saved && Array.isArray(saved.order)) {
      // 只保留仍存在于当前定义中的 key（定义删列后旧缓存不产生幽灵顺序）
      const known = new Set(
        watchlistColumnDefs.filter(d => d.draggable).map(d => d.key)
      );
      customOrder.value = saved.order.filter(k => known.has(k));
    }
  } catch {
    /* 读取失败按无偏好处理 */
  }
}

function persistSettings(): void {
  localForage()
    .setItem<ColumnSettings>(STORAGE_KEY, {
      hidden: [...hiddenKeys.value],
      order: [...customOrder.value]
    })
    .catch(() => {
      /* 持久化失败不影响会话内生效（IndexedDB 不可用时降级由库内部处理） */
    });
}

export interface WatchlistColumnVisibility {
  /** 可被用户隐藏的列（hideable=true），供设置面板渲染勾选项 */
  hideableColumns: ComputedRef<ColumnDef[]>;
  /** 实际参与表格渲染的列：按自定义顺序排列，再过滤掉被隐藏的列 */
  visibleColumns: ComputedRef<ColumnDef[]>;
  isHidden: (key: string) => boolean;
  toggleColumn: (key: string, visible: boolean) => void;
  resetColumns: () => void;
  /** 表头拖拽结束：提交可拖拽列的新顺序（#992） */
  applyOrder: (orderedKeys: string[]) => void;
}

export function useWatchlistColumnVisibility(): WatchlistColumnVisibility {
  if (!loadStarted) {
    loadStarted = true;
    void loadSettings();
  }

  const hideableColumns = computed(() =>
    watchlistColumnDefs.filter(d => d.hideable)
  );

  /**
   * 全量列按自定义顺序重排：非拖拽列（固定列/内置列）保持默认锚点位置，
   * 拖拽列按保存顺序依次填入原拖拽区槽位——固定列左右包夹的布局不被破坏。
   */
  const orderedColumns = computed(() => {
    if (customOrder.value.length === 0) return watchlistColumnDefs;
    const orderIndex = new Map(customOrder.value.map((k, i) => [k, i]));
    const draggables = watchlistColumnDefs
      .filter(d => d.draggable && orderIndex.has(d.key))
      .sort((a, b) => orderIndex.get(a.key)! - orderIndex.get(b.key)!);
    const queue = [...draggables];
    return watchlistColumnDefs.map(d =>
      d.draggable ? (queue.shift() ?? d) : d
    );
  });

  const visibleColumns = computed(() =>
    orderedColumns.value.filter(
      d => !d.hideable || !hiddenKeys.value.has(d.key)
    )
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
    customOrder.value = [];
    persistSettings();
  }

  function applyOrder(orderedKeys: string[]): void {
    customOrder.value = orderedKeys;
    persistSettings();
  }

  return {
    hideableColumns,
    visibleColumns,
    isHidden,
    toggleColumn,
    resetColumns,
    applyOrder
  };
}
