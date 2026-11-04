/**
 * 自选表格列显隐 + 顺序偏好（issue #993 / #992；跨设备同步 #1337 方案 B）
 *
 * 职责：维护「哪些列被用户隐藏」与「可拖拽列的自定义顺序」。
 * 双层持久化（#1337）：本机 localforage（IndexedDB 优先，降级 localStorage）
 * + 云端 user_preferences（按 user_id 私有，换设备/换浏览器不丢）。
 *
 * 设计要点：
 * - 模块级单例状态：自选页 index.vue 与 SettingsDrawer 共享同一份，
 *   抽屉内勾选即时反映到表格，无需事件往返；
 * - 只持久化「被隐藏的列 key」+「可拖拽列的顺序」，而非全量配置：
 *   新增列默认可见且落在默认位置，避免老用户升级后新列被旧缓存吃掉；
 * - 顺序只记录 draggable=true 的中段列：固定列（marker/product 左固定、
 *   actions 右固定）不参与拖拽，重建时按默认定义归位；
 * - 合并策略「最近修改时间取胜」（pickNewer，可单测纯函数）：
 *   首屏先应用本地缓存不等网络，云端拉取后按 updated_at 择新单向收敛；
 *   云端不可达/未登录一律静默回退本地（本地缓存永远兜底）。
 */
import { computed, ref, type ComputedRef, type Ref } from "vue";
import { localForage } from "@/utils/localforage";
import { getUserPreference, putUserPreference } from "@/api/userPreference";
import {
  pickNewer,
  stripStamp,
  type ColumnSettings,
  type PrefStamp
} from "@/composables/watchlistColumnPrefs";
import {
  watchlistColumnDefs,
  type ColumnDef,
  type ColumnGroup
} from "@/views/asset/watchlist/columnDefs";
// 列序重建算法（纯函数，含「部分顺序不可当全量用」的推导与回归判据）
import { rebuildColumnOrder } from "@/views/asset/watchlist/columnOrder";
// 分组口径（通用组按 group 归属收列，与 scope 无关）与判据都在该纯模块内
import { buildColumnGroups } from "@/views/asset/watchlist/columnGroups";

const STORAGE_KEY = "watchlist-column-settings";

/** 模块级单例：页面与抽屉共享同一份状态 */
const hiddenKeys = ref<Set<string>>(new Set());
/** 默认隐藏、但被用户显式开启过的列（#993 新增列的默认关闭语义） */
const shownKeys = ref<Set<string>>(new Set());
const customOrder = ref<string[]>([]);
let loadStarted = false;

/** 把一份设置应用到内存状态（本地缓存与云端拉取共用） */
function applySettings(saved: ColumnSettings): void {
  if (Array.isArray(saved.hidden)) {
    hiddenKeys.value = new Set(saved.hidden);
  }
  if (Array.isArray(saved.shown)) {
    shownKeys.value = new Set(saved.shown);
  }
  if (Array.isArray(saved.order)) {
    // 只保留仍存在于当前定义中的 key（定义删列后旧缓存不产生幽灵顺序）
    const known = new Set(
      watchlistColumnDefs.filter(d => d.draggable).map(d => d.key)
    );
    customOrder.value = saved.order.filter(k => known.has(k));
  }
}

/** 本地时钟打点（ms）：updated_at 是本地合并策略的比较依据 */
function stampLocal(settings: ColumnSettings): ColumnSettings {
  return { ...settings, updated_at: Date.now() };
}

/** 读本地缓存（不应用，供合并比较）；无值/损坏返回 null */
async function readLocal(): Promise<PrefStamp | null> {
  try {
    const saved = await localForage().getItem<ColumnSettings>(STORAGE_KEY);
    if (saved && Array.isArray(saved.hidden)) {
      return { settings: saved, ts: saved.updated_at ?? 0 };
    }
  } catch {
    /* 读取失败按无偏好处理 */
  }
  return null;
}

