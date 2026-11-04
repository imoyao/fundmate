/**
 * 自选表格「列设置」分组（纯函数）。
 *
 * ## 为什么单独成模块
 *
 * 「列在表格里显不显示」与「列能不能在设置面板里被勾选」是**两套口径**：
 * - 显示判定看 `scope` / `appliesTo`（`useWatchlistColumnVisibility.isVisibleInView`）；
 * - 设置面板的分组**只能**看 `COLUMN_GROUP_MAP` 的归类。
 *
 * 混用出过真实缺陷（#2650）：`trend` 的 `scope` 改成 `"category"` 后，「通用字段」组
 * 按 `scope === "mixed"` 取列，把它过滤掉了；而它的分组是 `general`，又不属于任何
 * 品类组（bond / fund / …）——于是它**在设置面板里彻底消失**，PR 承诺的
 * 「混合视图可在列设置开启」成了空路径（用户实测反馈）。
 *
 * 口径写死在这里：**通用组按 `group === "general"` 收列，与 `scope` 无关**；
 * 其余组 = 通用列 + 该组专属列（用户在任何品类导航下都能一屏配齐通用列）。
 * 判据见 `__tests__/columnGroups.spec.ts`「每个可隐藏列都必须至少出现在一个分组里」。
 */
import {
  COLUMN_GROUP_META,
  getColumnGroup,
  type ColumnDef,
  type ColumnGroup
} from "./columnDefs";

export interface ColumnGroupSection {
  key: ColumnGroup;
  title: string;
  desc: string;
  cols: ColumnDef[];
}

/**
 * 按分组渲染列设置面板。
 *
 * @param hideableColumns 可被用户隐藏的列（`ColumnDef.hideable === true`）
 */
export function buildColumnGroups(
  hideableColumns: ColumnDef[]
): ColumnGroupSection[] {
  // 通用列：只看分组归类，不看 scope——否则「scope=category 但语义属通用」的列
  // 会同时被通用组（scope 过滤）与品类组（分组名不匹配）漏掉。
  const general = hideableColumns.filter(
    c => getColumnGroup(c.key) === "general"
  );
  return COLUMN_GROUP_META.map(meta => {
    const cols =
      meta.key === "general"
        ? general
        : [
            ...general,
            ...hideableColumns.filter(c => getColumnGroup(c.key) === meta.key)
          ];
    return { ...meta, cols };
  }).filter(g => g.cols.length > 0);
}
