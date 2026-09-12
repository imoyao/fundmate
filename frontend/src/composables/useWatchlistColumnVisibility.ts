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
import { computed, ref, type ComputedRef, type Ref } from "vue";
import { localForage } from "@/utils/localforage";
import {
  watchlistColumnDefs,
  COLUMN_GROUP_META,
  getColumnGroup,
  type ColumnDef,
  type ColumnGroup
} from "@/views/asset/watchlist/columnDefs";

const STORAGE_KEY = "watchlist-column-settings";

/** 列设置持久化结构 */
interface ColumnSettings {
  hidden: string[];
  /**
   * 被用户「显式开启」的默认隐藏列（defaultHidden=true）。
   * 与 hidden 分开存：hidden 记「用户关掉的」，shown 记「用户打开的」，二者互斥。
   * 旧缓存缺 shown 字段时按「从未开启」处理，新增列保持隐藏（不打扰老用户）。
   */
  shown?: string[];
  /** 可拖拽列的自定义顺序（key 数组）；缺省 = 默认定义顺序（#992） */
  order?: string[];
}

/** 模块级单例：页面与抽屉共享同一份状态 */
const hiddenKeys = ref<Set<string>>(new Set());
/** 默认隐藏、但被用户显式开启过的列（#993 新增列的默认关闭语义） */
const shownKeys = ref<Set<string>>(new Set());
const customOrder = ref<string[]>([]);
let loadStarted = false;

/** 启动时异步恢复本地偏好；失败静默回退默认（缓存损坏不应锁死表格） */
async function loadSettings(): Promise<void> {
  try {
    const saved = await localForage().getItem<ColumnSettings>(STORAGE_KEY);
    if (saved && Array.isArray(saved.hidden)) {
      hiddenKeys.value = new Set(saved.hidden);
    }
    if (saved && Array.isArray(saved.shown)) {
      shownKeys.value = new Set(saved.shown);
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
      shown: [...shownKeys.value],
      order: [...customOrder.value]
    })
    .catch(() => {
      /* 持久化失败不影响会话内生效（IndexedDB 不可用时降级由库内部处理） */
    });
}

export interface WatchlistColumnVisibility {
  /** 可被用户隐藏的列（hideable=true），供设置面板渲染勾选项 */
  hideableColumns: ComputedRef<ColumnDef[]>;
  /**
   * 按品类分组的可隐藏列（2026-09-12）：分组仅影响设置面板的呈现组织，
   * 不改变显隐判定（仍走 isHidden/toggleColumn）。空分组自动剔除。
   */
  groupedHideableColumns: ComputedRef<
    { key: ColumnGroup; title: string; desc: string; cols: ColumnDef[] }[]
  >;
  /** 实际参与表格渲染的列：按自定义顺序排列，再过滤掉被隐藏的列 */
  visibleColumns: ComputedRef<ColumnDef[]>;
  isHidden: (key: string) => boolean;
  toggleColumn: (key: string, visible: boolean) => void;
  resetColumns: () => void;
  /** 表头拖拽结束：提交可拖拽列的新顺序（#992） */
  applyOrder: (orderedKeys: string[]) => void;
}

