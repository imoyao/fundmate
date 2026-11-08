/**
 * 预览行管线的纯计算核（#2876 增量 4a）：从 useImportWizard.ts 下沉的
 * 「输入是行数组、输出是数字/分组」的一批纯函数。
 *
 * 设计约束（红线）：
 * - 本文件不 import vue、不读任何 ref / computed / reactive，全部函数只吃入参。
 * - 函数体与历史实现逐字一致，唯一改写是 `previewData.value` → `rows`、
 *   `selectedKeys.value` → `selectedKeys`、`duplicatesHandled.value` → `duplicatesHandled`。
 * - 表格行过滤 `applyRowFilters` **不在此列**：它读 5 个筛选 ref、有 8 条过滤分支，
 *   单独一个增量处理。
 *
 * 跨段依赖说明：`countByCategory` 必须按**显示单元**计数，所以在本模块内部直接调
 * `mergeLinkGroups`——拆成两段由调用方拼会重新引入「概览条 2 条、表格 1 行」的漂移
 * （#2836 实测教训）。
 */

import { getTypeLabel } from "@/constants/assetType";
import {
  categorizeRow,
  isRowBlocked,
  isMissingCode,
  isAmountMismatch,
  hasFixProblem,
  isAutoSelectableRow
} from "./previewPredicates";
import type { FixSectionKey, SectionCounts } from "./batchFixLogic";
import type { PreviewRow } from "./previewRow";

/**
 * link_group 合并（利息 + 税折叠为一条净额行）——分页与计数共用，保证两者一致。
 *
 * **只合并两行都没问题的情况**：任一行解析错、缺代码、待补全或金额对不上，
 * 就各自原样展示。理由：合并行的 `_rowKey` 是合成的（`merged_<父行>`），
 * 用户在修正面板里改它改不到真实数据（后端认的是原始行的 `_rowKey`）；
 * 而且「这一组有问题」时用户必须看见是哪一行有问题，折起来只会多一次展开。
 *
 * 合并只发生在同步配对成功的息+税上（后端 `importer/linking.py` 打的组），
 * 所以「合并 = 这组已经核对干净」这个前提是站得住的。
 */
export function mergeLinkGroups(list: PreviewRow[]): PreviewRow[] {
  const mergedList: PreviewRow[] = [];
  const processedGroupIds = new Set<string>();
  for (const row of list) {
    const groupId = row.link_group_id;
    if (groupId && !processedGroupIds.has(groupId)) {
      const groupRows = list.filter(r => r.link_group_id === groupId);
      const healthy =
        groupRows.length === 2 && groupRows.every(r => !hasFixProblem(r));
      if (healthy) {
        const interestRow =
          groupRows.find(r => r.op_type !== "tax") || groupRows[0];
        const taxRow = groupRows.find(r => r.op_type === "tax") || groupRows[1];
        const netAmount = (interestRow.amount || 0) + (taxRow.amount || 0);
        const parentKey = `merged_${interestRow._rowKey}`;
        const detailRows = groupRows.map(r => ({ ...r }));
        mergedList.push({
          ...interestRow,
          _rowKey: parentKey,
          amount: netAmount,
          net_amount: netAmount,
          is_merged: true,
          children: detailRows,
          notes: `税前${interestRow.amount?.toFixed(2)}元，扣税${Math.abs(taxRow.amount || 0).toFixed(2)}元，实收${netAmount.toFixed(2)}元`,
          op_type_label: "利息收入"
        });
        processedGroupIds.add(groupId);
      } else {
        groupRows.forEach(r => mergedList.push(r));
        processedGroupIds.add(groupId);
      }
    } else if (!groupId) mergedList.push(row);
  }
  return mergedList;
}

export function countBlockedRows(rows: PreviewRow[]): number {
  return rows.filter(
    row =>
      isRowBlocked(row) &&
      !row.is_duplicate &&
      !row.error &&
      !row.is_cash_transfer
  ).length;
}

/**
 * 已隐藏但仍被勾选的重复行数（#2274）。
 * 「取消显示重复行」只切显隐、不动勾选（导入载荷与「已选择 N 条」均以
 * selectedKeys 为唯一真相源）：这些行不出现在「只看问题数据」视图里，
 * 却会随 selectedKeys 进入导入载荷（keep_duplicate 真插入）。
 * UI 据此给出可见提示，避免「看不见自己要导什么」。
 */
