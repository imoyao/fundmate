/**
 * 「深度」档的行业 / 赛道排行数据层（#1431 / #1731 / #980）。
 *
 * 三张表（申万行业拥挤度 / 热门赛道拥挤度 / 行业乖离率）来自同一个多指标接口，
 * 只有 `source` 与错误文案不同——原实现在组件里把同一段 18 行的 try/catch/finally
 * 抄了三遍。这里收成一个 `loadMultiItems`，状态用 ref 组合传入。
 */
import { computed, ref, type Ref } from "vue";
import { getMultiItems } from "@/api/temperature";
import {
  CROWDING_HIGH_THRESHOLD,
  CROWDING_LOW_THRESHOLD
} from "@/constants/temperature";

/** 一级分类：申万行业（含乖离率）/ 热门赛道（外部临时源，无乖离率） */
export const RANK_CATEGORIES = [
  { key: "sw", label: "申万行业", source: "industry_crowding" },
  { key: "track", label: "热门赛道", source: "track_crowding" }
] as const;

export type RankCategoryKey = (typeof RANK_CATEGORIES)[number]["key"];

/** 二级视图：拥挤度 / 乖离率 */
export const RANK_VIEWS = [
  {
    key: "crowding",
    label: "拥挤度",
    info: {
      sw: "申万一级 31 个行业的历史分位：综合拥挤度、成交额占全A比例、换手率、60 日线上占比、60 日新高占比、融资买入占比、百万大单。越高越拥挤。",
      track:
        "18 个热门赛道（概念指数 + 申万细分，如 AI芯片 / 半导体设备 / 光通信）的历史分位，维度同行业视图；赛道维度无行业乖离率。"
    },
    staleTip:
      "数据暂未更新，当前为最近一次成功计算的结果或占位提示，非实时数据，仅供参考。"
  },
  {
    key: "bias",
    label: "乖离率",
    info: {
      sw: "LOGBIAS = (ln(收盘) − EMA20(ln(收盘))) × 100：正 = 位于均线上方（偏热），负 = 下方（偏冷）；档位阈值 ±15 / ±5。",
      track: "赛道维度不提供行业乖离率（该口径仅申万一级行业适用）。"
    },
    staleTip:
      "行情数据暂未更新，当前乖离率基于最近一次成功抓取的价格计算，非实时数据，仅供参考。"
  }
] as const;

export type RankViewKey = (typeof RANK_VIEWS)[number]["key"];

/** 分位色标图例：阈值与 crowdingColorClass 同源，避免文案与实现不一致 */
export const RANK_LEGEND = [
  {
    label: `低迷 <${CROWDING_LOW_THRESHOLD}`,
    dotClass: "rank-legend__dot--low"
  },
  {
    label: `中性 ${CROWDING_LOW_THRESHOLD}–${CROWDING_HIGH_THRESHOLD}`,
    dotClass: "rank-legend__dot--mid"
  },
  {
    label: `过热 >${CROWDING_HIGH_THRESHOLD}`,
    dotClass: "rank-legend__dot--high"
  }
];

interface TableState {
  items: Ref<any[]>;
  date: Ref<string>;
  stale: Ref<boolean>;
  loading: Ref<boolean>;
}

/**
 * 取一组多指标数据。
 *
 * 注意 `else` 分支**只清 items / stale、不清 date**：这是既有行为（数据为空时日期
 * 保留上一次的值），改成清空会让标题行的「更新：」闪成「暂无」。
 */
async function loadMultiItems(
  source: string,
  errorLabel: string,
  state: TableState
) {
  state.loading.value = true;
  try {
    const res = await getMultiItems(source);
    const data = res.data;
    if (data && data.items) {
      state.items.value = data.items;
      state.date.value = data.date || "";
      state.stale.value =
        Boolean(data.stale) || (data.items || []).some((i: any) => i.stale);
    } else {
      state.items.value = [];
      state.stale.value = false;
    }
  } catch (e) {
    console.error(errorLabel, e);
    state.items.value = [];
    state.date.value = "";
    state.stale.value = false;
  } finally {
    state.loading.value = false;
  }
}

