import { computed, ref } from "vue";
import type {
  AggregationDimension,
  AggregationInstitutionGroup,
  AggregationProductGroup,
  AggregationQuery,
  AggregationResult,
  AggregationSort
} from "@/api/ledger";

/**
 * 聚合视图取数器：入参为聚合查询参数，返回含 `data` 的响应。
 * 由调用方注入（场外基金 / 场内证券各传自己的 API 函数），
 * 使本 composable 与具体品类解耦。
 */
export type AggregationFetcher = (
  params: AggregationQuery
) => Promise<{ data?: AggregationResult | null } | any>;

export interface UseAggregationOptions {
  /** 默认每页条数 */
  pageSize?: number;
  /** 类型 Tab 筛选字段：'fund_type'（基金，默认）/ 'asset_type'（证券） */
  typeFilterField?: "fund_type" | "asset_type";
}

/**
 * 持仓聚合视图的取数与交互状态（#1101 场外基金 / #1132 场内证券 共用）。

 * 收敛两品类下钻页完全相同的逻辑：维度切换、排序、分页、加载与错误态，
 * 以及「数据日期」语义（最早快照日 = 最滞后的一笔，对外展示最诚实）。

 * 页面主文件只做编排，符合 docs/spec/frontend-ui.md §3 的页面规模规范。
 */
