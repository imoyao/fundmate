/**
 * 占比标注（分组头 / 品类聚合卡共用）。
 *
 * 为什么抽成纯函数：同一个「占多少」会出现在分组头（本组 / 总资产）与品类卡
 * （品类 / 总资产）两处，两处各写一遍 `toFixed(1)` 迟早分叉；更要紧的是**兜底分支**
 * 必须一致——不可计算时返回 null（调用方整项不渲染），而不是返回 "0.0%"
 * 把「不知道」说成「没有」。
 */
export function shareOfTotal(
  part: number | null | undefined,
  total: number
): string | null {
  if (part == null || !Number.isFinite(part) || part < 0) return null;
  if (!Number.isFinite(total) || total <= 0) return null;

  const pct = (part / total) * 100;

  // 极小但非零：给 0.1% 而不是 0.0%。「有一点点」与「一点没有」在财务语境里
  // 是两件事，不能因为保留一位小数就抹平。
  if (pct > 0 && pct < 0.1) return "0.1%";

  // 数据异常（分项之和大于总资产）时不写 >100%：占比的上限就是整体，
  // 写出「103.2%」只会让用户以为界面算错了。
  if (pct >= 100) return "100%";

  return `${pct.toFixed(1)}%`;
}
