import { http } from "@/utils/http";

export interface StrategyTag {
  id: number;
  name: string;
  created_at?: string;
}

/** 获取所有策略标签 */
export function getStrategyTags() {
  return http.request<any>("get", "/api/strategy/");
}

/** 创建策略标签 */
export function createStrategyTag(data: { name: string }) {
  return http.request<any>("post", "/api/strategy/", { data });
}

/** 删除策略标签 */
export function deleteStrategyTag(id: number) {
  return http.request<any>("delete", `/api/strategy/${id}/`);
}

/** 为持仓绑定策略标签 */
export function bindPositionTag(tagId: number, positionId: number) {
  return http.request<any>("post", `/api/strategy/${tagId}/positions/${positionId}/`);
}

/** 为持仓解绑策略标签 */
export function unbindPositionTag(tagId: number, positionId: number) {
  return http.request<any>("delete", `/api/strategy/${tagId}/positions/${positionId}/`);
}

/** 获取所有持仓的策略标签关联 */
export function getPositionTagRelations() {
  return http.request<any>("get", "/api/strategy/relations/");
}

/** 获取策略视图全局数据（持仓、资产、标签、关联关系） */
export function getStrategyOverview() {
  return http.request<any>("get", "/api/strategy/overview/");
}
