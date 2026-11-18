/**
 * 预览行的客户端类型（#2879 第二刀）。
 *
 * 为什么需要这一层：后端 `/api/importers/parse/` 的 `ImportPreviewRow` 只描述
 * **服务端产出的字段**；预览表格在前端还会挂一批**纯客户端字段**——
 * 行键 `_rowKey`、忽略标 `_ignored`、编辑态 `isEditingQty…`、合并行的 `children`
 * 等。此前这些字段全靠 `any[]` 兜着，于是「行上到底能有什么字段」只存在于
 * 十几个函数的实现细节里，重构时无从校验（#2879 卡面点名的正是这条泄漏）。
 *
 * 口径：
 * - 本类型 = `ImportPreviewRow`（服务端字段，唯一真源）+ 客户端附加字段；
 * - 只登记**真实被写入 / 读取**的字段，每个字段注明谁写、为何存在；
 * - 不放开索引签名（`[k: string]: unknown`）——一放开，任何一个拼错字段名都会
 *   静默变成 unknown，等于把 `any` 换个写法留在原地。
 *
 * 边界（别把它读成「类型安全了」）：`ImportPreviewRow` 的字段类型本身仍由
 * `api/importer.ts` 决定，后端改了字段这里不会自动跟着变——那是接口契约测试的事，
 * 不在本类型的职责内。
 */

import type { ImportPreviewRow } from "@/api/importer";
import type { SmartFillOrigin } from "./smartFillPrice";

/** 表格里可原地编辑的四个数字字段（EditableCell 的唯一入口） */
export type EditField = "quantity" | "price" | "amount" | "fee";

export interface PreviewRow extends ImportPreviewRow {
  /** 行唯一键：`addRowKeys()` 注入（`row_<idx>`）；利息+税合并行是合成的 `merged_<父键>` */
  _rowKey: string;
  /** 合并行标记（前端折叠 display 单元用，非服务端字段） */
  is_merged?: boolean;
  /** 合并行折叠掉的原始明细行（`mergeLinkGroups` 写入） */
  children?: PreviewRow[];
  /** 「逐行忽略」标：由 `toggleIgnoreRow()` 翻转，仅前端语义 */
  _ignored?: boolean;
  /** 用户手动改过配置目标：批量「按类型套用」不得覆盖（#1447） */
  _allocationManual?: boolean;
  /** 疑似重复行已被用户处理（显示/计数用，#2274） */
  _duplicateHandled?: boolean;
  /** 批量修正补齐后仍缺数据（`applyManualFill` 写入，供面板过滤） */
  _dataMissing?: boolean;
  /** 被系统自动填充过的字段名清单——**唯一**的「已自动填充」判据（#2902） */
  _autoFilled?: string[];
  /**
   * 旧版「已自动补价」标记（#2902 起判据搬到 `_autoFilled`，本字段仅由
   * `cellEditLogic.smartFill` / `smartFillPrice.fillSmartPrice` 兼容写入）。
   */
  smartFilled?: boolean;
  /** #2137 手续费拆分四列：与 fee 总额有「拆分之和 == fee」不变量，手改总额时整体置 null */
  fee_commission?: number | null;
  fee_stamp_duty?: number | null;
  fee_transfer_fee?: number | null;
  fee_other?: number | null;
  /** 智能补价的「改前 / 改后」原值（随行走草稿，供【恢复原始值】） */
  _smartFillOrigin?: SmartFillOrigin;
  /** 原地编辑前的值（`startEdit` 写入、`finishEdit` 读后 delete）；仅四个 EditField 上的旧值 */
  _oldValue?: number;
  isEditingQty?: boolean;
  isEditingPrice?: boolean;
  isEditingAmount?: boolean;
  isEditingFee?: boolean;
}

/**
 * el-table 的 `#default="{ row }"` 槽把行类型放宽成组件库的 `DefaultRow`
 * （`Record<PropertyKey, any>`），与 `PreviewRow` **无交集**——索引签名不会满足必填字段，
 * 所以 `:row="row"` 直接传会报「缺少属性」。类型收敛只能在这个**边界**上断言一次，
 * 组件内部随后全按 `PreviewRow` 走；不要在调用点各写一份 `as any`，那等于把泄漏
 * 又搬回十几个模板里。
 *
 * 边界（别把它读成「运行时也校验」）：纯断言，不做字段检查——el-table 交来的
 * 就是 `previewData` 的元素（`addRowKeys` 补过 `_rowKey`），形状由写入侧保证。
 */
/** 纯计算函数只读写行的部分字段：测试夹具与服务端中间态均可传入（#2879 第二刀）。 */
export type PreviewRowLike = Partial<PreviewRow>;

export function asPreviewRow(row: unknown): PreviewRow {
  return row as PreviewRow;
}

/**
 * 数组版边界：`addRowKeys` 补过 `_rowKey` 的行进入 `previewData` 时，唯一一次断言。
 *
 * 为什么不把 `addRowKeys` 自己改成返回 `PreviewRow[]`：它是通用工具（有
 * `addRowKeys([{ a: 1 }])` 这类单测），输入什么形状就得返回什么形状。预览行语义
 * 属于向导，由 `useImportWizard` 的包装在这里收口；断言只写一次，下游全部受
 * `PreviewRow` 约束，而不是把 `as any` 摊到十几个赋值点。
 *
 * 同 `asPreviewRow`：纯断言，不做运行时字段校验。
 */
export function asPreviewRows<T extends object>(rows: T[]): PreviewRow[] {
  return rows as unknown as PreviewRow[];
}
