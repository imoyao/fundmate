/**
 * 穿透面板共用的格式化助手（#2617 拆分引入）。
 *
 * 为什么要单独成文件：`PenetrationPanel` 已有 500+ 行，触到 `check_vue_size`
 * 的 400 行阈值（issue #980）。拆出子组件后三个 SFC 都要用同一套比率 / 条形
 * 宽度口径——复制三份就会出现「同一个 0.4225 在两个面板里显示成不同宽度」。
 *
 * 口径纪律：比率一律由后端给 0~1 值，前端**只格式化不做除法**；分母由后端定
 * （行业行是 `ratio_of_penetrated`、直持行是 `ratio_of_total`，两者不可混）。
 */

/** 0~1 比率 → 百分比字符串；null/undefined 按 0 处理（后端「造不出」时给 null） */
export function percent(ratio: number | null | undefined): string {
  return `${((ratio ?? 0) * 100).toFixed(1)}%`;
}

/** 0~1 比率 → 条形宽度；夹取到 0~100 防止脏数据把条形撑出容器 */
export function barWidth(ratio: number | null | undefined): string {
  const r = Math.max(0, Math.min(1, ratio ?? 0));
  return `${(r * 100).toFixed(2)}%`;
}
