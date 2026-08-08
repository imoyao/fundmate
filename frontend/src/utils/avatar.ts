/**
 * 生成式头像工具（D9：头像不落盘、不上传）。
 *
 * 头像由 DiceBear 以 `{style}/{seed}.svg` 稳定生成：
 * - seed 决定"长什么样"（同一 seed + 同一风格永远同一张脸）；
 * - style 决定画风（adventurer / blobs / clay 等）。
 * 默认 seed 取用户 supabase_id 的确定性哈希，保证不改则头像稳定；
 * 用户可在个人中心切换风格或"随机换一个"（更新保存的 seed）。
 *
 * 动画（D-头像-2）：10.x 起 DiceBear 支持纯 CSS 内嵌动画，`<img>` 直接播放，
 * 默认打开（仅对官方动画风格生效），尊重系统 prefers-reduced-motion。
 * 老的 9.x URL（无动画能力）在解析时兼容，重建时统一升级到 10.x。
 *
 * 隐私：seed 只使用非 PII 的用户标识哈希，绝不含 email / 手机号。
 */

/** 头像风格全集（全年龄友好、活泼不怪异的卡通系 + 抽象图形系） */
export const AVATAR_STYLES = [
  "adventurer",
  "adventurer-neutral",
  "lorelei",
  "micah",
  "big-smile",
  "fun-emoji",
  "big-ears-neutral",
  "bottts",
  "clay",
  "blobs",
  "shapes",
  "squircles",
  "waves",
  "glyphs"
] as const;

export type AvatarStyle = (typeof AVATAR_STYLES)[number];

/** 官方支持 CSS 动画的风格（仅这些风格能播动画，其他风格传 animationVariant 会被忽略） */
export const ANIMATED_AVATAR_STYLES: ReadonlySet<AvatarStyle> = new Set([
  "clay",
  "blobs",
  "shapes",
  "squircles",
  "waves"
]);

export const DEFAULT_AVATAR_STYLE: AvatarStyle = "adventurer";

/** 动画速度档（官方支持 six speeds，此处统一用 medium） */
const DEFAULT_ANIMATION_VARIANT = "medium";

/** 风格中文名（果冻胶囊按钮 / 下拉展示用，避免直接暴露英文 key） */
export const AVATAR_STYLE_LABEL: Record<AvatarStyle, string> = {
  adventurer: "冒险家",
  "adventurer-neutral": "冒险家·中性",
  lorelei: "柔线",
  micah: "简约",
  "big-smile": "大笑脸",
  "fun-emoji": "表情",
  "big-ears-neutral": "大耳朵",
  bottts: "机器人",
  clay: "软陶",
  blobs: "气泡",
  shapes: "几何",
  squircles: "圆角方格",
  waves: "波浪",
  glyphs: "字形"
};

/** 10.x 为当前版本；旧 9.x 域名仅用于兼容解析老头像 URL */
const DICEBEAR_BASE = "https://api.dicebear.com/10.x";
const DICEBEAR_BASE_LEGACY = "https://api.dicebear.com/9.x";

/** 简单确定性字符串哈希（djb2），保证非可逆、非 PII 的稳定 seed */
export function hashSeed(input: string): string {
  let h = 5381;
  for (let i = 0; i < input.length; i++) {
    h = ((h << 5) + h + input.charCodeAt(i)) | 0;
  }
  // 保证正数并填充，避免负号
  return Math.abs(h).toString(36);
}

export interface BuildAvatarOptions {
  /** 是否开启 CSS 动画（默认 true，仅对官方动画风格生效） */
  animated?: boolean;
}

/** 生成一张 DiceBear 头像 URL（10.x，带可选动画参数） */
export function buildAvatarUrl(
  style: AvatarStyle,
  seed: string,
  options: BuildAvatarOptions = {}
): string {
  const animated = options.animated ?? true;
  const params = new URLSearchParams({ seed });
  if (animated && ANIMATED_AVATAR_STYLES.has(style)) {
    params.set("animationVariant", DEFAULT_ANIMATION_VARIANT);
  }
  return `${DICEBEAR_BASE}/${style}/svg?${params.toString()}`;
}

/** 基于用户唯一标识生成默认头像 URL（不改则稳定一致，默认带动画） */
export function defaultAvatarUrl(
  uniqueId?: string | null,
  options: BuildAvatarOptions = {}
): string {
  const seed = uniqueId ? hashSeed(uniqueId) : hashSeed("fundmate-anon");
  return buildAvatarUrl(DEFAULT_AVATAR_STYLE, seed, options);
}

/** 随机换一张脸 / 一个风格（换脸 + 换风格；调用方保存后持久化在 users.avatar） */
export function randomAvatarUrl(options: BuildAvatarOptions = {}): string {
  return buildAvatarUrl(randomAvatarStyle(), randomSeed(), options);
}

/** 从全集里随机挑一个风格 */
export function randomAvatarStyle(): AvatarStyle {
  return AVATAR_STYLES[Math.floor(Math.random() * AVATAR_STYLES.length)];
}

/** 生成一个新的随机 seed（换脸用，配合 buildAvatarUrl 使用） */
export function randomSeed(): string {
  return hashSeed(
    Math.random().toString(36).slice(2) + Date.now().toString(36)
  );
}

/** 校验一个针对本应用的生成式头像 URL 是否是合法的 DiceBear 地址（10.x 或 9.x） */
export function isAvatarUrl(value: string | null | undefined): boolean {
  if (!value) return false;
  return (
    value.startsWith(`${DICEBEAR_BASE}/`) ||
    value.startsWith(`${DICEBEAR_BASE_LEGACY}/`)
  );
}

/**
 * 从 DiceBear 头像 URL 解析出 style、seed 与动画状态（编辑个人中心时回填用）。
 * 兼容 9.x / 10.x；解析失败返回 null（非本应用生成的 URL 无法还原）。
 * 注意：4=0.x 版本的动画参数为 `animationVariant`，老 URL 一律视为静态，重建后自动升级。
 */
export function parseAvatarUrl(
  value: string | null | undefined
): { style: AvatarStyle; seed: string; animated: boolean } | null {
  if (!value) return null;
  const prefix = value.startsWith(`${DICEBEAR_BASE_LEGACY}/`)
    ? DICEBEAR_BASE_LEGACY
    : value.startsWith(`${DICEBEAR_BASE}/`)
      ? DICEBEAR_BASE
      : null;
  if (!prefix) return null;
  const rest = value.slice(prefix.length + 1);
  const slashIdx = rest.indexOf("/");
  if (slashIdx === -1) return null;
  const style = rest.slice(0, slashIdx) as AvatarStyle;
  const query = new URLSearchParams(rest.slice(slashIdx + 1));
  const seed = query.get("seed") ?? "";
  if (!seed || !(AVATAR_STYLES as readonly string[]).includes(style)) {
    return null;
  }
  const animated = !!(query.get("animationVariant") ?? null);
  return { style, seed, animated };
}
