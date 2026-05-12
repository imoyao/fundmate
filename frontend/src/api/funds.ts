import { http } from "@/utils/http";

export interface FundOption {
  code: string;
  name: string;
  type: string;
}

export function searchFunds(keyword: string) {
  return http.request<any>("get", "/api/funds/search", {
    params: { q: keyword }
  });
}
