/**
 * 按 Unicode 码点统计字符数（与后端 Python `len()` 口径严格一致）。
 *
 * 背景：JS 的 `String.length` 数的是 UTF-16 code unit——emoji 等增补平面
 * 字符占 2 个 unit；而后端 Pydantic 的 `min_length` / `max_length` 按
 * Python `len()`（Unicode 码点）计数。两端若各用各的，会出现「前端放行、
 * 后端 422」的口径错位（decisions.md D73，D72 遗留收尾）。
 *
 * 口径是「码点」而非「字素簇」：组合 emoji（如 👨‍👩‍👧）按码点算 5——
 * 与后端一致、且只会更严，不会出现前端过后端拒；字素簇需后端引入
 * grapheme 依赖，暂不做（D73 登记）。
 *
 * 孤立代理对（损坏字符串）两端都按 1 计，口径不破。
 */
export function textLength(value: string | null | undefined): number {
  if (!value) return 0;
  return [...value].length;
}
