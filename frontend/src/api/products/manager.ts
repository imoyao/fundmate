// frontend/src/api/products/manager.ts
// 基金经理档案 / 代表作重仓（#2878 子域拆分；实现逐字搬自 api/products.ts，端点契约勿改）
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 任职基金条目（`/api/products/manager-profile/` 返回） */
/**
 * 展示换算结果（#1970 扩展 · 后端转换层 `services/tenure_display.py`）。
 *
 * **为什么前端不再自己换算**：后端存的是为计算而存的原始值（如从业天数 5125、
 * 规模 307.94），界面要的是给人看的解读（「14 年又 15 天」）。换算收口在后端单点，
 * 改口径不会漏改某个页面 —— 前端再写一次 `÷365` 正是要消灭的那种重复。
 *
 * `basis` 必须被消费：没有口径的数字等于假数字（详见各字段注释）。
 */
export interface TenureDisplay {
  /** 数值年（供前端排序/比较，不用于直接展示） */
  years: number;
  /** 展示文本，如「14 年又 15 天」（与天天基金 F10 口径逐字对齐） */
  text: string;
  /**
   * 口径标记：
   * - `em_days_derived`：由东财「累计从业时间」反推的**首次任职日**，
   *   为**日历跨度**，公转私/ 断档**不扣减**；
   * - `derived_from_start`：由库内任期起始日反推（无东财数据时的降级路径）。
   *
   * ⚠️ `em_days_derived` 的日期有 **±1 天不确定性**（基准日与东财统计截止日
   * 可能差一天，实测跨零点重跑会整体偏移）。故界面**不可**宣称「精确到 X 月 X 日
   * 开始任职」这类精确表述；「从业 N 年」不受影响。
   */
  basis: "em_days_derived" | "derived_from_start";
  /**
   * 溯源原值，由起始日**反算**回的天数（**非数据库原值** —— `managers` 表没有
   * `tenure_days` 列，天数只是入站数据不入库）。与东财原始天数的差异在 **±1 天**内。
   *
   * 仅供审计/展示辅助，**不要当精确溯源使用**。
   */
  raw: number | null;
  start_date: string;
  as_of: string;
}

/** 规模展示值。⚠️ 口径：仅该经理**现任**基金合计，不含已卸任基金 */
export interface ScaleDisplay {
  text: string;
  value: number;
  unit: "亿元";
  basis: string;
}

/** 回报展示值。`value` 带符号（负数为跌），前端按符号选 `--color-rise/fall` */
export interface ReturnDisplay {
  /** 显式带符号，如 `+43.59%` / `-18.52%` */
  text: string;
  value: number;
  basis: string;
}

export interface ManagerProfileFund {
  fund_code: string;
  name: string;
  /** 代表作品标记（来自 fund_managers 关联表） */
  is_classic: boolean;
  /** 任职起止：来自天天基金 F10（#1970 扩展前实测填充率 0%，恒为 null） */
  start_date: string | null;
  end_date: string | null;
  /**
   * 在任标记 = 未记录卸任日（#1970 扩展）。
   *
   * **不能改用东财全量表的「现任基金」**：实测张坤已于 2026-05-22 卸任蓝筹精选，
   * 但 `fund_manager_em` 仍把他列为该基金现任（粗粒度、不含卸任时间）。
   */
  is_active: boolean;
  /** 本基金任期时长（口径见 TenureDisplay.basis） */
  tenure_display: TenureDisplay | null;
}

