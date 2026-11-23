// 同类优选页的状态、派生与取数（#980 拆分自 index.vue）。
//
// 只做「页面在算什么」：类型目录、当前指标与方向、榜单行、诚实降级用的剔除数 /
// 口径版本 / 样本区间。渲染结构在 ../components/FundRankingTable.vue，
// 列定义在 ../rankingColumns.ts；本文件不出现任何 DOM 或样式。
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import {
  getFundRiskRanking,
  getFundRiskTypes,
  type FundRiskRankingRow,
  type FundRiskTypeOption
} from "@/api/products";
import { DASH } from "../rankingCells";
import type { RankingColumn } from "../rankingColumns";

export interface UseFundRankingOptions {
  /** 列定义：排序说明文案与首击方向都读它 */
  tableColumns: RankingColumn[];
}

export function useFundRanking(options: UseFundRankingOptions) {
  const { tableColumns } = options;
  const router = useRouter();

  const initialLoading = ref(true);
  const typesLoading = ref(false);
  const rankingLoading = ref(false);
  const typeOptions = ref<FundRiskTypeOption[]>([]);
  const selectedTypeId = ref<number | null>(null);
  const metric = ref<string>("sharpe");
  // 类型收在这里：模板里写 `order as 'asc' | 'desc'` 会被 vue 解析器
  // 当成已废弃的 filter 语法（vue/no-deprecated-filter），断言不该出现在模板里
  const order = ref<"asc" | "desc">("desc");
  const rows = ref<FundRiskRankingRow[]>([]);
  const excludedDistorted = ref(0);
  const caliberVersion = ref<number | null>(null);
  const metricGuideOpen = ref<string[]>([]);

  // 卡片标题不再承载「当前类型」：类型由筛选带上的分段控制器自述（选中项 + 只数），
  // 旧标题「混合型 · 同类优选」于是成了同一句话的第三遍（#3215 撤掉）。
  const rankingInfo = computed(() => {
    const label =
      tableColumns.find(c => c.key === metric.value)?.label ?? metric.value;
    // 沿用旧分段控件的用户语言：desc = 从优到劣（最大回撤以负数存储，降序即回撤浅者前）
    return `按「${label}」${order.value === "desc" ? "从优到劣" : "从劣到优"}排序；点击表头可切换指标与方向，悬停表头看指标解释`;
  });
  const excludedTip = computed(
    () =>
      `另有 ${excludedDistorted.value} 只因口径可疑（净值跳变 / 样本不足）被剔除，未进入本榜——它们算出来的值可能异常突出，但那是数据问题不是业绩。`
  );
  const noRowHint = computed(() =>
    excludedDistorted.value > 0
      ? "该类型下所有基金的指标都因口径可疑被剔除——数据问题，不是没有基金。"
      : "该类型下暂时没有可上榜的数据。"
  );
  // 指标窗口 / 数据截至（2026-10-17 第二轮）：原「窗口」列每行同值（快照全是
  // 近3年），是纯噪音——删列，信息移到这里随脚注讲清口径。
  const windowLabel = computed(() => rows.value[0]?.window_label ?? "—");
  const asOfDate = computed(
    () => (rows.value[0]?.as_of ?? "").slice(0, 10) || "—"
  );
  const sampleRange = computed(() => {
    if (!rows.value.length) return DASH;
    const values = rows.value.map(r => r.sample_points).filter(v => v != null);
    if (!values.length) return DASH;
    const min = Math.min(...values);
    const max = Math.max(...values);
    return min === max ? `${min}` : `${min}~${max}`;
  });

  async function loadTypes() {
    typesLoading.value = true;
    try {
      const res = await getFundRiskTypes();
      typeOptions.value = res?.data?.types ?? [];
      // 默认选中只数最多的那一类（typeOptions 已按 count 降序）
      if (typeOptions.value.length && selectedTypeId.value == null) {
        selectedTypeId.value = typeOptions.value[0].fund_type_id;
      }
    } catch {
      typeOptions.value = [];
    } finally {
      typesLoading.value = false;
    }
  }

  /** 请求序号：连续快速点击表头会并发多次请求，过期响应直接丢弃，防止旧数据覆盖新排序 */
  let loadSeq = 0;

  async function loadRanking() {
    if (selectedTypeId.value == null) return;
    const seq = ++loadSeq;
    rankingLoading.value = true;
    try {
      const res = await getFundRiskRanking({
        fund_type_id: selectedTypeId.value,
        metric: metric.value,
        order: order.value
      });
      if (seq !== loadSeq) return;
      const data = res?.data;
      rows.value = data?.rows ?? [];
      excludedDistorted.value = data?.excluded_distorted ?? 0;
      caliberVersion.value = data?.caliber_version ?? null;
    } catch {
      if (seq !== loadSeq) return;
      rows.value = [];
      excludedDistorted.value = 0;
    } finally {
      if (seq === loadSeq) rankingLoading.value = false;
    }
  }

  function onTypeChange() {
    loadRanking();
  }

  /** 表头排序（#3200 迁 el-table 后方向由表格上抛）：
   *  首击方向仍守「该列语义方向」（high ⇒ desc；low ⇒ asc），但决定权已交给
   *  FundRankingTable 的 sort-orders——el-table 算好的档位就是唯一真相，这里再按
   *  dir 推一遍必然与表格内部状态漂移（箭头与请求方向打架）。本函数只写回状态。 */
  function onSort(payload: { key: string; order: "asc" | "desc" }) {
    metric.value = payload.key;
    order.value = payload.order;
    loadRanking();
  }

  function goDetail(code: string) {
    router.push(`/fund/${code}`);
  }

  onMounted(async () => {
    try {
      await loadTypes();
      await loadRanking();
    } finally {
      initialLoading.value = false;
    }
  });

  return {
    // 状态
    initialLoading,
    typesLoading,
    rankingLoading,
    typeOptions,
    selectedTypeId,
    metric,
    order,
    rows,
    excludedDistorted,
    caliberVersion,
    metricGuideOpen,
    // 派生（文案与脚注）
    rankingInfo,
    excludedTip,
    noRowHint,
    windowLabel,
    asOfDate,
    sampleRange,
    // 行为
    onTypeChange,
    onSort,
    goDetail
  };
}