export function countHiddenSelectedDuplicates(
  rows: PreviewRow[],
  selectedKeys: Set<string>,
  duplicatesHandled: boolean
): number {
  if (!duplicatesHandled) return 0;
  let count = 0;
  for (const row of rows) {
    if (
      row.is_duplicate &&
      row._duplicateHandled &&
      selectedKeys.has(row._rowKey)
    )
      count++;
  }
  return count;
}

export function shouldShowPriceUpdateTip(
  rows: PreviewRow[],
  selectedKeys: Set<string>,
  importedCount: number
): boolean {
  if (importedCount === 0) return false;
  return rows.some(row => {
    if (!selectedKeys.has(row._rowKey)) return false;
    return ["stock", "fund", "etf", "bond"].includes(row.type);
  });
}

export function groupAllocationByType(rows: PreviewRow[]): Array<{
  type: string;
  label: string;
  count: number;
  currentAllocation: string;
}> {
  const groups: Record<
    string,
    { label: string; count: number; currentAllocation: string }
  > = {};
  rows.forEach(row => {
    if (
      row.is_duplicate ||
      row.error ||
      row.is_cash_transfer ||
      isRowBlocked(row) ||
      row._allocationManual
    )
      return;
    const type = row.type || "unknown";
    if (!groups[type])
      groups[type] = {
        label: getTypeLabel(type),
        count: 0,
        currentAllocation: row.allocation || "longterm"
      };
    groups[type].count++;
  });
  return Object.entries(groups).map(([type, data]) => ({ type, ...data }));
}

/**
 * `summarizeErrors` 的入参形状：三项都可缺。
 *
 * 为什么不是 `ImportErrorItem[]`：历史调用与单测会喂**半截对象**（只给 `error`+`name`，
 * 或者 `error` 已判空），函数体本来就是防御式读取（`err.error || "未知错误"`）。
 * 写成必填会让「本来就允许缺」变成「必须补空串」，那是在改调用侧的语义，
 * 不是在收类型。`ImportErrorItem[]` 结构上可赋值给本类型，无需转换。
 */
export interface ErrorSummaryInput {
  symbol?: string;
  name?: string;
  error?: string | null;
}

export function summarizeErrors(
  errors: ErrorSummaryInput[]
): Array<{ reason: string; count: number; items: string[] }> {
  const groups: Record<string, { count: number; items: string[] }> = {};
  errors.forEach(err => {
    const reason = err.error || "未知错误";
    const name = err.name || err.symbol || "--";
    if (!groups[reason]) groups[reason] = { count: 0, items: [] };
    groups[reason].count++;
    groups[reason].items.push(name);
  });
  return Object.entries(groups).map(([reason, data]) => ({
    reason,
    ...data
  }));
}

/** 三卡片条数：按**显示单元**统计（息+税折成一行），故 sum === 表格总行数。
 *
 * 为什么不能按原始行统计（#2836 实测教训）：一组兑息+代扣税原先是两行，表格
 * 折叠成一行后仍按两行计数——概览条说「共 2 条」而表格只有 1 行，用户数不出来。
 * `mergeLinkGroups` 只在「两行都没问题」时才合并（见该函数的 why），所以
 * fix 条数与 `fixSectionRows`（按原始行、供批量修正定位）始终一致。
 */
export function countByCategory(rows: PreviewRow[]): {
  complete: number;
  duplicate: number;
  fix: number;
} {
  const counts = { complete: 0, duplicate: 0, fix: 0 };
  mergeLinkGroups(rows).forEach(row => counts[categorizeRow(row)]++);
  return counts;
}

/**
 * #2281：「数据完整」卡内的转账行条数。与 categorizeRow 同口径取子集
 * （转账行若同时疑似重复则归 duplicate 卡，不计入此处），保证 chips 计数
 * ≤ 卡片条数；摘要卡据此提示「转账可导入 / 转账待关联」。
 */
export function countCompleteTransfers(rows: PreviewRow[]): number {
  let n = 0;
  rows.forEach(row => {
    if (row.is_cash_transfer && categorizeRow(row) === "complete") n++;
  });
  return n;
}

