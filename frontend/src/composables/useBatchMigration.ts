import { ref, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { formatDate } from "@/utils/date";
import {
  previewLedgerMigration,
  commitLedgerMigration,
  type LedgerItem,
  type SalesInstitution,
  type MigrationPreviewItem,
  type MigrationPreviewResult,
  type MigrationAction,
  type MigrationResolution,
  type MigrationCommitPayload,
  type MigrationCommitResult,
  type MigrationConservation
} from "@/api/ledger";

export interface UseBatchMigrationProps {
  ledgers: LedgerItem[];
  accountInfo: LedgerItem | null;
  salesInstitutions: SalesInstitution[];
  ledgerId: string;
  accountName: string;
  sameTypeLedgers: LedgerItem[];
}

export interface UseBatchMigrationOptions {
  onCommitted: () => void;
}

// ── 批量迁移（两段式）：preview 只读出分类与冲突，用户在决议面板逐条选择后 commit ──

/** 冲突行唯一键：持仓按 symbol，资产按名称+两级分类（与 commit 决议定位口径一致） */
export function migrationRowKey(item: MigrationPreviewItem): string {
  return item.kind === "position"
    ? `position:${item.symbol}`
    : `asset:${item.name}|${item.major_category ?? ""}|${item.minor_category ?? ""}`;
}

/** 未绑定销售机构的统一提示文案（源或候选任一缺失时展示） */
export const MIGRATION_UNBOUND_HINT =
  "该账户未绑定销售机构，建议先在账户设置中绑定，便于同机构自动归账";

export interface MigrationTargetOption {
  ledger: LedgerItem;
  /** 绑定的销售机构 id（null=未绑定） */
  institutionId: number | null;
  /** 销售机构展示名（未绑定或名录缺失时为空串） */
  institutionName: string;
  /** 与源账本绑定同一销售机构 */
  sameInstitution: boolean;
}

/** 机构 id → 展示名（AMAC 名录，display_name 优先） */
export function salesInstitutionName(
  id: number | null | undefined,
  salesInstitutions: SalesInstitution[]
): string {
  if (!id) return "";
  const inst = salesInstitutions.find(s => s.id === id);
  return inst?.display_name || inst?.org_name || "";
}

/**
 * 字段术语按资产类型区分（基金与股票是两个概念，各用专业口径）：
 * fund → 确认份额/确认净值/确认日期；stock 及其他非基金类型 → 持仓数量/成本价/成本日期。
 */
export interface MigrationFieldTerms {
  quantity: string;
  avgPrice: string;
  confirmDate: string;
  /** 数量单位：基金为份，股票等为股 */
  quantityUnit: string;
  /** 合并说明中的加权平均措辞 */
  weightedAvgLabel: string;
  /** 合并说明中的日期取新措辞 */
  dateNewerLabel: string;
}

export const FUND_FIELD_TERMS: MigrationFieldTerms = {
  quantity: "确认份额",
  avgPrice: "确认净值",
  confirmDate: "确认日期",
  quantityUnit: "份",
  weightedAvgLabel: "确认净值加权平均",
  dateNewerLabel: "确认日期取较新"
};

export const STOCK_FIELD_TERMS: MigrationFieldTerms = {
  quantity: "持仓数量",
  avgPrice: "成本价",
  confirmDate: "成本日期",
  quantityUnit: "股",
  weightedAvgLabel: "成本加权平均",
  dateNewerLabel: "成本日期取较新"
};

/** 基金类持仓判定：仅 asset_type=fund 走净值口径，其余一律按数量/成本价口径 */
export function isFundPosition(item: MigrationPreviewItem): boolean {
  return item.kind === "position" && item.asset_type === "fund";
}

export function positionTerms(item: MigrationPreviewItem): MigrationFieldTerms {
  return isFundPosition(item) ? FUND_FIELD_TERMS : STOCK_FIELD_TERMS;
}

/** 冲突字段中文名（对比表与「不一致字段」标签共用），资产行只有金额 */
export function fieldLabels(
  item: MigrationPreviewItem
): Record<string, string> {
  const terms = positionTerms(item);
  return {
    quantity: terms.quantity,
    avg_price: terms.avgPrice,
    confirm_date: terms.confirmDate,
    amount: "金额"
  };
}

export function diffFieldLabels(item: MigrationPreviewItem): string {
  const labels = fieldLabels(item);
  return (item.conflict_fields ?? []).map(f => labels[f] ?? f).join("、");
}

/**
 * 数字展示：至少 2 位小数（对齐设计规范）、最多 4 位——
 * 对比场景需区分 0.0001 份级差异，避免「显示相等实则不等」误导决议。
 */
export function formatMigrationNumber(value: number, digits = 2): string {
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: 4
  });
}

