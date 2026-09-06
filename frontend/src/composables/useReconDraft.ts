import { localForage } from "@/utils/localforage";
import type { OcrTxnRow, OcrHoldingRow } from "@/api/ocr";

/**
 * 统一对账工作台草稿层（#1232 P0-B / #1239）。
 *
 * 设计（对齐 docs/working-notes/reconciliation-framework-design-2026-08-31.md §5.7）：
 * - **导入草稿全局单槽**：key = `recon-draft`（前端当前无 familyId 暴露，localforage 本身
 *   已按浏览器实例隔离，故退化为固定 key；后续多家庭需在此拼接家庭标识）。
 *   真正"只存一份"，靠 payload.domain + ledgerId 路由恢复。
 * - **识别候选草稿独立槽**：key = `recon-draft:recognizer`（P3-1 / #1250），与导入草稿
 *   **按 key 隔离互不覆盖**；识别候选行（AI 识图/文本产出）落入此槽，由工作台三域 Tab 加载。
 * - **payload 必须带 domain 标记**（A/E账户、B/快照一致性、C/对账单交割单导入），
 *   避免跨域恢复时类型错乱（§5.8）。
 * - **TTL 7 天**（localforage 单位为分钟，7×24×60=10080）；过期仅影响未提交编辑态。
 * - **不存文件二进制**：只存解析结果——恢复后无法重新解析，行内编辑是刚需。
 *
 * Set 序列化：`selectedKeys` 是 `Set`（不可 JSON 序列化），写入转数组、读取转回 Set。
 *
 * 识别候选契约（#1250 / P3-1）：AI 识别结果（txn_import / holding_import 场景）经预览核对后，
 * 序列化为 `RecognizerCandidate` 落入 `recon-draft:recognizer` 草稿，与导入向导共享
 * `recon-draft` 命名空间，但 key 不同故互不覆盖；工作台按 `kind`（txn→域 C / holding→域 A）
 * 加载并参与对账。
 */

export type ReconDomain = "A" | "B" | "C";

/** AI 识别候选类型：交易（→域 C）/ 持仓（→域 A） */
export type RecognizerCandidateKind = "txn" | "holding";

/**
 * 识别候选行（#1250）。直接复用 OCR 预览行结构（OcrTxnRow / OcrHoldingRow），
 * 仅附加 `kind` 标记以便工作台路由到对应域。提交入库时剥离 `kind` 即可原样回传
 * `/api/importers/confirm`（txn）或 `/api/importers/holdings/confirm`（holding）。
 */
export type RecognizerCandidate =
  (OcrTxnRow & { kind: "txn" }) | (OcrHoldingRow & { kind: "holding" });

/** 识别候选草稿 payload（key = `recon-draft:recognizer`） */
export interface RecognizerDraftPayload {
  /** 目标对账域：txn→C（对账单导入）/ holding→A（E账户） */
  domain: ReconDomain;
  /** 关联账户 ID（txn 场景需要，holding 场景后端自动归到 E账户） */
  ledgerId: number | null;
  /** 保存时间（ISO） */
  savedAt: string;
  /** 候选行（交易/持仓混合，按 kind 区分） */
  candidates: RecognizerCandidate[];
}

/** 对账行：导入解析结果/预览行均为异构键值对，用此类型替代裸 `any` */
export interface ReconRow {
  [key: string]: unknown;
}

export interface ReconDraftPayload {
  /** 对账域：A=E账户 / B=持仓快照一致性 / C=对账单交割单导入 */
  domain: ReconDomain;
  /** 选中账户 ID（E账户/交易导入均需，用于恢复账本上下文） */
  ledgerId: number | null;
  /** 保存时间（ISO） */
  savedAt: string;
  /** 恢复目标步骤（域内约定：交易导入=2 预览修正，E账户=1 对账结果） */
  currentStep: number;
  /** 解析结果行（交易导入=previewData / E账户=previewRows），行内编辑是刚需 */
  rows: ReconRow[];
  /** 交易导入专用：勾选键（Set 序列化后的数组） */
  selectedKeys?: string[];
  /** 交易导入专用：账本上下文 */
  selectedLedgerId?: number | null;
  /** 交易导入专用：导入模板（standard_fund/ths/...） */
  selectedMode?: string;
}

const KEY_PREFIX = "recon-draft";
const TTL_MINUTES = 7 * 24 * 60; // 7 天

/** 导入草稿 key（全局单槽，与识别候选草稿按 key 隔离，互不覆盖） */
const draftKey = (): string => `${KEY_PREFIX}`;

/** 识别候选草稿 key（P3-1 / #1250）：独立槽，避免覆盖导入草稿 */
const RECOGNIZER_KEY = `${KEY_PREFIX}:recognizer`;

/** 序列化前清洗 rows：剥离不可 JSON 化的字段（函数/循环引用），保留行内编辑所需字段 */
function sanitizeRows(rows: ReconRow[]): ReconRow[] {
  return rows.map(row => {
    const copy: Record<string, unknown> = {};
    for (const key of Object.keys(row)) {
      const v = row[key];
      if (v === undefined || typeof v === "function") continue;
      if (typeof v === "object" && v !== null) {
        // Set/Map 等非 JSON 类型转普通数组/对象，避免序列化丢失
        try {
          JSON.stringify(v);
          copy[key] = v;
        } catch {
          copy[key] = Array.isArray(v) ? v.map(String) : String(v);
        }
      } else {
        copy[key] = v;
      }
    }
    return copy;
  });
}

