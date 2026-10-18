import { http } from "@/utils/http";
import type { ApiResponse, DeleteResponse } from "@/api/types";

/** 策略标签（对齐后端 _tag_to_dict） */
export interface StrategyTag {
  id: number;
  name: string;
  created_at?: string | null;
}

/** 策略视图持仓行（对齐 build_strategy_overview.holdings；资产行 id = asset.id + 100000） */
export interface StrategyOverviewHolding {
  id: number;
  symbol: string;
  name: string | null;
  type: string | null;
  type_label: string;
  quantity: number;
  current_price: number;
  avg_price: number;
  account_name: string | null;
  /** 价格时点（#2140 / #2210）：基金=实际采用的最新净值日；其他=快照回写日；缺省为 null */
  price_date?: string | null;
  /**
   * 当日确认口径是否已定型（#2210）：true = 行内估值副行应隐藏；
   * null / 缺省 = 不隐藏。**状态 = 后端字段契约**，前端禁止按日期自行推断。
   */
  settled_today?: boolean | null;
}

/** 策略视图全局数据（对齐 build_strategy_overview 返回 dict） */
export interface StrategyOverviewData {
  holdings: StrategyOverviewHolding[];
  tags: { id: number; name: string }[];
  /** {position_id: [tag_name, ...]}；JSON 键为字符串形式的持仓 id */
  relations: Record<string, string[]>;
}

/** 获取所有策略标签 */
export function getStrategyTags() {
  return http.request<ApiResponse<StrategyTag[]>>("get", "/api/strategy/");
}

/** 创建策略标签（重名时后端返回 409） */
export function createStrategyTag(data: { name: string }) {
  return http.request<ApiResponse<StrategyTag>>("post", "/api/strategy/", {
    data
  });
}

/** 删除策略标签（级联删除关联） */
export function deleteStrategyTag(id: number) {
  return http.request<DeleteResponse>("delete", `/api/strategy/${id}/`);
}

/** 为持仓绑定策略标签（重复绑定时后端返回 409） */
export function bindPositionTag(tagId: number, positionId: number) {
  return http.request<DeleteResponse>(
    "post",
    `/api/strategy/${tagId}/positions/${positionId}/`
  );
}

/** 为持仓解绑策略标签 */
export function unbindPositionTag(tagId: number, positionId: number) {
  return http.request<DeleteResponse>(
    "delete",
    `/api/strategy/${tagId}/positions/${positionId}/`
  );
}

/** 获取所有持仓的策略标签关联，data 形如 {position_id: [tag_name, ...]} */
export function getPositionTagRelations() {
  return http.request<ApiResponse<Record<string, string[]>>>(
    "get",
    "/api/strategy/relations/"
  );
}

/** 获取策略视图全局数据（持仓、资产、标签、关联关系，一个请求） */
export function getStrategyOverview() {
  return http.request<ApiResponse<StrategyOverviewData>>(
    "get",
    "/api/strategy/overview/"
  );
}
