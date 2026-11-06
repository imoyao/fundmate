// frontend/src/api/products/advisor.ts
// 投顾组合档案（#2878 子域拆分；实现逐字搬自 api/products.ts，端点契约勿改）
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/**
 * 投顾组合档案（#1975 · 详情页投顾组合区块）。字段名跟随后端/库的 snake_case 契约。
 *
 * 可得性（本机真实库 105 个组合实测）：`org_name` / `risk_level` / 区间收益 /
 * 回撤 / 波动率 / 夏普 填充率 **91~100%**；而 `strategy_type` / `cum_return` /
 * `running_days` / `benchmark` / `excess_return` 为 **0%**、`host` **1.9%**、
 * `return_ytd` **2.9%** —— 前端一律降级「—」，不编造占位值（设计 §6 诚实降级）。
 *
 * `holding_count` / `adjust_count` 供区块判断「成分基金 / 调仓记录」要不要渲染、
 * 请求要不要发：实测调仓只覆盖 **16/105** 个组合，多数组合**「没有调仓」才是常态**。
 */
export interface AdvisorProfileResult {
  code: string;
  name: string;
  /** 平台码（QIEMAN / TIANTIAN…）；中文标签走 constants/advisorPlatform */
  platform: string;
  org_name: string | null;
  /** 主理人；实测填充率仅 1.9%，故识别主要靠「名称 + 平台 + 机构」 */
  host: string | null;
  risk_level: string | null;
  product_type: string | null;
  strategy_type: string | null;
  strategy_summary: string | null;
  strategy_desc: string | null;
  /** 配置目标（五笔钱词表：liquid / stable / longterm…） */
  allocation: string | null;
  estab_date: string | null;
  running_days: number | null;
  benchmark: string | null;
  excess_return: number | null;
  nav: number | null;
  nav_date: string | null;
  source_url: string | null;
  is_active: boolean;
  cum_return: number | null;
  annual_return: number | null;
  return_1d: number | null;
  return_1w: number | null;
  return_1m: number | null;
  return_1q: number | null;
  return_6m: number | null;
  return_1y: number | null;
  return_ytd: number | null;
  return_since_incep: number | null;
  max_drawdown: number | null;
  volatility: number | null;
  sharpe_ratio: number | null;
  holding_count: number;
  adjust_count: number;
}

/**
 * 取投顾组合档案（详情页投顾组合区块首屏）。
 *
 * 只回答「这是个什么组合」；「持什么 / 调过什么」走**已上线**的
 * `getAdvisorHoldings` / `getAdvisorAdjusts`（自选速览抽屉在用的同一对端点），
 * 本函数不重复搬数据 —— 但返回的条数可让调用方先判断要不要发那两个请求。
 */
export function getAdvisorProfile(params: { code: string }) {
  return http.request<ApiResponse<AdvisorProfileResult>>(
    "get",
    "/api/products/advisor-profile/",
    { params }
  );
}
