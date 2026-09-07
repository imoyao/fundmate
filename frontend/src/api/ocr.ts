import { http } from "@/utils/http";

// AI 识别调用后端会再调火山方舟（单次最长 60s + 重试），全局 axios timeout(10s) 不够，单独放宽到 120s
const OCR_REQUEST_TIMEOUT = 120000;

/** 构建 OCR ledger_id 查询参数；用 != null 覆盖 ledgerId=0 这种合法值，避免 truthy 误判导致漏传 */
function buildLedgerParams(ledgerId?: number | null) {
  return ledgerId != null ? { ledger_id: String(ledgerId) } : undefined;
}

/** AI 识别场景：自选导入（默认）/ 持仓交易导入 / 持仓导入（仅 upsert 持仓，不建流水，见 #1018） */
export type OcrScenario = "watchlist_import" | "txn_import" | "holding_import";

/** OCR 当日剩余次数（进入弹窗前展示余量；feature=ocr_import|txn_import） */
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

/** 自选场景候选（OCR/文本批量识别返回的单条候选） */
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

/** 持仓场景预览行（与 importer parse 预览行同构，可直接复用导入确认表格） */
export interface OcrTxnRow {
  symbol: string;
  name: string;
  type: string;
  display_type: string;
  op_type: string;
  op_type_label: string;
  quantity: number;
  price: number;
  amount: number;
  fee: number;
  trade_date: string;
  import_hash: string;
  source: string;
  is_duplicate: boolean;
  error: string | null;
  warnings: string[];
  /** 资产配置（liquid/longterm，预览表格回填） */
  allocation?: string | null;
}

/** 持仓导入场景预览行（holding_import）：确认时走 /api/importers/holdings/confirm，不建流水 */
export interface OcrHoldingRow {
  symbol: string;
  name: string;
  type: string;
  quantity: number | string;
  price: number | string;
  amount: number | string;
  snapshot_date: string;
  account_name: string;
  ledger_id: number;
  source: string;
  import_hash: string;
  is_duplicate?: boolean;
  error?: string;
  warnings?: string[];
}

type RecognizeResponse = {
  data:
    | { items: OcrImportItem[]; usage: unknown }
    | {
        scenario: OcrScenario;
        rows: (OcrTxnRow | OcrHoldingRow)[];
        usage: unknown;
      };
  message: string;
};

/** 查询某功能当日 AI 识别剩余次数 */
export const getOcrUsage = (feature: string = "ocr_import") => {
  return http.request<OcrUsageResult>("get", `/api/usage/${feature}`);
};

/** 图片（base64）→ 方案方舟识别 → 候选列表/预览行；消耗 1 次对应场景配额 */
export const recognizeImage = (
  imageBase64: string,
  scenario: OcrScenario = "watchlist_import",
  ledgerId?: number | null
) => {
  const params = buildLedgerParams(ledgerId);
  return http.request<RecognizeResponse>(
    "post",
    "/api/ocr/recognize",
    { data: { image_base64: imageBase64, scenario }, params },
    { timeout: OCR_REQUEST_TIMEOUT }
  );
};

/** 纯文本 → LLM 批量提取（AI 批量导入）；消耗 1 次对应场景配额 */
export const parseImportText = (
  text: string,
  scenario: OcrScenario = "watchlist_import",
  ledgerId?: number | null
) => {
  const params = buildLedgerParams(ledgerId);
  return http.request<RecognizeResponse>(
    "post",
    "/api/ocr/parse",
    { data: { text, scenario }, params },
    { timeout: OCR_REQUEST_TIMEOUT }
  );
};