/** 构建草稿 payload（内部统一清洗 + Set→数组） */
function buildPayload(partial: {
  domain: ReconDomain;
  ledgerId: number | null;
  currentStep: number;
  rows: ReconRow[];
  selectedKeys?: Set<string>;
  selectedLedgerId?: number | null;
  selectedMode?: string;
}): ReconDraftPayload {
  return {
    domain: partial.domain,
    ledgerId: partial.ledgerId,
    savedAt: new Date().toISOString(),
    currentStep: partial.currentStep,
    rows: sanitizeRows(partial.rows),
    selectedKeys: partial.selectedKeys ? [...partial.selectedKeys] : undefined,
    selectedLedgerId: partial.selectedLedgerId ?? partial.ledgerId,
    selectedMode: partial.selectedMode
  };
}

/**
 * 草稿层统一入口。全局单槽：saveDraft 覆盖旧草稿，getDraft 返回唯一一份。
 */
export function useReconDraft() {
  /** 写入草稿（覆盖旧草稿；TTL 7 天） */
  async function saveDraft(payload: {
    domain: ReconDomain;
    ledgerId: number | null;
    currentStep: number;
    rows: ReconRow[];
    selectedKeys?: Set<string>;
    selectedLedgerId?: number | null;
    selectedMode?: string;
  }): Promise<void> {
    await localForage().setItem<ReconDraftPayload>(
      draftKey(),
      buildPayload(payload),
      TTL_MINUTES
    );
  }

  /** 读取草稿；不存在或已过期返回 null */
  async function getDraft(): Promise<ReconDraftPayload | null> {
    const draft = await localForage().getItem<ReconDraftPayload>(draftKey());
    return draft ?? null;
  }

  /** 丢弃草稿（「丢弃草稿」入口） */
  async function discardDraft(): Promise<void> {
    await localForage().removeItem(draftKey());
  }

  /** 是否存在有效草稿 */
  async function hasDraft(): Promise<boolean> {
    return (await getDraft()) !== null;
  }

  /** 读取并把 selectedKeys 数组还原为 Set（交易导入专用） */
  async function getDraftWithSet(): Promise<
    (ReconDraftPayload & { selectedKeySet: Set<string> }) | null
  > {
    const draft = await getDraft();
    if (!draft) return null;
    return { ...draft, selectedKeySet: new Set(draft.selectedKeys ?? []) };
  }

  // ── 识别候选草稿（P3-1 / #1250）：独立槽，与导入草稿按 key 隔离 ──

  /** 写入识别候选草稿（覆盖旧候选；TTL 7 天）。domain 决定工作台路由：txn→C / holding→A */
  async function saveRecognizerCandidates(payload: {
    domain: ReconDomain;
    ledgerId: number | null;
    candidates: RecognizerCandidate[];
  }): Promise<void> {
    // 防御校验：domain 必须与候选 kind 对应，txn 必带 ledgerId，避免按错误域加载/入库
    const kinds = new Set<RecognizerCandidateKind>(
      payload.candidates.map(c => c.kind)
    );
    if (kinds.has("txn") && payload.domain !== "C") {
      throw new Error("txn 候选必须落在域 C（对账单交割单导入）");
    }
    if (kinds.has("holding") && payload.domain !== "A") {
      throw new Error("holding 候选必须落在域 A（E账户）");
    }
    if (kinds.has("txn") && payload.ledgerId == null) {
      throw new Error("txn 候选必须携带 ledgerId 以关联账户");
    }
    await localForage().setItem<RecognizerDraftPayload>(
      RECOGNIZER_KEY,
      {
        domain: payload.domain,
        ledgerId: payload.ledgerId,
        savedAt: new Date().toISOString(),
        candidates: payload.candidates
      },
      TTL_MINUTES
    );
  }

  /** 读取识别候选草稿的候选行；不存在或已过期返回空数组 */
  async function getRecognizerCandidates(): Promise<RecognizerCandidate[]> {
    const draft =
      await localForage().getItem<RecognizerDraftPayload>(RECOGNIZER_KEY);
    return draft?.candidates ?? [];
  }

  /** 读取完整识别候选草稿 payload（含 domain/ledgerId/savedAt）；无则返回 null */
  async function getRecognizerDraft(): Promise<RecognizerDraftPayload | null> {
    return (
      (await localForage().getItem<RecognizerDraftPayload>(RECOGNIZER_KEY)) ??
      null
    );
  }

  /** 丢弃识别候选草稿；传 kind 时仅移除该类型候选，避免误删另一类尚未提交的候选 */
  async function clearRecognizerCandidates(
    kind?: RecognizerCandidateKind
  ): Promise<void> {
    if (kind == null) {
      await localForage().removeItem(RECOGNIZER_KEY);
      return;
    }
    const draft =
      await localForage().getItem<RecognizerDraftPayload>(RECOGNIZER_KEY);
    if (!draft) return;
    const remaining = draft.candidates.filter(c => c.kind !== kind);
    if (remaining.length === 0) {
      await localForage().removeItem(RECOGNIZER_KEY);
    } else {
      await localForage().setItem<RecognizerDraftPayload>(
        RECOGNIZER_KEY,
        { ...draft, candidates: remaining, savedAt: new Date().toISOString() },
        TTL_MINUTES
      );
    }
  }

  /** 是否存在有效识别候选草稿 */
  async function hasRecognizerCandidates(): Promise<boolean> {
    return (await getRecognizerCandidates()).length > 0;
  }

  return {
    saveDraft,
    getDraft,
    getDraftWithSet,
    discardDraft,
    hasDraft,
    saveRecognizerCandidates,
    getRecognizerCandidates,
    getRecognizerDraft,
    clearRecognizerCandidates,
    hasRecognizerCandidates
  };
}
