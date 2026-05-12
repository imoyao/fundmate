import { http } from "@/utils/http";

export interface SecurityOption {
  symbol: string;
  name: string;
  market: string;
  type: string;
}

export function searchSecurities(keyword: string) {
  return http.request<any>("get", "/api/securities/search/", {
    params: { q: keyword }
  });
}
