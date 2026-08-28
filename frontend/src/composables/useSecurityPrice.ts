import { ref, watch, type Ref } from "vue";
import {
  getSecurityPriceRange,
  type SecurityPriceRange
} from "@/api/securities";

/**
 * 证券（股票/可转债）成交价区间：随标的和交易日拉取，供卖出价校验与提交拦截。
 * 快速卖出、手动记账、买入三处共用，避免各写各的拉取与校验逻辑（#948 统一约束）。
 */
export function useSecurityPriceRange(
  symbol: Ref<string | undefined>,
  date: Ref<string | undefined>,
  isStock: Ref<boolean> = ref(true)
) {
  const priceRange = ref<SecurityPriceRange | null>(null);
  const loading = ref(false);

  async function refresh(
    sym?: string,
    d?: string
  ): Promise<SecurityPriceRange | null> {
    const s = sym ?? symbol.value;
    const dt = d ?? date.value;
    if (!s || !isStock.value) {
      priceRange.value = null;
      return null;
    }
    loading.value = true;
    try {
      const res = await getSecurityPriceRange(s, dt);
      priceRange.value = res?.data ?? null;
    } catch {
      priceRange.value = null;
    } finally {
      loading.value = false;
    }
    return priceRange.value;
  }

  watch([symbol, date, isStock], () => {
    refresh();
  });

  return { priceRange, loading, refresh };
}

/** 构造 Element Plus 校验器：成交价明显偏离当日区间即提示，绝不静默修正（#948）。无行情放行。 */
export function createStockPriceValidator(
  getRange: () => SecurityPriceRange | null,
  isStock: () => boolean
) {
  return (_rule: unknown, value: unknown, callback: (err?: Error) => void) => {
    if (!isStock() || value == null || (value as number) <= 0)
      return callback();
    const range = getRange();
    if (!range) return callback();
    const { low, high, date: rangeDate } = range;
    if ((value as number) < low || (value as number) > high) {
      return callback(
        new Error(
          `成交价超出 ${rangeDate} 交易日区间（${low} ~ ${high}），请核对后重新输入`
        )
      );
    }
    callback();
  };
}

/** 提交前一次性校验，返回错误信息或 null（无行情放行，后端兜底）。 */
export function checkPriceInRange(
  price: number,
  range: SecurityPriceRange | null,
  isStock: boolean
): string | null {
  if (!isStock || !price || price <= 0 || !range) return null;
  const { low, high, date: rangeDate } = range;
  if (price < low || price > high) {
    return `成交价超出 ${rangeDate} 交易日区间（${low} ~ ${high}），请核对后重新输入`;
  }
  return null;
}
