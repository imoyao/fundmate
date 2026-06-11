import { http } from "@/utils/http";

/** 解析上传的交易文件，返回预览数据 */
export function parseFile(file: File, template: string, ledgerId: number | null) {
  const formData = new FormData();
  formData.append('file', file);
  // 构建查询参数
  const params = new URLSearchParams();
  params.set('template', template);
  if (ledgerId) {
    params.set('ledger_id', String(ledgerId));
  }
  return http.request<any>("post", `/api/importers/parse?${params.toString()}`, {
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 10000,
  });
}

/** 确认导入选中的交易记录 */
export function confirmImport(rows: any[]) {
  return http.request<any>("post", "/api/importers/confirm", { data: rows });
}
