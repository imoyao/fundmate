// src/views/welcome/composables/householdCols.ts
/**
 * 家庭口径三列的**定义**：标签、取值口径、各自入口。
 *
 * 为什么抽出来：
 *   1. `to` 全部指向**既有**路由，是本卡与站内三张页面的唯一契约。三条 href 散在
 *      组件的 computed 里时，改路由名只能靠肉眼搜；集中后与 `useHouseholdLinks`
 *      的手势契约同目录相邻，改入口不必进模板。
 *   2. 顺序即恒等式 `总资产 = 负债 + 净资产`，不能随手调换。定义与理由放在一起，
 *      比埋在 30 行 computed 字面量里更难被误改。
 *   3. 组件只负责把 props 接上（`pick`），不再承载「这一列去哪、什么色」的判断。
 */

/** 三列取值所需的卡片 props 子集（与组件 props 同名，便于直接传 props） */
export interface HouseholdBandValues {
  totalAssets: number | null;
  totalLiabilities: number | null;
  netAssets: number | null;
}

export interface HouseholdColMeta {
  key: "assets" | "liabilities" | "net";
  label: string;
  /** 数值色：净资产是结论（主色），负债降一档；总资产同样用主色，不抢戏 */
  color: string;
  /** 入口（既有路由，不新增路径） */
  to: string;
  /** 悬停 / 读屏的去向说明 */
  title: string;
  /** 净资产是这一带的结论：样式里只加字重，不加字号/颜色 */
  strong: boolean;
  /** 取值口径（财务恒等式的每一项各取自己的字段） */
  pick: (values: HouseholdBandValues) => number | null;
}

export const HOUSEHOLD_COLS: readonly HouseholdColMeta[] = [
  {
    key: "assets",
    label: "家庭总资产",
    color: "var(--text-primary)",
    to: "/panorama",
    title: "查看资产构成",
    strong: false,
    pick: values => values.totalAssets
  },
  {
    key: "liabilities",
    label: "家庭总负债",
    color: "var(--text-secondary)",
    to: "/inventory?tab=liability",
    title: "查看负债明细",
    strong: false,
    pick: values => values.totalLiabilities
  },
  {
    key: "net",
    label: "家庭净资产",
    color: "var(--text-primary)",
    to: "/analysis",
    title: "查看资产净值走势",
    strong: true,
    pick: values => values.netAssets
  }
];
