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

// frontend/src/api/importer.ts
export function calcFundNav(symbols: string[], date: string) {
  return http.request<any>("post", "/api/funds/nav/", {
    data: { symbols, date }
  });
}
