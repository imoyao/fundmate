import { http } from "@/utils/http";

export function getPortfolioXirr() {
  return http.request<any>("get", "/api/performance/xirr/", {
    params: { scope: "portfolio" }
  });
}

export function getPositionXirr(positionId: number) {
  return http.request<any>("get", "/api/performance/xirr/", {
    params: { scope: "position", position_id: positionId }
  });
}
