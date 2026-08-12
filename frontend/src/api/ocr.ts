import { http } from "@/utils/http";

/** OCR 当日剩余次数（进入弹窗前展示余量） */
export type OcrUsageResult = {
  data: {
    feature: string;
    period_date: string;
    count: number;
    quota: number;
    remaining: number;
  };
  message: string;
};

/** OCR/文本批量识别返回的单条候选 */
export interface OcrImportItem {
  code: string;
  name: string;
  /** 标准化代码（场内如 SH600519；场外基金为裸代码）。缺失时用 code */
  symbol?: string;
  /** 资产类型：stock / etf / bond / fund（后端反查 Securities/Funds 表） */
  type?: string;
  market?: string;
  venue?: string;
}

/** 查询当日 OCR 剩余次数 */
export const getOcrUsage = () => {
  return http.request<OcrUsageResult>("get", "/api/ocr/usage");
};

/** 图片（base64）→ 火山方舟识别 → 基金候选列表；消耗 1 次当日配额 */
export const recognizeImage = (imageBase64: string) => {
  return http.request<{ data: { items: OcrImportItem[]; usage: unknown } }>(
    "post",
    "/api/ocr/recognize",
    { data: { image_base64: imageBase64 } }
  );
};

/** 纯文本 → LLM 批量提取基金代码（AI 批量导入）；消耗 1 次当日配额 */
export const parseImportText = (text: string) => {
  return http.request<{ data: { items: OcrImportItem[]; usage: unknown } }>(
    "post",
    "/api/ocr/parse",
    { data: { text } }
  );
};
