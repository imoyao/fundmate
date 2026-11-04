import type { OcrHoldingRow, OcrScenario, OcrTxnRow } from "@/api/ocr";
import type { RecognizerCandidate } from "@/composables/useReconDraft";

/** 预览行：交易行与持仓行的并集，表格按场景取不同列 */
export type PreviewRow = OcrTxnRow | OcrHoldingRow;

/** 输入方式 */
export type ImportTab = "image" | "text";

/** 场景切换（决定落入域 C / 域 A）；scenarioLock 时整组隐藏 */
export type ScenarioOption = Extract<
  OcrScenario,
  "txn_import" | "holding_import"
>;

/** 显式标注取值类型，供 SegmentedControl 泛型推断（数组字面量会把 value 拓宽成 string） */
export const SCENARIO_OPTIONS: { label: string; value: ScenarioOption }[] = [
  { label: "交易识别", value: "txn_import" },
  { label: "持仓识别", value: "holding_import" }
];

export const IMPORT_TAB_OPTIONS: { label: string; value: ImportTab }[] = [
  { label: "上传图片", value: "image" },
  { label: "粘贴文本", value: "text" }
];

/** 剩余次数低于此值即提示「额度紧张」 */
export const LOW_QUOTA = 2;
/** 拉取额度失败时的兜底值 */
export const DEFAULT_QUOTA = 5;
/** 额度用尽的门槛（后端 remaining 可能返回负） */
const EMPTY_QUOTA = 0;

/** 额度条提示文案（三态：正常留空 / 紧张 / 用尽） */
export function usageHintOf(remaining: number, occupied: boolean): string {
  if (occupied) return "额度已用尽，请明日再试";
  if (remaining <= LOW_QUOTA) return "额度紧张，谨慎使用";
  return "";
}

/** 额度条状态类名（驱动配色） */
export function usageStateClassOf(
  remaining: number,
  occupied: boolean
): "" | "is-low" | "is-used-up" {
  if (occupied) return "is-used-up";
  if (remaining <= LOW_QUOTA) return "is-low";
  return "";
}

/** 额度条图标 */
export function usageIconOf(remaining: number, occupied: boolean): string {
  if (occupied) return "ep:warning";
  if (remaining <= LOW_QUOTA) return "ep:bell";
  return "ep:magic-stick";
}

/** 场景 → 用量统计的 feature key */
export function usageFeatureOf(scenario: ScenarioOption): string {
  return scenario === "txn_import" ? "txn_import" : "holding_import";
}

/** 「开始识别」是否可点：额度 + 当前输入方式是否已有内容 */
export function canRecognizeOf(input: {
  remaining: number;
  occupied: boolean;
  tab: ImportTab;
  hasImage: boolean;
  text: string;
}): boolean {
  if (input.occupied || input.remaining <= EMPTY_QUOTA) return false;
  if (input.tab === "image") return input.hasImage;
  return input.text.trim().length > 0;
}

/** 识别失败的错误对象形态（axios 响应 + 可能的业务码） */
export type RecognizeError = {
  response?: { status?: number; data?: { message?: string } };
  code?: string;
  message?: string;
};

/**
 * 识别失败提示：503 / 超时都**不消耗次数**，措辞必须点明这一点（用户据此决定是否重试）。
 * 返回 level 供调用方决定弹 warning 还是 error。
 */
export function recognizeFailureOf(e: unknown): {
  message: string;
  level: "warning" | "error";
} {
  const err = e as RecognizeError;
  const status = err.response?.status;
  if (status === 503) {
    return {
      message: "AI 识别服务暂时繁忙，请稍后重试（失败不消耗次数）",
      level: "error"
    };
  }
  if (status === 429) {
    return {
      message:
        err.response?.data?.message || "今日 AI 识别次数已用完，请明日再试",
      level: "warning"
    };
  }
  if (err.code === "ECONNABORTED" || err.message?.includes("timeout")) {
    return {
      message: "识别超时，请稍后重试（失败不消耗次数）",
      level: "error"
    };
  }
  return {
    message: err.response?.data?.message || err.message || "识别失败，请重试",
    level: "error"
  };
}

/** 场景 → 对账域：交易进域 C（对账单），持仓进域 A（E账户） */
export function domainOf(scenario: ScenarioOption): "A" | "C" {
  return scenario === "txn_import" ? "C" : "A";
}

/** 场景 → 候选行 kind 标记（工作台按 kind 路由） */
function kindOf(scenario: ScenarioOption): "txn" | "holding" {
  return scenario === "txn_import" ? "txn" : "holding";
}

/**
 * 预览行 → 草稿候选行。
 * 交易场景把关联账户 id 直接打入候选行，提交时无需再次选择（域 C 按账本隔离）。
 */
export function buildCandidates(
  rows: PreviewRow[],
  scenario: ScenarioOption,
  ledgerId: number | null
): RecognizerCandidate[] {
  const kind = kindOf(scenario);
  return rows.map(r => {
    // 深拷贝成纯对象：预览行存在 `ref` 里，嵌套数组（如 warnings）会被 Vue 包成 Proxy，
    // 而 IndexedDB 的 structured clone 不接受 Proxy —— 带 warnings 的交易行会在
    // 「确认进草稿」时抛 DataCloneError，表现为点了没反应（持仓行无嵌套字段，故不发作）。
    const base = JSON.parse(JSON.stringify({ ...r, kind })) as Record<
      string,
      unknown
    >;
    if (scenario === "txn_import" && ledgerId) {
      base.ledger_id = ledgerId;
    }
    return base as unknown as RecognizerCandidate;
  });
}

/** 额度为 0 时点「开始识别」的提示（文本通道与图片通道共用） */
export const EMPTY_QUOTA_HINT = "今日 AI 识别额度已用完，请明日再试";

/** 图片 → base64（去掉 `data:...;base64,` 前缀） */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(",")[1] ?? result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
