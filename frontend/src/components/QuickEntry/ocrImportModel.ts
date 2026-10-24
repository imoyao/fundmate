/**
 * AI 批量导入弹窗的模型层（纯函数，零 Vue 依赖）。
 *
 * 从 OcrImportModal.vue 抽出的三件事，都恰好是「输出必须逐字不变」的部分：
 * 候选列表的派生（哪些已存在、默认勾不勾）、创建自选条目的请求体（符号兜底 /
 * 类型兜底 / 分组数组拷贝）、导入结果的一句话文案（成功 / 有失败的两种措辞）。
 * 放在这里就能用 vitest 钉住，而不必等到真跑一次导入。
 */

import type { OcrImportItem } from "@/api/ocr";
import type { WatchlistItemCreateInput } from "@/api/watchlist";

/** 待勾选候选：后端识别结果 + 前端派生的两个状态位 */
export type OcrCandidate = OcrImportItem & {
  /** 已在自选（置灰、不可勾、不参与导入） */
  exists: boolean;
  selected: boolean;
};

/** 导入方式分段选项：显式标注取值类型，供 SegmentedControl 泛型推断 */
export const IMPORT_TAB_OPTIONS: { label: string; value: "image" | "text" }[] =
  [
    { label: "上传图片", value: "image" },
    { label: "粘贴文本", value: "text" }
  ];

/** 导入理由（写进自选条目的 add_reason，便于日后回溯这批资产的来源） */
export const OCR_IMPORT_REASON = "AI 批量导入";

/**
 * 识别结果 → 候选列表。
 * 已存在的按 `symbol || code` 命中：命中则置灰且**默认不勾**（用户刚识别一批，
 * 默认全勾会把「已存在」也一起提交，白跑一遍 409）。
 */
export function buildCandidates(
  items: OcrImportItem[],
  existing: Set<string>
): OcrCandidate[] {
  return items.map(it => {
    const key = it.symbol || it.code;
    const exists = existing.has(key);
    return { ...it, exists, selected: !exists };
  });
}

/**
 * 单条候选 → 创建自选条目的请求体。
 *
 * 透传后端反查的 type/market/venue/symbol，**不按 code 前缀猜类型**——
 * 否则股票 600519 / 深市 ETF 159915 会被误判成场外基金导入。
 */
export function buildCreatePayload(
  item: OcrImportItem,
  groupIds: readonly number[]
): WatchlistItemCreateInput {
  return {
    symbol: item.symbol || item.code,
    // 名称快照（#1508）：OCR 识别结果自带 name，随创建落库
    name: item.name,
    asset_type: item.type || "fund",
    market: item.market,
    venue: item.venue || "OTC",
    add_reason: OCR_IMPORT_REASON,
    // #2106：导入时勾选的自定义分组（空数组 = 不分组，行为与不带该字段一致）
    group_ids: [...groupIds]
  };
}

export type OcrImportOutcome = {
  success: number;
  skipped: number;
  /** 失败条目的代码（用于文案里点名） */
  failed: string[];
};

/**
 * 导入结果 → 提示文案 + 提示级别。
 * 有失败走 error（并把失败代码逐个点名），全成功走 success（跳过数仅在非零时出现）。
 */
export function summarizeImport({
  success,
  skipped,
  failed
}: OcrImportOutcome): { level: "success" | "error"; message: string } {
  if (failed.length > 0) {
    return {
      level: "error",
      message: `导入完成：成功 ${success} 条，跳过已存在 ${skipped} 条，失败 ${
        failed.length
      } 条（${failed.join("、")}）`
    };
  }
  return {
    level: "success",
    message: `导入成功 ${success} 条${
      skipped > 0 ? `，跳过已存在 ${skipped} 条` : ""
    }`
  };
}
