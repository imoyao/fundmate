// frontend/src/api/products/pro.ts
// Pro 模块状态 / 深度洞察 / 风险 / 资产配置相关性（#2878 子域拆分；实现逐字搬自 api/products.ts，端点契约勿改）
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** Pro 单模块可用性位（#2272 · #994 Phase 1 骨架；available 在 Phase 2-4 逐个翻转） */
export interface ProModuleStatus {
  /** 模块是否已上线（performance 已随 Phase 2 翻真） */
  available: boolean;
  /** 落地 Phase（2/2/3/4，见 #994 五阶段排期） */
  phase: number;
}

/**
 * `GET /api/products/pro/` 返回（#2272 骨架；#2324 起由家庭权益驱动）。
 *
 * `paywall_required` **不再是恒量**：后端按家庭权益位现算
 * （`backend/app/services/product_pro_status.py` 的 `build_pro_status`），
 * 前端仅在 `VITE_PRO_PAYWALL_ENABLED` 未配置时采信它（三态判定见
 * `views/product/components/proEntitlement.ts` 的 `resolvePaywallEnabled`）。
 */
export interface ProStatusResult {
  symbol: string;
  asset_type: string | null;
  /** Pro 总开关；当前恒 true（模块级可用性由 `modules[*].available` 决定） */
  pro_enabled: boolean;
  /**
   * 是否必须挂付费墙遮罩：家庭一份 Pro 权益都没开通 ⇒ true。
   *
   * 与「模块可用性」是两件事：`available` 说的是**这个模块建好没有**，
   * 本字段说的是**这户人家能不能看**。付费墙开着时内容端点会回 403，
   * 故前端不应把它当展示位来读。
   */
  paywall_required: boolean;
  modules: Record<
    "performance" | "risk" | "allocation" | "report",
    ProModuleStatus
  >;
}

/** 拉取单标的 Pro 状态位（详情页「高级洞察 Pro」区块挂载即取，失败由组件降级为无徽标） */
export function fetchProStatus(symbol: string, assetType?: string | null) {
  return http.request<ApiResponse<ProStatusResult>>(
    "get",
    "/api/products/pro/",
    {
      params: { symbol, asset_type: assetType ?? undefined }
    }
  );
}

/** 账户级 XIRR（#1972 口径：跨账户现金流合并 + 当前市值虚拟卖出；空结构全 0） */
export interface ProInsightXirr {
  xirr: number;
  total_invested: number;
  current_value: number;
  total_withdrawn: number;
  total_return: number;
  cashflow_count: number;
}

/** 账户级行为画像（#994 Phase 0 FIFO 口径 v2：盈亏由配对自算，不读 realized_pnl） */
export interface ProInsightBehavior {
  /** 全额配对的卖出笔数（胜率/盈亏比样本量） */
  closed_count: number;
  win_rate: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  profit_loss_ratio: number | null;
  /** 平均持有天数（按配对份额加权） */
  avg_holding_days: number | null;
  /** Σ 配对盈亏（元），仅全额配对的卖出笔 */
  realized_pnl_total: number | null;
  cash_dividend_total: number | null;
  buy_count: number;
  sell_count: number;
  unmatched_sell_count: number;
  unmatched_sell_shares: number;
  caveats: string[];
}

/** `GET /api/products/pro-insight/` 返回（#994 Phase 2 · 模块一账户级指标）。
 * has_account_data=false 时前端渲染引导文案，不编数字 */
export interface ProInsightResult {
  symbol: string;
  asset_type: string | null;
  has_account_data: boolean;
  xirr: ProInsightXirr;
  behavior: ProInsightBehavior;
}

/** 拉取 Pro 模块一账户级指标（XIRR + 行为画像；登录态注入 family_id） */
export function fetchProInsight(symbol: string, assetType?: string | null) {
  return http.request<ApiResponse<ProInsightResult>>(
    "get",
    "/api/products/pro-insight/",
    {
      params: { symbol, asset_type: assetType ?? undefined }
    }
  );
}