export function formatMigrationAmount(value: number): string {
  return `¥${value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}

/** keep/duplicate 行的数值摘要：持仓按类型取术语（基金净值口径/股票成本口径），资产展示金额 */
export function snapshotSummary(item: MigrationPreviewItem): string {
  if (item.kind === "asset") {
    return formatMigrationAmount(item.source.amount);
  }
  const terms = positionTerms(item);
  const parts = [
    `${formatMigrationNumber(item.source.quantity)} ${terms.quantityUnit}`,
    `${terms.avgPrice} ${formatMigrationNumber(item.source.avg_price)} 元`
  ];
  if (item.source.confirm_date)
    parts.push(formatDate(item.source.confirm_date));
  return parts.join(" · ");
}

export interface MigrationCompareCell {
  key: string;
  label: string;
  source: string;
  target: string;
  /** 该字段在 conflict_fields 中 → 双方数值均高亮警示 */
  diff: boolean;
}

/** 源/目标并排对比单元格：持仓按类型比数量/成本（净值）/日期，资产只比金额 */
export function compareCells(
  item: MigrationPreviewItem
): MigrationCompareCell[] {
  const conflicts = item.conflict_fields ?? [];
  const labels = fieldLabels(item);
  if (item.kind === "asset") {
    return [
      {
        key: "amount",
        label: labels.amount,
        source: formatMigrationAmount(item.source.amount),
        target: item.target ? formatMigrationAmount(item.target.amount) : "—",
        diff: conflicts.includes("amount")
      }
    ];
  }
  const fmtDate = (d: string | null) => (d ? formatDate(d) : "—");
  return [
    {
      key: "quantity",
      label: labels.quantity,
      source: formatMigrationNumber(item.source.quantity),
      target: item.target ? formatMigrationNumber(item.target.quantity) : "—",
      diff: conflicts.includes("quantity")
    },
    {
      key: "avg_price",
      label: labels.avg_price,
      source: formatMigrationNumber(item.source.avg_price),
      target: item.target ? formatMigrationNumber(item.target.avg_price) : "—",
      diff: conflicts.includes("avg_price")
    },
    {
      key: "confirm_date",
      label: labels.confirm_date,
      source: fmtDate(item.source.confirm_date),
      target: item.target ? fmtDate(item.target.confirm_date) : "—",
      diff: conflicts.includes("confirm_date")
    }
  ];
}

export const MIGRATION_ACTION_LABELS: Record<MigrationAction, string> = {
  keep_source: "保留源",
  keep_target: "保留目标",
  merge: "合并"
};

/** 决议选项：持仓三选，资产无合并语义仅二选（§5.2） */
export function actionOptions(item: MigrationPreviewItem): {
  value: MigrationAction;
  label: string;
}[] {
  const base = [
    {
      value: "keep_source" as const,
      label: MIGRATION_ACTION_LABELS.keep_source
    },
    {
      value: "keep_target" as const,
      label: MIGRATION_ACTION_LABELS.keep_target
    }
  ];
  return item.kind === "position"
    ? [
        ...base,
        { value: "merge" as const, label: MIGRATION_ACTION_LABELS.merge }
      ]
    : base;
}

/**
 * 合并预计结果（§5.2.1 展示口径）：数量相加、加权平均（四舍五入到分）、日期取较新。
 * 措辞按资产类型切换（基金：确认净值加权平均/确认日期取较新；股票等：成本加权平均/成本日期取较新）。
 * 仅为选中态说明文案，入库口径以后端整数运算为准。
 */
export function mergeNote(item: MigrationPreviewItem): string {
  if (item.kind !== "position") return "";
  const terms = positionTerms(item);
  const qSrc = item.source.quantity;
  const pSrc = item.source.avg_price;
  const qTgt = item.target?.quantity ?? 0;
  const pTgt = item.target?.avg_price ?? 0;
  const qty = qSrc + qTgt;
  // 展示口径允许浮点四舍五入到分；非入库计算路径
  const price =
    qty > 0 ? Math.round(((qSrc * pSrc + qTgt * pTgt) / qty) * 100) / 100 : 0;
  const newestDate = [item.source.confirm_date, item.target?.confirm_date]
    .filter((d): d is string => !!d)
    .sort()
    .pop();
  const parts = [
    `合并后：${formatMigrationNumber(qty)} ${terms.quantityUnit}`,
    `${terms.weightedAvgLabel}：${formatMigrationNumber(price)} 元`
  ];
  if (newestDate)
    parts.push(`${terms.dateNewerLabel}：${formatDate(newestDate)}`);
  return parts.join(" · ");
}

/** 当前决议的说明文案：merge 展示预计结果，二选一展示动作含义 */
export function actionNote(
  item: MigrationPreviewItem,
  action: MigrationAction | undefined
): string {
  if (!action) return "";
  if (action === "keep_source") return "以来源数值写入目标账户，目标原值被覆盖";
  if (action === "keep_target") return "保留目标数值，来源这笔不迁入";
  return mergeNote(item);
}

export function useBatchMigration(
  props: UseBatchMigrationProps,
  opts: UseBatchMigrationOptions
) {
  const batchMigrateVisible = ref(false);
  const batchTargetLedgerId = ref<number | null>(null);
  const migrationPanelVisible = ref(false);
  const migrationPreviewLoading = ref(false);
  const migrationCommitting = ref(false);
  const migrationPreview = ref<MigrationPreviewResult | null>(null);
  /** conflict 行决议表：行键 → 动作；打开面板时按系统建议初始化（§7 默认选中 suggestion） */
  const resolutions = ref<Record<string, MigrationAction>>({});

  const previewItems = computed(() => migrationPreview.value?.items ?? []);
  const keepItems = computed(() =>
    previewItems.value.filter(i => i.classification === "keep")
  );
  const duplicateItems = computed(() =>
    previewItems.value.filter(i => i.classification === "duplicate")
  );
  const conflictItems = computed(() =>
    previewItems.value.filter(i => i.classification === "conflict")
  );

  /** 未决议数：全部归零前「确认迁移」保持禁用 */
  const pendingCount = computed(
    () =>
      conflictItems.value.filter(
        item => !resolutions.value[migrationRowKey(item)]
      ).length
  );

  const targetLedgerName = computed(
    () =>
      props.ledgers.find(l => l.id === batchTargetLedgerId.value)?.name ||
      "目标账户"
  );

  /** 跨机构迁移放行标记：二次确认通过后置位，commit 时随请求携带 */
  const allowCrossInstitution = ref(false);

  /**
   * 批量迁移目标候选：同销售机构优先（软优先策略）——
   * 同机构候选排最前并标注机构名，其余保持原排序；不禁止跨机构，仅影响排序与默认选中。
   */
  const batchTargetOptions = computed<MigrationTargetOption[]>(() => {
    const sourceInstId = props.accountInfo?.sales_institution_id ?? null;
    const candidates = props.sameTypeLedgers.map(l => ({
      ledger: l,
      institutionId: l.sales_institution_id ?? null,
      institutionName: salesInstitutionName(
        l.sales_institution_id,
        props.salesInstitutions
      ),
      sameInstitution:
        !!sourceInstId &&
        !!l.sales_institution_id &&
        l.sales_institution_id === sourceInstId
    }));
    // 稳定分组：同机构在前，其余保持原顺序
    return [
      ...candidates.filter(c => c.sameInstitution),
      ...candidates.filter(c => !c.sameInstitution)
    ];
  });

  /** 未绑定提示：已选目标或源账本缺销售机构绑定时给出归账建议 */
  const migrationBindingHint = computed(() => {
    const selected = batchTargetOptions.value.find(
      o => o.ledger.id === batchTargetLedgerId.value
    );
    if (
      (selected && !selected.institutionId) ||
      !props.accountInfo?.sales_institution_id
    ) {
      return MIGRATION_UNBOUND_HINT;
    }
    return "";
  });

  /** 跨机构判定：优先用 preview 返回的 institution 块；旧响应缺块时按本地绑定关系兜底 */
  function resolveCrossInstitution(preview: MigrationPreviewResult): boolean {
    if (preview.institution) return preview.institution.cross_institution;
    const sourceInstId = props.accountInfo?.sales_institution_id ?? null;
    const targetInstId =
      props.ledgers.find(l => l.id === batchTargetLedgerId.value)
        ?.sales_institution_id ?? null;
    return !!sourceInstId && !!targetInstId && sourceInstId !== targetInstId;
  }

  /** 底栏状态文案：未决议时提示剩余量，就绪后预告将执行的动作计数 */
  const footerStatusText = computed(() => {
    if (pendingCount.value > 0) {
      return `还有 ${pendingCount.value} 项待决议，决议完成后方可确认`;
    }
    const parts = [`${keepItems.value.length} 项直接迁移`];
    if (duplicateItems.value.length)
      parts.push(`${duplicateItems.value.length} 项丢弃重复`);
    if (conflictItems.value.length)
      parts.push(`${conflictItems.value.length} 项按决议处理`);
    return `已就绪：${parts.join("，")}`;
  });

  /** 默认决议：跟随系统建议（§5.2）；建议缺失或对行类型无意义时取安全兜底 */
  function defaultResolution(item: MigrationPreviewItem): MigrationAction {
    const suggestion = item.suggestion;
    if (item.kind === "position") {
      return suggestion === "keep_target" || suggestion === "merge"
        ? suggestion
        : "merge";
    }
    // 资产无合并语义：默认保留源值（迁移语义是把源数据并入目标）
    return suggestion === "keep_target" ? "keep_target" : "keep_source";
  }

  function applyDefaultResolutions(items: MigrationPreviewItem[]) {
    const map: Record<string, MigrationAction> = {};
    for (const item of items) {
      if (item.classification !== "conflict") continue;
      map[migrationRowKey(item)] = defaultResolution(item);
    }
    resolutions.value = map;
  }

  /** 守恒结果转文案（成功提示用；未知键原样输出键名） */
  function conservationText(conservation?: MigrationConservation): string {
    if (!conservation) return "";
    const labels: Record<string, string> = {
      source_out_positions: "源账本迁出份额",
      target_in_positions: "目标账本迁入份额",
      source_out_assets: "源账本迁出金额",
      target_in_assets: "目标账本迁入金额"
    };
    const parts: string[] = [];
    for (const [key, value] of Object.entries(conservation)) {
      if (typeof value !== "number") continue;
      parts.push(`${labels[key] ?? key} ${formatMigrationNumber(value)}`);
    }
    return parts.join("，");
  }

  /** 成功提示：各项计数 + 守恒结果；后端计数缺省时降级用本地预览计数 */
  function commitSuccessMessage(result?: MigrationCommitResult): string {
    const total = result?.total ?? previewItems.value.length;
    const parts = [`共处理 ${total} 项`];
    if (result?.position_count != null)
      parts.push(`持仓 ${result.position_count} 项`);
    if (result?.asset_count != null)
      parts.push(`资产 ${result.asset_count} 项`);
    const conservation = conservationText(result?.conservation);
    if (conservation) parts.push(conservation);
    return `迁移完成：${parts.join("，")}`;
  }

  /** 第一步：调 preview 拉取迁移方案（只读不写库），成功后进入决议面板 */
  async function handlePreviewMigration() {
    if (!batchTargetLedgerId.value) return;
    migrationPreviewLoading.value = true;
    try {
      const res = await previewLedgerMigration(
        Number(props.ledgerId),
        batchTargetLedgerId.value
      );
      const data = res.data ?? { items: [] };
      // 跨机构目标需二次确认；取消则停留在选择步，不进入决议面板
      if (resolveCrossInstitution(data)) {
        try {
          await ElMessageBox.confirm(
            "来源账户与目标账户绑定了不同销售机构。跨机构迁移会使交易归属与销售机构口径不一致，建议优先迁移到同机构账户。确定继续？",
            "跨机构迁移确认",
            {
              confirmButtonText: "继续迁移",
              cancelButtonText: "返回重选",
              type: "warning"
            }
          );
          allowCrossInstitution.value = true;
        } catch {
          // 用户取消：留在选择步重选目标
          return;
        }
      } else {
        allowCrossInstitution.value = false;
      }
      migrationPreview.value = data;
      applyDefaultResolutions(data.items);
      batchMigrateVisible.value = false;
      migrationPanelVisible.value = true;
    } catch (e) {
      const err = e as { response?: { data?: { message?: string } } };
      ElMessage.error(err?.response?.data?.message || "预览失败，请稍后再试");
    } finally {
      migrationPreviewLoading.value = false;
    }
  }

  /** 由决议表组装 commit 入参：持仓按 symbol 三选一，资产按三级分类键二选一 */
  function buildResolutions(): MigrationResolution[] {
    const list: MigrationResolution[] = [];
    for (const item of conflictItems.value) {
      const action = resolutions.value[migrationRowKey(item)];
      // 决议齐备才允许提交（按钮禁用兜底），此分支仅为类型收窄
      if (!action) continue;
      if (item.kind === "position") {
        list.push({ kind: "position", symbol: item.symbol, action });
      } else {
        list.push({
          kind: "asset",
          name: item.name,
          major_category: item.major_category ?? "",
          minor_category: item.minor_category ?? "",
          // 资产行无合并选项；状态异常落入 merge 时归一到保留源
          action: action === "merge" ? "keep_source" : action
        });
      }
    }
    return list;
  }

  /** 第二步：全部 conflict 决议完成后提交（单事务，失败整体回滚） */
  async function handleCommitMigration() {
    if (!batchTargetLedgerId.value || pendingCount.value > 0) return;
    migrationCommitting.value = true;
    try {
      const payload: MigrationCommitPayload = {
        target_ledger_id: batchTargetLedgerId.value,
        resolutions: buildResolutions()
      };
      // 跨机构迁移仅在用户二次确认后携带放行标记
      if (allowCrossInstitution.value) payload.allow_cross_institution = true;
      const res = await commitLedgerMigration(Number(props.ledgerId), payload);
      migrationPanelVisible.value = false;
      ElMessage.success(commitSuccessMessage(res.data));
      opts.onCommitted();
    } catch (e) {
      const err = e as { response?: { data?: { message?: string } } };
      ElMessage.error(err?.response?.data?.message || "迁移失败，源数据未变更");
    } finally {
      migrationCommitting.value = false;
    }
  }

  function openBatchMigrateDialog() {
    // 同机构软优先：存在同机构候选时默认选中第一个，减少跨机构误选
    const firstSame = batchTargetOptions.value.find(o => o.sameInstitution);
    batchTargetLedgerId.value = firstSame ? firstSame.ledger.id : null;
    allowCrossInstitution.value = false;
    migrationPreview.value = null;
    resolutions.value = {};
    batchMigrateVisible.value = true;
  }

  return {
    batchMigrateVisible,
    batchTargetLedgerId,
    migrationPanelVisible,
    migrationPreviewLoading,
    migrationCommitting,
    migrationPreview,
    resolutions,
    allowCrossInstitution,
    previewItems,
    keepItems,
    duplicateItems,
    conflictItems,
    pendingCount,
    targetLedgerName,
    batchTargetOptions,
    migrationBindingHint,
    footerStatusText,
    handlePreviewMigration,
    buildResolutions,
    handleCommitMigration,
    openBatchMigrateDialog
  };
}