export function useWatchlistColumnVisibility(
  activeCategory?: Ref<string | null> | ComputedRef<string | null>
): WatchlistColumnVisibility {
  if (!loadStarted) {
    loadStarted = true;
    void loadSettings();
  }

  /** 当前「品类」：类型筛选命中单一品类时为其 asset_type；否则 null＝混合视图（#1285） */
  const activeCat = computed(() => activeCategory?.value ?? null);

  /**
   * 视图作用域可见性（不含用户显隐偏好）。两个维度各管一段，互不越权：
   * - **混合视图**（`cat == null`）：看 `scope` —— 只有 `scope:"mixed"` 的通用列出现；
   * - **品类视图**（命中单一品类）：看 `appliesTo` —— 该列对当前品类成立（缺省＝全品类）即出现，
   *   与 `scope` 无关。`scope` 只回答「混合视图要不要出现」，不回答「品类视图要不要出现」。
   *
   * 历史坑（#1425 用户实测）：原实现把 `if (def.scope === "mixed") return true;` 短路在最前，
   * 于是「最新价 / 涨跌幅 / 持有数量 / 持仓市值 / 持仓收益」这些 `scope:"mixed"` 的列，
   * 在**基金经理、投顾组合**这类无行情、无持仓语义的品类视图里也照常出现
   * （选「基金经理」看到的表头却是最新价 / 涨跌幅 / 持有数量）。
   * 现改为品类视图一律由 `appliesTo` 把关，配合 columnDefs 的
   * `QUOTE_TYPES`（有行情）与 `TRADABLE_TYPES`（可交易）收敛适用范围。
   */
  function isVisibleInView(def: ColumnDef): boolean {
    const cat = activeCat.value;
    if (cat) return !def.appliesTo || def.appliesTo.includes(cat);
    return def.scope === "mixed";
  }

  const hideableColumns = computed(() =>
    watchlistColumnDefs.filter(d => d.hideable)
  );

  /**
   * 按品类分组（设置面板「表格列显示」分块渲染）：顺序取 COLUMN_GROUP_META，
   * 每个分组装入归属该组的 hideable 列；无列的组剔除，避免空标题。
   */
  const groupedHideableColumns = computed(() =>
    COLUMN_GROUP_META.map(g => ({
      ...g,
      cols: hideableColumns.value.filter(c => getColumnGroup(c.key) === g.key)
    })).filter(g => g.cols.length > 0)
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

  /**
   * 实际渲染的列 = 自定义顺序 × 用户显隐偏好 × **视图作用域**（#1285）：
   * - 固定/内置列恒显示；
   * - 用户显式关闭（hiddenKeys）→ 隐藏；
   * - 用户显式开启（shownKeys）→ **任何视图都显示**（覆盖视图作用域与默认隐藏）；
   * - 默认隐藏且未开启 → 隐藏；
   * - 其余按视图作用域：混合视图只显示 `scope:"mixed"` 通用列；
   *   品类视图显示该品类命中 `appliesTo` 的列。
   */
  const visibleColumns = computed(() =>
    orderedColumns.value.filter(d => {
      if (!d.hideable) return true;
      if (hiddenKeys.value.has(d.key)) return false;
      if (shownKeys.value.has(d.key)) return true;
      if (d.defaultHidden) return false;
      return isVisibleInView(d);
    })
  );

  /**
   * 返回「当前视图下是否实际隐藏」，而非「用户是否显式隐藏过」。
   * SettingsDrawer 以 `!isHidden(key)` 作为勾选框的 model-value：
   * - 默认隐藏列 / 当前视图不含的品类专属列，都会显示为「未勾选」，与表格所见一致；
   * - 勾上即「显式开启」→ 任何视图都显示（`toggleColumn` 对称）。
   * hiddenCount 统计同样依赖本语义。
   */
  function isHidden(key: string): boolean {
    const def = watchlistColumnDefs.find(d => d.key === key);
    // 不可隐藏列恒为可见：即便历史残留 hiddenKeys 含该 key，也不应显示「已隐藏」矛盾态
    if (def && !def.hideable) return false;
    return !visibleColumns.value.some(d => d.key === key);
  }

  function toggleColumn(key: string, visible: boolean): void {
    const def = watchlistColumnDefs.find(d => d.key === key);
    // 不可隐藏列（固定列/内置列）恒可见：即便被错误调用也不写入持久化数据，避免污染
    if (!def || !def.hideable) return;
    const nextHidden = new Set(hiddenKeys.value);
    const nextShown = new Set(shownKeys.value);
    if (visible) {
      nextHidden.delete(key);
      // 显式开启：仅当「无用户偏好时该列仍不可见」（默认隐藏 / 当前视图不含它）才记入 shown，
      // 否则记入只是污染持久化数据。shown 语义 = 任何视图都显示。
      if (def.defaultHidden || !isVisibleInView(def)) nextShown.add(key);
      else nextShown.delete(key);
    } else {
      nextHidden.add(key);
      nextShown.delete(key);
    }
    hiddenKeys.value = nextHidden;
    shownKeys.value = nextShown;
    persistSettings();
  }

  function resetColumns(): void {
    hiddenKeys.value = new Set();
    // 恢复默认：默认隐藏列回到隐藏态（清空「显式开启」记录）
    shownKeys.value = new Set();
    customOrder.value = [];
    persistSettings();
  }

  function applyOrder(orderedKeys: string[]): void {
    customOrder.value = orderedKeys;
    persistSettings();
  }

  return {
    hideableColumns,
    groupedHideableColumns,
    visibleColumns,
    isHidden,
    toggleColumn,
    resetColumns,
    applyOrder
  };
}
