/**
 * #871：收益率口径（XIRR / TWR / Modified Dietz）的共享状态与口径→字段映射。
 *
 * 两处消费：组合详情 `PortfolioReturnCard`、智能分析 `ReturnOverviewSection`
 * ——同选项、同语义、同降级规则。落 composables 而不是两页各抄一份：
 * 选项表 / 口径名改一处即全局生效，且「切换口径后旧数据未回来时不显示」
 * 这条规则只需实现一次（两页都栽过「把旧口径数字挂在新标签下」的坑）。
 *
 * 三种口径答三个不同的问题，不是同一个数字的三种算法：
 * - XIRR           年化、资金加权——「我这些年的持有体验」，受申赎时点影响；
 * - TWR            年化、时间加权——「组合本身表现」，剔除何时进钱，跨账户可比
 *                  （日因子连乘引擎，#2133；总资产口径，含现金等价物）；
 * - Modified Dietz 区间、不年化——「这一段贡献多少」。
 */
import { computed, ref, type Ref } from "vue";
import type { ReturnMethod, XirrData } from "@/api/performance";

/** 口径切换选项（两页逐字同款，#2153 同精神：开关同语义，数值才天然一致） */
export const RETURN_METHOD_OPTIONS: Array<{
  label: string;
  value: ReturnMethod;
}> = [
  { label: "年化", value: "xirr" },
  { label: "时间加权", value: "twr" },
  { label: "区间", value: "dietz" }
];

/** 口径全称（卡片标题 / tooltip 用） */
export const RETURN_METHOD_NAME: Record<ReturnMethod, string> = {
  xirr: "XIRR",
  twr: "TWR",
  dietz: "Modified Dietz"
};

/** 主指标标签词干（两页各自的前后缀不同，词干只有一份） */
export const RETURN_RATE_LABEL: Record<ReturnMethod, string> = {
  xirr: "年化收益率",
  twr: "时间加权年化",
  dietz: "区间收益率"
};

/** 口径说明 tooltip（组合详情卡片 info 用） */
export const RETURN_METHOD_TIP =
  "年化（XIRR）：资金加权，反映个人实际持有体验，受申赎时点影响；时间加权（TWR）：剔除申赎时点影响，跨账户/跨人可比；区间（Modified Dietz）：不年化的区间收益，看这一段贡献多少。";

/**
 * 收益率口径状态 + 口径→字段映射。
 *
 * @param data 当前收益率响应（随请求更新的 ref）
 */
export function useReturnMethod(data: Ref<XirrData | null>) {
  const returnMethod = ref<ReturnMethod>("xirr");

  /** 口径全称（响应 method 缺省时按当前选择兜底，历史调用无 method 字段） */
  const methodName = computed(() => RETURN_METHOD_NAME[returnMethod.value]);
  const rateLabel = computed(() => RETURN_RATE_LABEL[returnMethod.value]);

  /**
   * 主展示率值（百分数）。返回 null 的三种情况——数据未到、口径不匹配
   * （切换后旧响应未回来）、后端该口径字段缺失：调用方显示 `—`，
   * **不把旧口径的数字挂在新标签下，也不把「没算出来」画成 0**。
   */
  const primaryRate = computed(() => {
    const d = data.value;
    if (!d || d.cashflow_count <= 0) return null;
    if (d.method && d.method !== returnMethod.value) return null;
    const raw =
      returnMethod.value === "twr"
        ? d.twr_annualized
        : returnMethod.value === "dietz"
          ? d.dietz
          : d.xirr;
    return raw == null ? null : raw * 100;
  });

  /**
   * TWR 口径下因缺数据被跳过的天数（诚实降级提示用，#871）。
   * 日因子引擎对缺失的天「跳过而非当 0」——跳过的天数 > 0 意味着结果只
   * 覆盖有数据的天，展示侧应如实说明。非 TWR 口径或无该字段 → 0。
   */
  const daysSkipped = computed(() => {
    const d = data.value;
    if (!d || returnMethod.value !== "twr") return 0;
    return d.days_skipped ?? 0;
  });

  return {
    returnMethod,
    returnMethodOptions: RETURN_METHOD_OPTIONS,
    methodName,
    rateLabel,
    primaryRate,
    daysSkipped
  };
}
