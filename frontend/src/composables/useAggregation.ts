import { computed, ref, watch } from "vue";
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

  const result = ref<AggregationResult | null>(null);
  const loading = ref(false);
  const errorMsg = ref("");

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
    try {
      const res = await fetcher({
        dimension: dimension.value,
        sort: sort.value,
        order: order.value,
        page: page.value,
        page_size: pageSize.value
      });
      result.value = (res?.data as AggregationResult) ?? null;
    } catch (e: any) {
      errorMsg.value = e?.message || "加载失败";
      result.value = null;
    } finally {
      loading.value = false;
    }
  }

  /** 切换维度：回到第一页，避免停留在越界页码上出现空列表 */
  function setDimension(next: AggregationDimension) {
    if (dimension.value === next) return;
    dimension.value = next;
    page.value = 1;
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
  }

  function setPage(next: number) {
    page.value = next;
  }

  // 维度/排序/页码变化即重新取数：后端已支持这些参数，前端不做本地切片
  watch([dimension, sort, order, page, pageSize], load);

  return {
    dimension,
    sort,
    order,
    page,
    pageSize,
    result,
    loading,
    errorMsg,
    totalYuan,
    snapshotDate,
    snapshotDateLatest,
    hasSnapshotGap,
    productGroups,
    institutionGroups,
    total,
    totalPages,
    load,
    setDimension,
    setSort,
    setPage
  };
}
