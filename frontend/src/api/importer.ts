import { http } from "@/utils/http";

/** 解析上传的交易文件，返回预览数据 */
export function parseFile(file: File, template: string = 'standard') {
  const formData = new FormData();
  formData.append('file', file);
  return http.request<any>("post", `/api/importers/parse?template=${template}`, {
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  });
}

/** 确认导入选中的交易记录 */
export function confirmImport(rows: any[]) {
  return http.request<any>("post", "/api/importers/confirm", { data: rows });
}
