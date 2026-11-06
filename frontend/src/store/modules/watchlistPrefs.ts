// frontend/src/store/modules/watchlistPrefs.ts
import { defineStore } from "pinia";
import { ref } from "vue";
import { localForage } from "@/utils/localforage";
import {
  DEFAULT_SORT_METRIC,
  normalizeSortMetric,
  type SortMetric
} from "@/views/asset/watchlist/sortMetric";

/**
 * 自选页的「本地视图偏好」store（#2922，从 `useWatchlistData` 下沉）。
 *
 * ## 为什么必须是 store，而不是「把 ref 挪到另一个文件」
 *
 * 这两项偏好是**跨挂载点共享**的：自选页表格与设置抽屉同时读写同一份，改一处
 * 另一处必须立刻跟着变（每页条数改完分页器就得换档；表头切口径后整组排序要重算）。
 * 原先它们以**模块级单例**（`const pageSize = ref(...)` 写在 composable 文件顶层）
 * 的形式存在——这在运行时确实做到了单例，但代价是：
 * 1. 状态**不在任何显式容器里**：读 `useWatchlistData` 的返回对象看不出它跨挂载
 *    共享（返回值里混着「本次调用的私有状态」与「全应用唯一的状态」两类东西）；
 * 2. **无法重置**：测试之间只能靠「让多个用例共用同一份残留状态」或改模块内部实现，
 *    写成装饰性断言（本仓多次踩过「怎么都绿」）；
 * 3. 谁改了它无从追踪（无 devtools 可见性）。
 *
 * 故按 #2922 卡面「先分清跨页共享 / 单页派生，只有前者适合进 store」的裁决，把
 * **仅这两项**下沉；列表数据 / 分页游标 / 排序方向等仍是单页派生，留在 composable。
 *
 * ## 持久化口径不变（纯本地，不上云）
 *
 * 存 `localforage`（IndexedDB 不可用时库内降级 localStorage）。跨设备同步依赖后端
 * `user_preferences` 基建，本期不做（与 #1335 的裁决一致）：它是「我怎么看这张表」
 * 的偏好，云同步的价值低于实现成本。
 */

/** 每页条数可选档位（issue #1335）：与后端 per_page 限幅 [1,200] 对齐，不超出范围 */
export const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 20;

const PAGE_SIZE_STORAGE_KEY = "watchlist-page-size";
/** 复合列的排序口径（按列 key 记忆，见 sortMetric.ts） */
const SORT_METRICS_STORAGE_KEY = "watchlist-sort-metrics";
/** 首版的单值键（只存当日盈亏，取值 amount/pct）：读一次做迁移，之后不再写 */
const LEGACY_DAY_PNL_METRIC_STORAGE_KEY = "watchlist-day-pnl-metric";

export const useWatchlistPrefsStore = defineStore("watchlist-prefs", () => {
  /** 每页条数（自选页分页器与设置抽屉共享） */
  const pageSize = ref(DEFAULT_PAGE_SIZE);

  /**
   * 复合列的排序口径（按列 key 记忆）。
   *
   * 三个复合列各有各的两行数（今日估算：金额/涨幅；持仓市值：金额/占比；
   * 持仓收益：金额/收益率），故记的是 `{ [列 key]: SortMetric }` 而不是单个值——
   * 首版只服务当日盈亏（单值 ref），扩到三列后必须按列存，否则切一列会把
   * 另一列的口径一起改掉。
   */
  const sortMetrics = ref<Record<string, SortMetric>>({});

  // 记忆化「加载本地每页条数」Promise：多个挂载点（自选页 + 设置抽屉）并发调用
  // initPageSize 时共享同一次加载，避免第二个挂载点在首个 await 完成前即返回、
  // 用默认 20 发起首屏请求，随后被记忆值（如 50）覆盖导致「数据按 20 拉取、
  // 分页器按 50 显示」的短暂不一致。
  let pageSizeLoadPromise: Promise<void> | null = null;
  let sortMetricsLoadStarted = false;

  async function loadPageSize(): Promise<void> {
    try {
      const saved = await localForage().getItem<number>(PAGE_SIZE_STORAGE_KEY);
      if (
        typeof saved === "number" &&
        (PAGE_SIZE_OPTIONS as readonly number[]).includes(saved)
      ) {
        pageSize.value = saved;
      }
    } catch {
      /* 读取失败按默认处理 */
    }
  }

  function persistPageSize(): void {
    localForage()
      .setItem<number>(PAGE_SIZE_STORAGE_KEY, pageSize.value)
      .catch(() => {
        /* 持久化失败不影响会话内生效（IndexedDB 不可用时库内部降级 localStorage） */
      });
  }

  /**
   * 首屏前加载本地每页条数偏好（#1335），确保第一次 fetch 即使用已记忆的档位。
   * 幂等：返回记忆化的加载 Promise，所有调用方等待同一次加载完成。
   */
  async function initPageSize(): Promise<void> {
    if (!pageSizeLoadPromise) {
      pageSizeLoadPromise = loadPageSize();
    }
    return pageSizeLoadPromise;
  }

  /**
   * 切换每页条数（#1335）：仅接受预定义档位，越界值回退默认，
   * 避免与后端 per_page 限幅 [1,200] 冲突。
   *
   * @returns 是否真的变了——未变时调用方**不应**重置分页/重取（保持既有语义：
   *          重复点同一档位不发请求）。
   */
  function changePageSize(size: number): boolean {
    const allowed = PAGE_SIZE_OPTIONS as readonly number[];
    const next = allowed.includes(size) ? size : DEFAULT_PAGE_SIZE;
    if (next === pageSize.value) return false;
    pageSize.value = next;
    persistPageSize();
    return true;
  }

  async function loadSortMetrics(): Promise<void> {
    if (sortMetricsLoadStarted) return;
    sortMetricsLoadStarted = true;
    try {
      const saved = await localForage().getItem<Record<string, unknown>>(
        SORT_METRICS_STORAGE_KEY
      );
      const next: Record<string, SortMetric> = {};
      if (saved && typeof saved === "object") {
        for (const [key, raw] of Object.entries(saved)) {
          const metric = normalizeSortMetric(raw);
          if (metric) next[key] = metric;
        }
      }
      // 迁移：老用户存过「按涨幅排序」，不读旧键会静默回落成「按金额」
      if (!next.day_pnl) {
        const legacy = await localForage().getItem<unknown>(
          LEGACY_DAY_PNL_METRIC_STORAGE_KEY
        );
        const migrated = normalizeSortMetric(legacy);
        if (migrated) next.day_pnl = migrated;
      }
      sortMetrics.value = next;
    } catch {
      /* 读取失败按默认（金额，与列主行一致） */
    }
  }

  /** 取某列的当前口径；未存过 → 金额（与列主行一致） */
  function sortMetricOf(key: string): SortMetric {
    return sortMetrics.value[key] ?? DEFAULT_SORT_METRIC;
  }

  /** 设置某列口径：换新对象而不是改属性——引用变化让读它的 computed（整组排序）稳定重算 */
  function setSortMetric(key: string, metric: SortMetric): void {
    if (sortMetricOf(key) === metric) return;
    sortMetrics.value = { ...sortMetrics.value, [key]: metric };
    localForage()
      .setItem(SORT_METRICS_STORAGE_KEY, sortMetrics.value)
      .catch(() => {
        /* 持久化失败不影响本次会话 */
      });
  }

  return {
    pageSize,
    sortMetrics,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    initPageSize,
    changePageSize,
    loadSortMetrics,
    sortMetricOf,
    setSortMetric
  };
});
