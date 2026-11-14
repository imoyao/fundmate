/**
 * 图表周期筛选的唯一真相源（组合 / 账户页所有「按时间取数」的曲线共用）。
 *
 * ## 为什么抽出来
 *
 * 同一个页面上的三块曲线各自定义过一份「区间」：超额走势写死近 90 天、
 * 资金流动是 180 / 365 / 1095 三个数字、收益归因是 1m / 3m / ytd / 1y / all。
 * 于是同一个「近1年」在三处能落在不同起点，用户无法横向对照；补一档要改三处，
 * 必然漂移。这里把「档位 → 起止日」定成一份，控件形态见 `ChartRangeTabs`。
 *
 * ## 口径纪律
 *
 * - `end_date` 恒为今日，取**本地**日期（不走 `toISOString`，UTC 偏移会把区间挪一天）；
 * - 「成立来」不在前端算起点，发 `start_date=inception` **哨兵**由后端按作用域解析
 *   最早一笔资金流水（`services/scope.py::first_investment_date`）。前端此刻并不知道
 *   `first_txn_date`，「先取一次再发第二次」既多一轮请求（冷启动鸡生蛋），
 *   也会让两次请求的区间口径各算一遍而漂移；
 * - 月 / 年回退用 dayjs（月末夹取到当月最后一天）。原生 `Date.setMonth` 会把
 *   3-31 减一月溢出成 3-03，那是错的起点；
 * - 档位给的是**请求**区间。数据本身不够长时，由调用方用响应里的实际区间提示
 *   （见 `excessCaptionOf` / `rangeCaptionOf`），不改档位标签——「近5年」在只有
 *   一年数据的组合上仍是用户点的那个意思，只是备注「数据自 X 起」。
 */
import dayjs from "dayjs";

/** 九档周期。值即前后端约定的区间键（不含数字天数，避免「90 天」这种口径散落） */
export type ChartRangeKey =
  "1m" | "3m" | "6m" | "1y" | "2y" | "3y" | "5y" | "ytd" | "inception";

/** 中文标签（控件文案与图表说明共用同一份，禁止在组件里再写一遍） */
export const CHART_RANGE_LABELS: Record<ChartRangeKey, string> = {
  "1m": "近1月",
  "3m": "近3月",
  "6m": "近6月",
  "1y": "近1年",
  "2y": "近2年",
  "3y": "近3年",
  "5y": "近5年",
  ytd: "今年来",
  inception: "成立来"
};

/** 第一排常驻档（4 档，超出就走「更多」，避免一行塞满挤掉标题） */
export const PRIMARY_CHART_RANGE_KEYS = ["1m", "3m", "6m", "1y"] as const;

/** 「更多」下拉里的档；顺序与产品截图一致（近2年 → 近5年 → 今年来 → 成立来） */
export const MORE_CHART_RANGE_KEYS = [
  "2y",
  "3y",
  "5y",
  "ytd",
  "inception"
] as const;

/** 全部档位（第一排 + 更多），供「是否合法档位」与遍历使用 */
export const ALL_CHART_RANGE_KEYS: readonly ChartRangeKey[] = [
  ...PRIMARY_CHART_RANGE_KEYS,
  ...MORE_CHART_RANGE_KEYS
];

/** 「成立来」哨兵：起点交后端按作用域解析（与 `services/scope.py::INCEPTION` 同值） */
export const CHART_RANGE_INCEPTION = "inception";

/** 固定回退月数（不含 ytd / inception，二者另有算法） */
const MONTHS_BACK: Record<string, number> = {
  "1m": 1,
  "3m": 3,
  "6m": 6,
  "1y": 12,
  "2y": 24,
  "3y": 36,
  "5y": 60
};

export type ChartRangeParams = { start_date: string; end_date: string };

/** 档位 → 中文标签（未知档位原样回显，便于定位调错） */
export function chartRangeLabel(key: ChartRangeKey): string {
  return CHART_RANGE_LABELS[key] ?? key;
}

/**
 * 档位 → 请求参数（闭区间，`YYYY-MM-DD`）。
 *
 * `now` 可注入只为让单测不依赖系统时钟；生产路径永远走默认值。
 */
export function chartRangeParams(
  key: ChartRangeKey,
  now: dayjs.Dayjs = dayjs()
): ChartRangeParams {
  const end = now.format("YYYY-MM-DD");
  if (key === CHART_RANGE_INCEPTION) {
    return { start_date: CHART_RANGE_INCEPTION, end_date: end };
  }
  if (key === "ytd") {
    return {
      start_date: now.startOf("year").format("YYYY-MM-DD"),
      end_date: end
    };
  }
  const months = MONTHS_BACK[key] ?? 0;
  return {
    start_date: now.subtract(months, "month").format("YYYY-MM-DD"),
    end_date: end
  };
}

/**
 * 在给定档位集合里挑出可用的：请求起点早于作用域最早数据日的档不收。
 *
 * 例：组合 2025-06 才建仓，「近5年」与「成立来」画出来是**同一条线**，
 * 留着两个按钮等于让用户点两次拿到同一张图（假可操作性）。`inception` 恒保留。
 *
 * `earliest` 为空（起点未知 / 后端未给）时**不过滤**——不知道就别猜，
 * 少一档比多一档可疑更糟。
 */
export function availableRangeKeys(
  keys: readonly ChartRangeKey[],
  earliest: string | null | undefined,
  now: dayjs.Dayjs = dayjs()
): ChartRangeKey[] {
  if (!earliest) return [...keys];
  const first = dayjs(earliest);
  if (!first.isValid()) return [...keys];
  return keys.filter(key => {
    if (key === CHART_RANGE_INCEPTION) return true;
    const { start_date } = chartRangeParams(key, now);
    // 起点不早于最早数据日 ⇒ 这档被数据完整覆盖（含相等：建仓当天即区间首日）
    return !dayjs(start_date).isBefore(first, "day");
  });
}
