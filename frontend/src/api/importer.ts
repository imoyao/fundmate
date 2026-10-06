import { http } from "@/utils/http";
import type { OcrHoldingRow } from "@/api/ocr";

/** 导入预览行（对齐后端 _rows_from_records 输出；提交 /confirm 时原样回传） */
export interface ImportPreviewRow {
  symbol: string;
  name: string;
  /** 资产类型（stock/fund/cash 等） */
  type: string;
  /** 产品细分类型（如「混合型」「货币型」，仅展示用） */
  display_type: string;
  /** 标准化交易类型（小写） */
  op_type: string;
  /** 交易类型中文标签 */
  op_type_label: string;
  quantity: number;
  price: number;
  amount: number;
  fee: number;
  /** 确认日期 YYYY-MM-DD，解析失败为空串 */
  trade_date: string;
  account_name: string;
  /** 回传 confirm 用：缺了它落库不挂账户且去重失效（#1010） */
  ledger_id: number | null;
  /** 平台交易流水号 */
  contract_id: string;
  is_cash_transfer: boolean;
  /** 解析错误信息；正常行为 null */
  error: string | null;
  import_hash: string;
  is_duplicate: boolean;
  /** 配置目标（现金类默认 liquid，其余 null） */
  allocation: string | null;
  /** 关联交易组 id（同一笔交易的配对行共享） */
  link_group_id: string | null;
  /** 原始成交金额（同花顺专用） */
  trade_amount: number;
  /** 净发生金额绝对值（同花顺专用） */
  net_amount: number;
  /** 原始中文操作类型 */
  notes: string;
  source: string;
  /** 份额/净值是否为系统自动推算 */
  is_calculated: boolean;
}

/** 确认入库行（POST /api/importers/confirm/）。后端 commit_from_preview 除 symbol 硬索引外
 *  全部字段 .get() 兜底（缺省 = 不跳过 / 0 / 空串 / null），故仅 symbol 必填：
 *  解析预览行（ImportPreviewRow）与 OCR 识别候选行（剥 kind 后）均可直接回传。 */
export interface ImportConfirmRow {
  symbol: string;
  name?: string;
  type?: string;
  op_type?: string;
  quantity?: number;
  price?: number;
  amount?: number;
  fee?: number;
  trade_date?: string;
  account_name?: string;
  /** 缺了它落库不挂账户且去重失效（#1010） */
  ledger_id?: number | null;
  contract_id?: string;
  is_cash_transfer?: boolean;
  error?: string | null;
  import_hash?: string;
  is_duplicate?: boolean;
  /** #1882：疑似重复且被用户勾选保留 → 后端按「真插入」落库（仅 is_duplicate 行有意义） */
  keep_duplicate?: boolean;
  allocation?: string | null;
  source?: string;
  net_amount?: number;
}

/** 文件解析响应（对齐后端 /parse/） */
export interface ImportParseResponse {
  data: ImportPreviewRow[];
  total: number;
  error_count: number;
  duplicate_count: number;
  cash_transfer_count: number;
  message: string;
}

/** 确认导入的单条错误（对齐 commit_from_preview 的 errors 项） */
export interface ImportErrorItem {
  symbol: string;
  name: string;
  error: string;
}

/** 确认导入统计（对齐 commit_from_preview 返回 dict） */
export interface ImportCommitResult {
  imported: number;
  skipped: number;
  orphan_count: number;
  errors: ImportErrorItem[];
  /** 银证转账在关联现金账户侧生成的反向记录数（#1010） */
  cash_transfers_created: number;
  /** 勾选保留的疑似重复行实际入库数（#1882 决策 (a) 真插入） */
  kept_duplicates: number;
  /** 勾选保留但被去重规则拦截数（此前已保留过，幂等跳过，#1882） */
  kept_duplicates_blocked: number;
}

/** 确认导入响应 */
export interface ImportCommitResponse {
  data: ImportCommitResult;
  message: string;
}

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
  return http.request<ImportParseResponse>(
    "post",
    `/api/importers/parse/?${params.toString()}`,
    {
      data: formData,
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 10000
    }
  );
}

/** 确认导入选中的交易记录（预览行原样回传，后端按 is_duplicate/error 分流） */
export function confirmImport(rows: ImportConfirmRow[]) {
  return http.request<ImportCommitResponse>("post", "/api/importers/confirm/", {
    data: rows
  });
}

/** 确认导入持仓快照（holding_import）：SET 语义 upsert 至 positions，不建交易流水（#1018） */
export function confirmHoldingImport(rows: OcrHoldingRow[]) {
  return http.request<HoldingImportResponse>(
    "post",
    "/api/importers/holdings/confirm/",
    {
      data: rows
    }
  );
}
