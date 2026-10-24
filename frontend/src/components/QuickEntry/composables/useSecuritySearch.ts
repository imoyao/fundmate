import { ref } from "vue";
import { ElMessage } from "element-plus";
import { searchSecurities } from "@/api/securities";
import { searchFunds } from "@/api/funds";
import type { FundSearchItem } from "@/api/funds";
import { DEFAULT_SUB_RATE } from "@/utils/trading";

/** 证券/基金搜索结果项（原 BuyForm.vue 局部 interface，#980 拆出供子组件共用） */
export interface SecurityOption {
  symbol: string;
  name: string;
  market: string;
  type: string;
  type_label?: string;
  subscription_rate?: number;
  is_money_fund?: boolean;
  code?: string;
  is_manual?: boolean;
}

/**
 * 识别货币基金：以后端字段为准，代码段只作旧后端的降级兜底（#1661 收紧）。
 * 1. `/api/funds/search/` 的 is_money_fund 是**三态**（true / false / null，见
 *    `FundService._judge_money_fund`）：true → 货基；false / null → 非货基。
 *    null 表示名录里没有类型信息，此时**不猜**（宁漏不误）。
 * 2. 字段完全缺失（旧后端）时才回退代码段，且**必须先有交易所前缀**，与后端
 *    `fund_utils._code_segment_fallback` 同口径：SZ + 1[01]xxxx（深市货币基金/现金管理）、
 *    SH + 97xxxx（沪市现金管理产品）。
 *
 * 为什么不再用裸 `/^1[01]\d{4}$/`：场外基金代码由证监会独立分配，与交易所代码段无关
 * ——100016 富国天源沪港深平衡混合、110001 易方达平稳增长混合 都落在该段内；实测后端
 * `funds` 名录中命中该段的 106 个代码里 **0 个**是货币型。误判为货基会让后端价格任务
 * 按面值 1.0000 回写 current_price（持仓市值塌成「份额数」），故一律偏向漏判；即便前端
 * 这里判成 fund，后端写入路径仍会按 market 名录重新判定货基，不会漏掉真货基。
 *
 * 命中后前端提交 type='money_fund'。后端 #1233 改造后：
 * - 手动记账（本表单）走 POST /api/positions/ → process_buy_or_deposit(force_create_position=True)，
 *   照常建持仓、流水关联持仓；
 * - 交易导入路径仍只记孤儿资金流水（position_id=None、entry_status='orphan'）。
 */
export function resolveFundAssetType(
  code: string,
  isMoneyFund?: boolean | null
): "money_fund" | "fund" {
  if (isMoneyFund === true) return "money_fund";
  if (isMoneyFund === false) return "fund";
  return /^(?:SZ1[01]\d{4}|SH97\d{4})$/.test(code.trim().toUpperCase())
    ? "money_fund"
    : "fund";
}

/** 搜不到结果 / 搜索服务挂掉时的兜底项：允许用户按代码手填 */
function buildManualOption(query: string, ledgerType: string): SecurityOption {
  const isFundLedger = ledgerType === "fund" || ledgerType === "bank";
  const manualType = isFundLedger
    ? resolveFundAssetType(query.trim())
    : "stock";
  return {
    symbol: query.trim().toUpperCase(),
    name: query.trim(),
    market: "CN_A",
    type: manualType,
    type_label: manualType === "money_fund" ? "货币基金" : "手动输入",
    is_manual: true
  };
}

/**
 * 远程搜索：按账户类型分流到基金 / 证券接口，空结果降级为手填项。
 * @param getLedgerType 当前账户类型（调用时读取，账户切换后立即生效）
 */
export function useSecuritySearch(getLedgerType: () => string) {
  const searchLoading = ref(false);
  const securityOptions = ref<SecurityOption[]>([]);

  async function remoteSearch(query: string) {
    if (!query) {
      securityOptions.value = [];
      return;
    }
    searchLoading.value = true;
    const type = getLedgerType();
    try {
      let opts: SecurityOption[] = [];
      if (type === "fund" || type === "bank") {
        const res = await searchFunds(query);
        const arr = Array.isArray(res) ? res : (res.data ?? []);
        opts = arr.map((f: FundSearchItem) => {
          const assetType = resolveFundAssetType(f.code, f.is_money_fund);
          return {
            symbol: f.code,
            name: f.name,
            market: "CN_A",
            type: assetType,
            type_label: assetType === "money_fund" ? "货币基金" : "基金",
            subscription_rate: f.subscription_rate || DEFAULT_SUB_RATE
          };
        });
      } else {
        const res = await searchSecurities(query);
        const arr = Array.isArray(res) ? res : (res?.data ?? []);
        const typeLabels: Record<string, string> = {
          stock: "股票",
          bond: "可转债",
          etf: "ETF"
        };
        opts = arr.map((s: SecurityOption) => ({
          symbol: s.symbol,
          name: s.name,
          market: s.market,
          type: s.type,
          type_label: typeLabels[s.type] || s.type
        }));
      }
      if (opts.length === 0 && query.trim()) {
        opts = [buildManualOption(query, type)];
      }
      securityOptions.value = opts;
    } catch {
      if (query.trim()) {
        securityOptions.value = [buildManualOption(query, getLedgerType())];
      }
      ElMessage.warning("搜索服务暂不可用，已提供手动输入选项");
    } finally {
      searchLoading.value = false;
    }
  }

  /** 账户类型切换：旧选项是上一个账户的品类，必须清掉 */
  function reset() {
    securityOptions.value = [];
  }

  return { searchLoading, securityOptions, remoteSearch, reset };
}