/**
 * 四分区行源（#1792）：修正面板与 fixBreakdown 共用的唯一分桶。
 * 不变量：某行进入且仅进入一个分区 ⟺ categorizeRow(row) === "fix"——
 * 摘要卡「需要修正」条数 = 四分区行数之和，结构性成立（沿 #1791 验收② 的共谓词纪律）。
 */
export function bucketFixSections(
  rows: PreviewRow[]
): Record<FixSectionKey, PreviewRow[]> {
  const buckets: Record<FixSectionKey, PreviewRow[]> = {
    error: [],
    missingCode: [],
    missingQtyPrice: [],
    mismatch: []
  };
  rows.forEach(row => {
    if (row.is_duplicate || row.is_cash_transfer) return;
    if (row.error) buckets.error.push(row);
    else if (isMissingCode(row)) buckets.missingCode.push(row);
    else if (isRowBlocked(row)) buckets.missingQtyPrice.push(row);
    else if (isAmountMismatch(row)) buckets.mismatch.push(row);
  });
  return buckets;
}

/** 「需要修正」卡的细分统计：四分区行数直取，四桶之和恒等于 fix 条数 */
export function sectionCountsOf(
  buckets: Record<FixSectionKey, PreviewRow[]>
): SectionCounts {
  return {
    error: buckets.error.length,
    missingCode: buckets.missingCode.length,
    missingQtyPrice: buckets.missingQtyPrice.length,
    mismatch: buckets.mismatch.length
  };
}

/** 逆回购行：解析期由后端按代码模式识别（沪 204xxx / 深 1318xx），非问题分区——信息型 */
export function pickReverseRepoRows(rows: PreviewRow[]): PreviewRow[] {
  return rows.filter(row => row.type === "reverse_repo");
}

/** 自动填充可推算行：只缺一个（数量或价格）且金额在——缺的那个 = 金额 ÷ 另一个
 *
 * 入参是 `bucketFixSections(rows).missingQtyPrice` 那一桶，不再自行分桶（避免二次遍历）。
 */
export function pickAutoFillableRows(
  missingQtyPriceRows: PreviewRow[]
): PreviewRow[] {
  return missingQtyPriceRows.filter(row => {
    const qty = Number(row.quantity),
      prc = Number(row.price),
      amt = Number(row.amount);
    const qtyMissing = isNaN(qty) || qty <= 0;
    const prcMissing = isNaN(prc) || prc <= 0;
    if (isNaN(amt) || amt <= 0) return false;
    return (qtyMissing && !prcMissing) || (!qtyMissing && prcMissing);
  });
}

/** 已自动填充过的行（_autoFilled 记录字段名）——【查看已填充数据】的数据源 */
export function pickFilledRows(rows: PreviewRow[]): PreviewRow[] {
  return rows.filter(row => row._autoFilled?.length > 0);
}

/**
 * 「暂不导入」条数（#2836）——底栏「另有 N 条暂不导入」与「跳过这 N 条」按钮共用。
 *
 * 判据是 `!isAutoSelectableRow`（**默认不会被选中**），不是 `!isRowSelectable`：
 * 疑似重复的行虽然默认不选，却允许用户手动勾上强制导入（#1882），
 * 用「能不能勾」会把它们漏掉。这里要回答的是「点『跳过这些』会跳过哪些」。
 *
 * 为什么不再用 `duplicate + blocked + error` 加法：加法每加一类问题就得改一次，
 * 而且**已经漏过一次**——实测底栏写「另有 168 条」，概览条写「需要修正 1 条 =
 * 代码未匹配 1」，那 1 条既不在「已选择」里、也不在 168 里，凭空消失。
 *
 * 转账行与已忽略行不计入：前者勾不勾取决于「是否关联现金账户」，不是待修问题；
 * 后者是用户主动做的决定，不该反复提醒。
 */
export function countPendingFix(rows: PreviewRow[]): number {
  return rows.filter(
    row => !row.is_cash_transfer && !row._ignored && !isAutoSelectableRow(row)
  ).length;
}

/** 已选行里的银证转账条数：让「已选择 169 条」自己说清转账在不在里面 */
export function countSelectedTransfers(
  rows: PreviewRow[],
  selectedKeys: Set<string>
): number {
  let n = 0;
  rows.forEach(row => {
    if (row.is_cash_transfer && selectedKeys.has(row._rowKey)) n++;
  });
  return n;
}

