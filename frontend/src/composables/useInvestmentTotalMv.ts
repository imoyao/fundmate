import { ref } from "vue";
import { getDistributions } from "@/api/summary";

/**
 * 投资类产品总市值（元）——持仓市值占比的分母口径（GitHub #2239）。
 *
 * 取 `/api/summary/distributions/` 的 `category_distribution`「投资理财」
 * 切片（股票类 + 基金等高风险产品，后端已剔除货基 / 逆回购现金等价物，
 * 与持仓页「投资理财」大类同源）。家庭级、静态价——与展示金额
 * （position_market_value 同为静态价）同一价格基准，行占比之和不会因
 * 实时价 / 静态价混用而漂移（旧行为分母优先实时汇总，实测两行占比
 * 合计可到 100.99%）。
 *
 * **跨分组稳定**：旧口径用分组（或首页摘要表展示行）合计当分母，切分组时
 * 同一持仓的占比随分组总额跳变，失去「仓位权重」意义（2026-10-16 用户反馈）。
 *
 * 模块级单例：自选页与欢迎页组件共享同一份分母，任一处刷新两处同时生效。
 * 消费点收在 .ts（.vue 不出现 `category_distribution` 字面量），
 * `welcome_structure_dedup.test.js` 的「全站只画一次构成图」判据不受影响——
 * 本模块只读一个标量当占比分母，不画图（与盘点页 useInventoryData 同形态）。
 */
const investmentTotalMv = ref<number | null>(null);

/** 拉取 / 刷新投资类产品总市值。切片缺失或为 0（无投资类持仓）记为取不到。 */
export async function refreshInvestmentTotalMv(): Promise<void> {
  try {
    const res = await getDistributions();
    const slice = (res.data?.category_distribution ?? []).find(
      d => d.name === "投资理财"
    );
    // 取不到时置 null：占比行隐藏，不回退到分组内 / 本表合计等旧口径——
    // 错误口径比没有数字更伤（#2239）。
    investmentTotalMv.value = slice && slice.value > 0 ? slice.value : null;
  } catch (e) {
    // 瞬时失败保留上一次成功的值，避免整页占比闪没
    console.error("Failed to fetch investment total:", e);
  }
}

/** 自选页 / 欢迎页持仓市值占比的分母（元）。null = 取不到，调用方应隐藏占比行。 */
export function useInvestmentTotalMv() {
  return { investmentTotalMv, refreshInvestmentTotalMv };
}
