import { http } from "@/utils/http";
import type { OcrHoldingRow } from "@/api/ocr";

/** 持仓导入确认响应（holding_import）：返回本次 upsert 至 positions 的条数 */
export interface HoldingImportResponse {
  data: {
    imported: number;
    [key: string]: unknown;
  };
  message?: string;
}

/** 解析上传的交易文件，返回预览数据 */
export function parseFile(
  file: File,
  template: string,
  ledgerId: number | null
) {
  const formData = new FormData();
  formData.append("file", file);
  // 构建查询参数
  const params = new URLSearchParams();
  params.set("template", template);
  if (ledgerId) {
    params.set("ledger_id", String(ledgerId));
  }
  return http.request<any>(
    "post",
    `/api/importers/parse?${params.toString()}`,
    {
      data: formData,
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 10000
    }
  );
}

/** 确认导入选中的交易记录 */
export function confirmImport(rows: any[]) {
  return http.request<any>("post", "/api/importers/confirm", { data: rows });
}

/** 确认导入持仓快照（holding_import）：SET 语义 upsert 至 positions，不建交易流水（#1018） */
export function confirmHoldingImport(rows: OcrHoldingRow[]) {
  return http.request<HoldingImportResponse>(
    "post",
    "/api/importers/holdings/confirm",
    {
      data: rows
    }
  );
}