/** 基金经理资料聚合结果（#1970）。字段缺失一律为 null，前端据此降级为「—」 */
export interface ManagerProfileResult {
  mgr_code: string;
  name: string;
  /** 重名靠公司消歧（库内 119 组重名，最多 6 位同名） */
  company: string | null;
  /** 公司全称（AMAC 公示口径，覆盖低于简称，允许为 null） */
  company_full_name: string | null;
  /** 公司整体管理规模（亿元）。⚠️ 与本人 sum_scale 不同口径，勿当作「占比」解读 */
  company_scale: number | null;
  mgr_type: string | null;
  /**
   * 首次任职日（由 tenure_days 反推落库）。
   *
   * ⚠️ ① 是**职业起点**，不是基金级任职起始（后者在 `funds[].start_date`）；
   * ⚠️ ② 为**误差 ≤1 天的估计值**（基准日与东财统计截止日可能差一天），
   *    不可当精确日期对外表述。
   */
  appointment_date: string | null;
  /** 以下为原始值（亿元 / %），保留供交叉校验；**展示请用 *_display** */
  sum_scale: number | null;
  best_return: number | null;
  avatar_url: string | null;
  // ── 展示档（转换层产出，优先消费这些）──
  /** 从业年限。以**首次任职日**为基准，非各基金任期起算 */
  tenure_display: TenureDisplay | null;
  scale_display: ScaleDisplay | null;
  best_return_display: ReturnDisplay | null;
  /** 任职基金**总数**（非返回条数——列表有 fund_limit 上限，两者不同） */
  fund_count: number;
  /** **已列出条目中**的在任数（受 fund_limit 截断，不是全量在任数） */
  active_fund_count: number;
  funds: ManagerProfileFund[];
}

/** 基金经理资料。入参是 mgr_code 而非姓名（库内重名，姓名不是唯一键）。 */
export function getManagerProfile(params: {
  mgr_code: string;
  fund_limit?: number;
}) {
  return http.request<ApiResponse<ManagerProfileResult>>(
    "get",
    "/api/products/manager-profile/",
    { params }
  );
}

/** 代表作重仓单行 */
export interface ManagerHoldingRow {
  rank: number | null;
  stock_code: string;
  stock_name: string | null;
  /** 占净值比例（%） */
  ratio: number | null;
  /** 持仓市值（万元） */
  market_value: number | null;
}

/**
 * 风格标签（#2044）。
 *
 * - `dim`/`key` 是稳定枚举，前端按 `key` 映射 Badge 样式；
 * - 后端**不返回颜色**（配色由前端令牌决定，硬约束）；
 * - 数据不足的维度**缺席**而非 null——`style_labels` 里找不到该 `dim` 即该维度
 *   无数据，展示层按维度缺席处理（不渲染占位徽章）。
 */
export interface StyleLabel {
  /** 维度：`concentration` 持仓集中度 / `industry` 行业集中度 / `size` 市值风格 */
  dim: string;
  /** 稳定标签枚举，如 `concentration_high` / `size_large` */
  key: string;
  /** 中文短文案，如「持仓高集中」 */
  label: string;
  /** 可解释依据，如「前十大重仓占净值 65.8%，全库 P80」（hover/副文本展示） */
  basis: string;
}

/** 代表作前十大重仓结果（#1970 扩展 · `manager-holdings` 端点） */
export interface ManagerHoldingsResult {
  fund_code: string | null;
  fund_name: string | null;
  /** 报告期，如 2026Q2 */
  report_period: string | null;
  /** 报告期截止日 */
  report_date: string | null;
  /** 口径：`full` 全量披露 / `top10` 季报前十大 */
  basis: "full" | "top10" | null;
  /**
   * 口径中文标签，**必须展示**。
   *
   * 为什么：用户看到「十大重仓」时需要知道这是季报口径（只披露了 10 只）
   * 还是半年报全量，否则会把「只披露 10 只」误读成「只买了 10 只」。
   */
  basis_label: string | null;
  /** 前 N 大合计占净值比（集中度锚点） */
  total_ratio: number | null;
  rows: ManagerHoldingRow[];
  /** 风格标签（#2044）：纯函数判据 + 全库标定阈值，数据不足维度缺席 */
  style_labels: StyleLabel[];
  /** 无数据时的原因（固定契约：rows 为空即无数据，不是接口错误） */
  empty_reason?: string;
}

/**
 * 代表作前十大重仓。入参与 manager-profile 一致（mgr_code 而非姓名）。
 *
 * 为什么独立端点：重仓要按 fund_code 查最新报告期，是独立重查询；
 * 经理区块首屏并不总需要它，拆开后前端可按需决定发不发。
 */
export function getManagerHoldings(params: {
  mgr_code: string;
  fund_limit?: number;
}) {
  return http.request<ApiResponse<ManagerHoldingsResult>>(
    "get",
    "/api/products/manager-holdings/",
    { params }
  );
}
