import { ref, watch, type Ref } from "vue";
import { checkTradingDay } from "@/api/utils";
import { useFundTradeDate } from "@/composables/useFundTradeDate";
import type { SecurityOption } from "./useSecuritySearch";

interface NavSyncForm {
  trade_date: string;
  isAfter15: boolean;
  type: string;
  price: number | undefined;
  buyAmount: number | undefined;
  shares: number | undefined;
}

/**
 * 买入侧的「交易日 / 确认日 / 净值」同步（#980 从 BuyForm 拆出）。
 *
 * 一条 watch 串起三件事：交易日期或 15:00 时点变化 → 校验是否交易日；基金的净值
 * 一律先算确认日（15:00 后顺延）再按确认日拉净值。拉不到净值时置 `navMissing`，
 * 顺手清掉陈旧价格与联动份额，改走「先记账、官方净值到位后回填」。
 */
export function useBuyNavSync(deps: {
  form: NavSyncForm;
  selectedSecurityOption: Ref<SecurityOption | null>;
  /**
   * 净值缺失先记账（本模块负责置位/复位，状态由父层持有——联动与提交都要读它）：
   * 当日净值未发布 / 数据源故障拉不到时，不再把用户挡在记账之外，份额允许留空
   * （后端按金额与最近净值占位暂算、标 pending_nav），官方净值落库后由
   * nav_backfill 自动回填份额与成本。
   */
  navMissing: Ref<boolean>;
  /** 净值回填后回写脏基线（系统派生值不算用户编辑） */
  markClean: () => void;
}) {
  const { form, selectedSecurityOption, navMissing, markClean } = deps;

  const isTradingDay = ref<boolean | null>(null);

  // 基金交易日期联动 composable（calcFundConfirmDate + fetchFundNav）
  const {
    actualNavDate,
    confirmDate,
    calcConfirmAndNav,
    reset: resetTradeDate
  } = useFundTradeDate();

  async function fetchTradingDay() {
    if (selectedSecurityOption.value?.type === "fund" || !form.trade_date) {
      isTradingDay.value = null;
      return;
    }
    try {
      const res = await checkTradingDay(form.trade_date);
      isTradingDay.value = res?.data?.is_trading_day ?? false;
    } catch {
      isTradingDay.value = null;
    }
  }

  // 核心联动：监听日期和 15:00 切换，先算确认日，再用确认日拉净值
  watch(
    [() => form.trade_date, () => form.isAfter15, selectedSecurityOption],
    async () => {
      fetchTradingDay();

      // 股票价格区间由 useSecurityPriceRange 随标的/交易日自动刷新（#948 统一约束）

      if (selectedSecurityOption.value?.type === "fund" && form.trade_date) {
        const opt = selectedSecurityOption.value;
        if (!opt) return;
        const result = await calcConfirmAndNav({
          tradeDate: form.trade_date,
          symbol: opt.symbol,
          isAfter15: form.isAfter15
        });
        if (result?.nav != null) {
          form.price = result.nav;
          navMissing.value = false;
        } else {
          // 净值缺失：清掉陈旧价格与联动份额，改走「先记账、官方净值到位后回填」
          navMissing.value = true;
          form.price = undefined;
          form.shares = undefined;
        }
        // 净值是系统回填的派生值。用户还没录入金额/份额时，回填完即视为新的干净基线：
        // 否则「带预填进入页面、什么都不做就切操作类型」会被判成有未保存修改。
        // 用户已录入金额/份额时**不能**回写基线，否则那部分编辑会被洗掉。
        if (form.buyAmount == null && form.shares == null) markClean();
      } else {
        navMissing.value = false;
      }
    }
  );

  return {
    navMissing,
    isTradingDay,
    actualNavDate,
    confirmDate,
    calcConfirmAndNav,
    resetTradeDate
  };
}