export function useAggregation(
  fetcher: AggregationFetcher,
  options: UseAggregationOptions = {}
) {
  const dimension = ref<AggregationDimension>("product");
  const sort = ref<AggregationSort>("market_value");
  const order = ref<"asc" | "desc">("desc");
  const page = ref(1);
  const pageSize = ref(options.pageSize ?? 20);
  /** 名称/代码模糊搜索词（防抖触发请求） */
  const keyword = ref("");
  /** 基金小类名筛选；''=全部，'__none__'=未分类 */
  const fundType = ref("");

  const result = ref<AggregationResult | null>(null);
  const loading = ref(false);
  const errorMsg = ref("");

  /**
   * 骨架屏显隐控制（#1133 一致性修复）。
   *
   * 规则极简且可预测：**只要 loading 就显示骨架屏**。
   *
   * 此前两版都有问题：
   * 1. 200ms 阈值版 —— 把 UI 反馈绑到不可控的后端耗时上，导致切维度时
   *    「product 有缓存不显示 / institution 要 join AMAC 名录显示了」，同一操作两种反馈；
   *    且快请求时会落入「四分支全不满足」的空白渲染区，白屏一闪。
   * 2. 阈值 + force 双轨版 —— 规则复杂，且首屏仍可能白屏。
   *
   * 现用「最小显示时长 300ms」替代阈值来消除闪烁：
   * - 请求 50ms  → 骨架屏仍停留 300ms，平滑过渡，不闪
   * - 请求 2000ms → 骨架屏停留 2000ms，如实反映进度
   * 无论后端快慢，用户看到的反馈始终一致。
   */
  const showSkeleton = ref(false);
  let skeletonTimer: ReturnType<typeof setTimeout> | null = null;
  let skeletonShownAt = 0;
  /** 最小显示时长（ms）：一旦显示骨架屏，至少停留这么久，避免快请求一闪而过 */
  const MIN_SKELETON_MS = 300;

  /** 请求开始前调用 */
  function scheduleSkeleton() {
    if (skeletonTimer) clearTimeout(skeletonTimer);
    skeletonTimer = null;
    showSkeleton.value = true;
    skeletonShownAt = Date.now();
  }

  /** 请求结束时调用：补足最小显示时长后隐藏 */
  function settleSkeleton() {
    if (skeletonTimer) clearTimeout(skeletonTimer);

    if (!showSkeleton.value) {
      skeletonTimer = null;
      return;
    }

    const elapsed = Date.now() - skeletonShownAt;
    const remaining = MIN_SKELETON_MS - elapsed;
    if (remaining > 0) {
      skeletonTimer = setTimeout(() => {
        showSkeleton.value = false;
        skeletonTimer = null;
      }, remaining);
    } else {
      showSkeleton.value = false;
      skeletonTimer = null;
    }
  }

  /** 汇总市值（元）：后端以「分」下发 */
  const totalYuan = computed(
    () => (result.value?.total_market_value_cents ?? 0) / 100
  );

  /** 数据日期 = 全部持仓中最早的快照日（最滞后的一笔） */
  const snapshotDate = computed(() => result.value?.snapshot_date ?? null);
  /** 最近的快照日；与最早值不等说明各账户数据存在时间差 */
  const snapshotDateLatest = computed(
    () => result.value?.snapshot_date_latest ?? null
  );
  const hasSnapshotGap = computed(
    () =>
      !!snapshotDate.value &&
      !!snapshotDateLatest.value &&
      snapshotDate.value !== snapshotDateLatest.value
  );
  /**
   * 🔄 净值日期（NavService 取到的最新净值日期）。
   * 与 snapshot_date（份额日期）可能分叉，前端可据此做双日期展示。
   */
  const navDate = computed(() => result.value?.nav_date ?? null);

  const productGroups = computed<AggregationProductGroup[]>(() =>
    dimension.value === "product"
      ? ((result.value?.groups as AggregationProductGroup[]) ?? [])
      : []
  );

  const institutionGroups = computed<AggregationInstitutionGroup[]>(() =>
    dimension.value === "institution"
      ? ((result.value?.groups as AggregationInstitutionGroup[]) ?? [])
      : []
  );

  /** 分组总数（分页前的全量条数） */
  const total = computed(() => result.value?.total ?? 0);
  const totalPages = computed(() => result.value?.total_pages ?? 1);

  async function load() {
    loading.value = true;
    errorMsg.value = "";
    scheduleSkeleton();
    try {
      const query: AggregationQuery = {
        dimension: dimension.value,
        sort: sort.value,
        order: order.value,
        page: page.value,
        page_size: pageSize.value,
        keyword: keyword.value.trim() || undefined
      };
      // 类型 Tab 按配置字段筛选：基金走 fund_type，证券走 asset_type（#1266 / #1264）
      if (options.typeFilterField === "asset_type") {
        query.asset_type = fundType.value || undefined;
      } else {
        query.fund_type = fundType.value || undefined;
      }
      const res = await fetcher(query);
      result.value = (res?.data as AggregationResult) ?? null;
    } catch (e: any) {
      // 技术错误映射为用户友好文案，不暴露原始信息
      const msg = String(e?.message ?? e ?? "");
      if (/timeout/i.test(msg)) {
        errorMsg.value = "请求超时，请稍后重试";
      } else if (/network|fetch|abort/i.test(msg)) {
        errorMsg.value = "网络连接异常，请检查网络后重试";
      } else if (/429|too many/i.test(msg)) {
        errorMsg.value = "请求过于频繁，请稍后再试";
      } else if (/401|403|unauthorized/i.test(msg)) {
        errorMsg.value = "登录已过期，请重新登录";
      } else if (/500|502|503|504/i.test(msg)) {
        errorMsg.value = "服务暂时不可用，请稍后重试";
      } else {
        errorMsg.value = "加载失败，请重试";
      }
      result.value = null;
    } finally {
      loading.value = false;
      settleSkeleton();
    }
  }

  /**
   * 切换维度：回到第一页，避免停留在越界页码上出现空列表。
   * 页面须通过本方法切换维度（而非直接 v-model 改 dimension），
   * 否则页码不会重置。
   */
  function setDimension(next: AggregationDimension) {
    if (dimension.value === next) return;
    dimension.value = next;
    page.value = 1;
    void load();
  }

  /** 点击同一字段反转升降序，切换字段则重置为降序 */
  function setSort(next: AggregationSort) {
    if (sort.value === next) {
      order.value = order.value === "desc" ? "asc" : "desc";
    } else {
      sort.value = next;
      order.value = "desc";
    }
    page.value = 1;
    void load();
  }

  function setPage(next: number) {
    if (page.value === next) return;
    page.value = next;
    void load();
  }

  /** 关键词搜索：300ms 防抖，避免逐字打请求 */
  let keywordTimer: ReturnType<typeof setTimeout> | null = null;
  function setKeyword(value: string) {
    keyword.value = value;
    if (keywordTimer) clearTimeout(keywordTimer);
    keywordTimer = setTimeout(() => {
      page.value = 1;
      void load();
    }, 300);
  }

  /** 切换基金类型筛选：立即生效并回到第一页 */
  function setFundType(value: string) {
    if (fundType.value === value) return;
    fundType.value = value;
    page.value = 1;
    void load();
  }

  return {
    dimension,
    sort,
    order,
    page,
    pageSize,
    keyword,
    fundType,
    result,
    loading,
    showSkeleton,
    errorMsg,
    totalYuan,
    snapshotDate,
    snapshotDateLatest,
    hasSnapshotGap,
    navDate,
    productGroups,
    institutionGroups,
    total,
    totalPages,
    load,
    setDimension,
    setSort,
    setPage,
    setKeyword,
    setFundType
  };
}