export function useRankTables() {
  // 行业拥挤度（独立维度：行业 PB / 全A 中位 PB 历史百分位）
  const crowdingItems = ref<any[]>([]);
  const crowdingDate = ref<string>("");
  const crowdingStale = ref(false);
  const crowdingLoading = ref(false);

  // 热门赛道拥挤度（外部临时源 category=track，18 条；该维度无行业乖离率）
  const trackItems = ref<any[]>([]);
  const trackDate = ref<string>("");
  const trackStale = ref(false);
  const trackLoading = ref(false);

  // 行业乖离率（仅申万一级行业适用）
  const biasItems = ref<any[]>([]);
  const biasDate = ref<string>("");
  const biasStale = ref(false);
  const biasLoading = ref(false);

  const rankCategory = ref<RankCategoryKey>("sw");
  const rankView = ref<RankViewKey>("crowding");

  /** 切换分类：赛道无乖离率 → 自动回到拥挤度视图，避免停在空视图 */
  function switchCategory(key: RankCategoryKey) {
    rankCategory.value = key;
    if (key === "track") rankView.value = "crowding";
  }

  /** 切换排行视图（原为模板内联 `rankView = view.key`，抽成具名函数以便类型收窄） */
  function onRankViewChange(key: RankViewKey) {
    rankView.value = key;
  }

  /** 当前分类下可用的视图（赛道仅拥挤度） */
  const availableRankViews = computed(() =>
    rankCategory.value === "track"
      ? RANK_VIEWS.filter(v => v.key === "crowding")
      : RANK_VIEWS
  );

  /**
   * 排行分类 / 视图的分段选项（#1731 收敛）。
   * 两个源常量都带额外字段（`source` / `info` / `staleTip`），只取 SegmentedControl 要的
   * `label` + `value`，避免把业务字段漏进展示层。
   */
  const rankCategoryOptions = RANK_CATEGORIES.map(c => ({
    label: c.label,
    value: c.key
  }));

  const rankViewOptions = computed(() =>
    availableRankViews.value.map(v => ({ label: v.label, value: v.key }))
  );

  /** 当前「分类 × 视图」对应的提示、更新时间与滞后状态（标题行统一展示） */
  const activeRankView = computed(() => {
    const view =
      RANK_VIEWS.find(v => v.key === rankView.value) ?? RANK_VIEWS[0];
    const isCrowding = rankView.value === "crowding";
    const isTrack = rankCategory.value === "track";
    return {
      info: view.info[rankCategory.value],
      staleTip: view.staleTip,
      date: isCrowding
        ? isTrack
          ? trackDate.value
          : crowdingDate.value
        : biasDate.value,
      stale: isCrowding
        ? isTrack
          ? trackStale.value
          : crowdingStale.value
        : biasStale.value
    };
  });

  // 过滤整组标灰占位（item_code === '__NA__'），仅展示有效行业
  const crowdingValidItems = computed(() =>
    (crowdingItems.value || []).filter((i: any) => i.item_code !== "__NA__")
  );

  // 赛道同理（外部源关停时该 source 可能整组无数据）
  const trackValidItems = computed(() =>
    (trackItems.value || []).filter((i: any) => i.item_code !== "__NA__")
  );

  /** 当前分类下的拥挤度条目（行业 / 赛道共用同一张表） */
  const activeCrowdingItems = computed(() =>
    rankCategory.value === "track"
      ? trackValidItems.value
      : crowdingValidItems.value
  );

  const activeCrowdingLoading = computed(() =>
    rankCategory.value === "track" ? trackLoading.value : crowdingLoading.value
  );

  const fetchBias = () =>
    loadMultiItems("bias", "获取乖离率数据失败:", {
      items: biasItems,
      date: biasDate,
      stale: biasStale,
      loading: biasLoading
    });

  const fetchCrowding = () =>
    loadMultiItems("industry_crowding", "获取行业拥挤度数据失败:", {
      items: crowdingItems,
      date: crowdingDate,
      stale: crowdingStale,
      loading: crowdingLoading
    });

  // 热门赛道（外部临时源 category=track）：失败静默为空，赛道视图显示空态提示，不影响行业视图
  const fetchTrack = () =>
    loadMultiItems("track_crowding", "获取赛道拥挤度数据失败:", {
      items: trackItems,
      date: trackDate,
      stale: trackStale,
      loading: trackLoading
    });

  /** 三张表并发取数（#1546 T2.1：原为串行 await，首尾相接） */
  function fetchRankTables() {
    return Promise.all([fetchBias(), fetchCrowding(), fetchTrack()]);
  }

  return {
    rankCategory,
    rankView,
    rankCategoryOptions,
    rankViewOptions,
    activeRankView,
    activeCrowdingItems,
    activeCrowdingLoading,
    biasItems,
    biasLoading,
    switchCategory,
    onRankViewChange,
    fetchRankTables
  };
}
