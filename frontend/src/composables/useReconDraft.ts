import { localForage } from "@/utils/localforage";

/**
 * 统一对账工作台草稿层（#1232 P0-B / #1239）。
 *
 * 设计（对齐 docs/working-notes/reconciliation-framework-design-2026-08-31.md §5.7）：
 * - **全局单槽**：key = `recon-draft:<familyId>`（前端当前无 familyId 暴露，localforage 本身
 *   已按浏览器实例隔离，故退化为固定 key `recon-draft`；后续多家庭需在此拼接家庭标识）。
 *   真正"只存一份"，靠 payload.domain + ledgerId 路由恢复。
 * - **payload 必须带 domain 标记**（A/E账户、B/快照一致性、C/对账单交割单导入），
 *   避免跨域恢复时类型错乱（§5.8）。
 * - **TTL 7 天**（localforage 单位为分钟，7×24×60=10080）；过期仅影响未提交编辑态。
 * - **不存文件二进制**：只存解析结果——恢复后无法重新解析，行内编辑是刚需。
 *
 * Set 序列化：`selectedKeys` 是 `Set`（不可 JSON 序列化），写入转数组、读取转回 Set。
 */

export type ReconDomain = "A" | "B" | "C";

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
  rows: any[];
  /** 交易导入专用：勾选键（Set 序列化后的数组） */
  selectedKeys?: string[];
  /** 交易导入专用：账本上下文 */
  selectedLedgerId?: number | null;
  /** 交易导入专用：导入模板（standard_fund/ths/...） */
  selectedMode?: string;
}

const KEY_PREFIX = "recon-draft";
const TTL_MINUTES = 7 * 24 * 60; // 7 天

/** 当前草稿 key：前端无 familyId，localforage 已按浏览器实例隔离，退化为固定 key */
const draftKey = (): string => `${KEY_PREFIX}`;

/** 序列化前清洗 rows：剥离不可 JSON 化的字段（函数/循环引用），保留行内编辑所需字段 */
function sanitizeRows(rows: any[]): any[] {
  return rows.map(row => {
    const copy: Record<string, any> = {};
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
  rows: any[];
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
    rows: any[];
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

  return {
    saveDraft,
    getDraft,
    getDraftWithSet,
    discardDraft,
    hasDraft
  };
}