/** 上云（fire-and-forget）：剥离本地时钟字段，服务端维护 updated_at */
function pushCloud(settings: ColumnSettings): void {
  putUserPreference(STORAGE_KEY, stripStamp(settings)).catch(() => {
    /* 云端不可达/未登录不影响会话内生效（本地已写） */
  });
}

/** 启动时恢复本地偏好并拉云端合并；失败静默回退默认（缓存损坏不应锁死表格） */
async function loadSettings(): Promise<void> {
  const local = await readLocal();
  if (local) applySettings(local.settings);
  try {
    const res = await getUserPreference<ColumnSettings>(STORAGE_KEY);
    const cloud = res?.data;
    if (!cloud) {
      // 云端无值：本地有则回传一次（首访上云）；没有则维持默认
      if (local) pushCloud(local.settings);
      return;
    }
    const cloudStamp: PrefStamp = {
      settings: cloud.value,
      ts: cloud.updated_at ? Date.parse(cloud.updated_at) : 0
    };
    const winner = pickNewer(local, cloudStamp);
    if (!winner) return;
    applySettings(winner.settings);
    if (winner === cloudStamp) {
      // 云端更新：落到本地（带上云端时间戳，保证下次合并可比）
      localForage()
        .setItem<ColumnSettings>(STORAGE_KEY, {
          ...winner.settings,
          updated_at: cloudStamp.ts
        })
        .catch(() => {
          /* 本地写失败不阻塞 */
        });
    } else if (local && cloudStamp.ts !== local.ts) {
      // 本地更新：回传云端（单向收敛一次，不做同步环）
      pushCloud(local.settings);
    }
  } catch {
    /* 未登录（401）/网络失败：本地配置照常生效 */
  }
}

function persistSettings(): void {
  const settings: ColumnSettings = {
    hidden: [...hiddenKeys.value],
    shown: [...shownKeys.value],
    order: [...customOrder.value]
  };
  const stamped = stampLocal(settings);
  localForage()
    .setItem<ColumnSettings>(STORAGE_KEY, stamped)
    .catch(() => {
      /* 持久化失败不影响会话内生效（IndexedDB 不可用时降级由库内部处理） */
    });
  pushCloud(stamped);
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
   * 按「品类视图」分组（设置面板「表格列显示」分导航渲染，2026-09-12 修订）：
   * 每个非「通用」视图 = 通用列 + 该品类专属列合并呈现，让用户在「基金」视图下
   * 一屏配齐基金相关的所有列，不必跨两个分组跳。通用列因同一 key 共享，跨视图显隐
   * 状态天然同步；UI 以配色区分「通用/专属」。无列的组剔除，避免空标题。
   *
   * ⚠️ 通用列**只能按 `COLUMN_GROUP_MAP` 的归类取**，不能按 `scope === "mixed"` 取：
   * 后者会让 scope=category 但语义属通用的列（#2650 的 `trend`）在设置面板里消失。
   * 口径与回归判据见 `views/asset/watchlist/columnGroups.ts` 与其单测。
   */
  const groupedHideableColumns = computed(() =>
    buildColumnGroups(hideableColumns.value)
  );

  /**
   * 全量列按自定义顺序重排：非拖拽列（固定列/内置列）保持默认锚点位置，
   * 拖拽列按保存顺序依次填入原拖拽区槽位——固定列左右包夹的布局不被破坏。
   *
   * ⚠️ 重建算法必须由 `rebuildColumnOrder` 负责（2026-10-30）：持久化的 `order`
   * 只含「当时可见」的列（7~8 个），而可拖拽槽位约 50 个。曾在此就地实现「按槽位
   * shift、队列空则保留原位」，于是同一列既占了别人的槽位、又留在自己的原生槽位，
   * 表头整段重复（走势/持有数量/持仓市值/持仓收益 各两遍）。详见 columnOrder.ts。
   */
  const orderedColumns = computed(() =>
    rebuildColumnOrder(watchlistColumnDefs, customOrder.value)
  );

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
