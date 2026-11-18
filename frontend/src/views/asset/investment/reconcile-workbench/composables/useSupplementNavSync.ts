import { computed, ref, watch, type Ref } from "vue";

/** 净值链路的最小契约（`useFundTradeDate().calcConfirmAndNav` 的子集） */
export type SupplementNavResolver = (options: {
  tradeDate: string;
  symbol?: string;
  isAfter15?: boolean;
}) => Promise<{ actualNavDate: string; nav?: number } | null>;

interface SupplementNavForm {
  op_type: string;
  confirm_date: string;
  avg_price?: number;
  buy_amount?: number;
}

/**
 * 补录弹窗的「交易日期 → 确认净值」联动（2026-11-15）。
 *
 * ## 为什么补录也要拉净值
 *
 * owner 指出：记一笔的基金买入是「填金额 → 按当日净值自动算份额」，补录却要人
 * 手填「成交数量 + 成交价格」，同一件事两个口径。基金买入时用户手里有的是金额
 * 与日期，份额恰恰是要算出来的那个数——让人反着手填就是把换算成本推回给用户。
 *
 * 口径与 `QuickEntry` 的 `useBuyNavSync` 一致：一律先算确认日（这里没有 15:00
 * 档位，补录的是历史成交，按 15:00 前下单处理）再按实际净值日拉净值。拉不到就
 * 置 `navMissing`，由表单提示「份额与净值请手填」，**不猜一个净值**。
 *
 * ## 为什么只在「场外基金 + 买入」时拉
 *
 * - 股票 / ETF / 可转债没有当日净值，成交价就是成交价；
 * - 卖出 / 存入 / 取出不需要反算份额（卖出填的是份额，账单上写的就是份额）。
 *
 * 品种来自后端差异出参的 `asset_type`（`positions.type`，名录回退 `fund`），
 * 前端不再按「未知品种」一律 4 位精度兜底。
 */
export function useSupplementNavSync(deps: {
  form: SupplementNavForm;
  /** 差异行标的的品种（`fund` / `stock` / `etf` / ...），查不到为空串 */
  assetType: Ref<string>;
  /** 标的代码（拉净值用） */
  symbol: () => string;
  /**
   * 净值链路（调用方传 `useFundTradeDate().calcConfirmAndNav`）。
   *
   * 为什么不在本模块内自己 `useFundTradeDate()`：那条链会经 `@/utils/http` 一路
   * 引到 `@/router` → `@/utils/supabase`，模块级就要 VITE_SUPABASE_*；单测在没有
   * env 的环境下会直接「Failed Suites」。注入后本模块只依赖 Vue + 纯状态，
   * 「净值查不到时清系统填的值、但不动用户手填的值」这条可以被测试咬住。
   */
  calcConfirmAndNav: SupplementNavResolver;
}) {
  const { form, assetType, symbol, calcConfirmAndNav } = deps;

  const navMissing = ref(false);
  /** 我们自动写进 `avg_price` 的净值；用户改过就置空，之后不再被系统清掉 */
  const autoNav = ref<number | null>(null);
  const navDate = ref("");

  const isFundBuy = computed(
    () => assetType.value === "fund" && form.op_type === "buy"
  );

  /** 用户手改了净值（不是我们填的那个）⇒ 视为人工值，清/回填都不再动它 */
  watch(
    () => form.avg_price,
    value => {
      if (autoNav.value != null && value !== autoNav.value)
        autoNav.value = null;
    }
  );

  function clearAutoNav(): void {
    if (autoNav.value == null) return;
    form.avg_price = undefined;
    autoNav.value = null;
  }

  watch([() => form.confirm_date, () => form.op_type, assetType], async () => {
    if (!isFundBuy.value || !form.confirm_date) {
      clearAutoNav();
      navMissing.value = false;
      navDate.value = "";
      return;
    }
    const result = await calcConfirmAndNav({
      tradeDate: form.confirm_date,
      symbol: symbol(),
      // 补录的是历史成交，没有「15:00 后下单」这个档位，按当日 15:00 前处理
      isAfter15: false
    });
    if (result?.nav != null) {
      form.avg_price = result.nav;
      autoNav.value = result.nav;
      navMissing.value = false;
      navDate.value = result.actualNavDate;
      return;
    }
    // 净值缺失：清掉我们填的旧净值，别让上一笔/上一天的净值留在框里
    clearAutoNav();
    navMissing.value = true;
    navDate.value = "";
  });

  /** 净值行下面的口径提示（无提示时为空串，模板按空串隐藏） */
  const navHint = computed(() => {
    if (!isFundBuy.value) return "";
    if (navMissing.value) {
      return `${form.confirm_date} 的净值查不到：份额和净值请手填，别按估算值提交`;
    }
    if (typeof form.avg_price === "number" && form.avg_price > 0) {
      return navDate.value
        ? `已按 ${navDate.value} 的净值自动填入，可按实际确认净值修改`
        : "已按该日净值自动填入，可按实际确认净值修改";
    }
    return "选好交易日期后自动填当日净值";
  });

  return { navMissing, navDate, navHint, isFundBuy };
}