/**
 * 表格行过滤的入参快照（#2876 增量 4b）。
 *
 * 五个键一一对应组合式里的五个 ref。抽成显式入参后，过滤函数不再读任何
 * Vue 运行时状态——它和本模块其余函数一样，单测直接喂行对象即可，不必
 * 起 hook、不必 mock 五个 ref。类型故意写成宽泛的 `string` 而不是字面量
 * 联合：旧键的清理历史见 applyRowFilters 的 JSDoc，键集合历史上就变过，
 * 收窄类型只会把「后端多塞一个状态键」变成编译错误而不是分支自然处理。
 */
export interface RowFilterState {
  /** 概览卡状态键：`""` | `blocked` | `complete` | `duplicate` | `fix` */
  tableStatusFilter: string;
  /** 子分类胶囊：`""` | `missingCode` | `mismatch` | `error` */
  activeCategoryFilter: string;
  showProblemOnly: boolean;
  tableFilterKeyword: string;
  tableTypeFilter: string[];
}

/**
 * 表格行过滤（状态 + 子分类 + 问题开关 + 关键词 + 类型）。
 * #1791 起分页数据与总条数共用本函数——此前是两处 90 行近重复实现，新增过滤键
 * 只改一边就会出现「分页显示与底部总条数对不上」的漂移。
 * 旧键 normal / problem / error 是 SummaryStats 胶囊 Tab 的写入值，胶囊已随本卡
 * 删除（#1791 要做的事 7：两套分类法合并），死分支一并移除。
 *
 * **无过滤键命中时返回入参同一引用**（`list` 从 `base` 出发、命中才重新赋值），
 * 调用方不要依赖这一点的副本语义，也不要在这里补 `.slice()`——它是历史行为，
 * #2876 增量 4b 只搬家不修行为。
 */
export function applyRowFilters(
  base: PreviewRow[],
  f: RowFilterState
): PreviewRow[] {
  let list = base;
  const status = f.tableStatusFilter;
  if (status === "blocked")
    list = list.filter(
      row =>
        isRowBlocked(row) &&
        !row.is_duplicate &&
        !row.error &&
        !row.is_cash_transfer
    );
  else if (status === "complete" || status === "duplicate" || status === "fix")
    // 三卡片状态键：与卡片计数同谓词（categorizeRow）
    list = list.filter(row => categorizeRow(row) === status);

  if (f.activeCategoryFilter === "missingCode")
    list = list.filter(
      row =>
        isMissingCode(row) &&
        !row.is_duplicate &&
        !row.error &&
        !row.is_cash_transfer
    );
  else if (f.activeCategoryFilter === "mismatch")
    list = list.filter(row => {
      if (row.is_duplicate || row.error || row.is_cash_transfer) return false;
      return isAmountMismatch(row);
    });
  else if (f.activeCategoryFilter === "error")
    list = list.filter(
      row => !!row.error && !row.is_duplicate && !row.is_cash_transfer
    );

  if (f.showProblemOnly)
    list = list.filter(row => {
      // 与概览条三卡同谓词（`categorizeRow`）。这里曾经手写了一份
      // 「缺字段 || 解析错误 || 重复 || 编辑中」，漏掉「代码未匹配」和
      // 「金额对不上」——于是卡片说「需要修正 1 条」，切到只看问题数据
      // 却是「暂无数据」（#2836 实测）。
      const cat = categorizeRow(row);
      if (cat === "fix") return true;
      if (cat === "duplicate")
        return !(row.is_duplicate && row._duplicateHandled);
      // 就地编辑中的行即使已经改好也要留在原地，否则一按键整行就消失
      return Boolean(
        row.isEditingQty ||
        row.isEditingPrice ||
        row.isEditingAmount ||
        row.isEditingFee
      );
    });
  if (f.tableFilterKeyword) {
    const kw = f.tableFilterKeyword.toLowerCase();
    list = list.filter(
      row =>
        String(row.symbol).toLowerCase().includes(kw) ||
        String(row.name).toLowerCase().includes(kw)
    );
  }
  if (f.tableTypeFilter.length > 0)
    list = list.filter(row => f.tableTypeFilter.includes(row.type));
  return list;
}