/** Pro 模块二 BIAS 块（既有 bias 引擎口径：刘晨明 LOGBIAS，EMA20 对数乖离） */
export interface ProRiskBias {
  available: boolean;
  /** 乖离率值（%）；正 = 高于均线 */
  bias: number | null;
  /** 引擎信号标签（温度计同款话术） */
  label: string | null;
  /** 波段位置 0-100 */
  position: number | null;
  /** 最新收盘价/净值 */
  close: number | null;
  /** 数据日期（ISO） */
  data_date: string | null;
  /** 行情源失败回退旧缓存时为 true */
  stale: boolean;
  reason: string | null;
}

/** Pro 模块二 风险块（波动率 + VaR 95%，analytics/var.py 口径） */
export interface ProRiskMetrics {
  available: boolean;
  /** 年化波动率（%） */
  annual_volatility: number | null;
  /** VaR 95%（%，负数 = 单日最大可能亏损） */
  var_95: number | null;
  /** 窗口内日收益样本数 */
  sample_returns: number;
  window: string;
  as_of: string | null;
  /** 序列口径（累计净值/前复权…） */
  basis: string | null;
  reason: string | null;
  caveats: string[];
}

/** Pro 模块二 账户级块（持仓市值 × VaR%，模块一 XIRR 同源市值） */
export interface ProRiskAccount {
  has_position: boolean;
  /** 持仓市值（元） */
  position_value: number;
  /** 95% 置信单日最坏亏损（元，负数）；无持仓或 VaR 缺失为 null */
  var_95_yuan: number | null;
}

/** `GET /api/products/pro-risk/` 返回（#994 Phase 2 · 模块二偏离与风险控制）。
 * 块级自治：基金级指标不依赖账户数据，逐块 available + reason */
export interface ProRiskResult {
  symbol: string;
  asset_type: string | null;
  bias: ProRiskBias;
  risk: ProRiskMetrics;
  account: ProRiskAccount;
}

/** Pro 模块三 单只对比对象（当前标的 vs 家庭其余持仓之一） */
export interface ProAllocationPeer {
  symbol: string;
  /** 持仓名称（可能为 null：导入时没拿到名字的那几行） */
  name: string | null;
  asset_type: string | null;
  /** Pearson 相关系数（-1 ~ +1）；这里恒有值——算不出的已被后端跳过 */
  correlation: number;
  /** 配对上的同期交易日数（低于 60 天的不出现在结果里） */
  overlap_days: number;
}

/** `GET /api/products/pro-allocation/` 返回（#994 Phase 2 · 模块三资产配置与相关性）。
 * 回答一句话：你以为分散了吗？ */
export interface ProAllocationResult {
  symbol: string;
  asset_type: string | null;
  /** 序列窗口（1Y） */
  window: string;
  /** 配对样本下限（60），前端脚注解释「为什么有持仓没出现在列表里」 */
  min_overlap: number;
  available: boolean;
  /** 不可用时原因（无序列 / 无其他持仓 / 全部 peer 都算不出） */
  reason: string | null;
  /** 基准标的序列有效点数 */
  sample_days: number;
  /** 序列口径（累计净值/前复权…） */
  basis: string | null;
  /** 相关系数列表（|ρ| 降序） */
  peers: ProAllocationPeer[];
  /** 因样本不足/无波动被跳过的持仓只数——诚实披露，不静默丢弃 */
  skipped_count: number;
  /** ρ ≥ 0.8 的只数：账面分散、风险仍集中的部分 */
  high_correlation_count: number;
  caveats: string[];
}

/** 拉取 Pro 模块二风险指标（BIAS + 波动率 + VaR；登录态注入 family_id） */
export function fetchProRisk(symbol: string, assetType?: string | null) {
  return http.request<ApiResponse<ProRiskResult>>(
    "get",
    "/api/products/pro-risk/",
    {
      params: { symbol, asset_type: assetType ?? undefined }
    }
  );
}

/** 拉取 Pro 模块三相关性分析（当前标的 vs 家庭持仓；登录态注入 family_id） */
export function fetchProAllocation(symbol: string, assetType?: string | null) {
  return http.request<ApiResponse<ProAllocationResult>>(
    "get",
    "/api/products/pro-allocation/",
    {
      params: { symbol, asset_type: assetType ?? undefined }
    }
  );
}
