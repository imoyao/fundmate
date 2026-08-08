/**
 * 生成式头像工具（D9：头像不落盘、不上传）。
 *
 * 头像由 DiceBear 以 `{style}/{seed}.svg` 稳定生成：
 * - seed 决定"长什么样"（同一 seed + 同一风格永远同一张脸）；
 * - style 决定画风（adventurer / lorelei / fun-emoji / micah 等）。
 * 默认 seed 取用户 supabase_id 的确定性哈希，保证不改则头像稳定；
 * 用户可在个人中心切换风格或"随机换一个"（更新保存的 seed）。
 *
 * 隐私：seed 只使用非 PII 的用户标识哈希，绝不含 email / 手机号。
 */

/** 头像风格色板（全年龄友好、活泼不怪异的卡通系） */
export const AVATAR_STYLES = [
  "adventurer",
  "lorelei",
  "fun-emoji",
  "micah"
] as const;

export type AvatarStyle = (typeof AVATAR_STYLES)[number];

export const DEFAULT_AVATAR_STYLE: AvatarStyle = "adventurer";

/** 风格中文名（果冻胶囊按钮 / 下拉展示用，避免直接暴露英文 key） */
export const AVATAR_STYLE_LABEL: Record<AvatarStyle, string> = {
  adventurer: "冒险家",
  lorelei: "优雅",
  "fun-emoji": "趣味",
  micah: "简约"
};

const DICEBEAR_BASE = "https://api.dicebear.com/9.x";

/** 简单确定性字符串哈希（djb2），保证非可逆、非 PII 的稳定 seed */
export function hashSeed(input: string): string {
  let h = 5381;
  for (let i = 0; i < input.length; i++) {
    h = ((h << 5) + h + input.charCodeAt(i)) | 0;
  }
  // 保证正数并填充，避免负号
  return Math.abs(h).toString(36);
}

/** 生成一张 DiceBear 头像 URL */
export function buildAvatarUrl(style: AvatarStyle, seed: string): string {
  return `${DICEBEAR_BASE}/${style}/svg?seed=${encodeURIComponent(seed)}`;
}

/** 基于用户唯一标识生成默认头像 URL（不改则稳定一致） */
export function defaultAvatarUrl(uniqueId?: string | null): string {
  const seed = uniqueId ? hashSeed(uniqueId) : hashSeed("fundmate-anon");
  return buildAvatarUrl(DEFAULT_AVATAR_STYLE, seed);
}

/** 随机换一个 seed（换脸）；调用方保存后头像持久化在 users.avatar */
export function randomAvatarUrl(
  style: AvatarStyle = DEFAULT_AVATAR_STYLE
): string {
  const seed = Math.random().toString(36).slice(2) + Date.now().toString(36);
  return buildAvatarUrl(style, hashSeed(seed));
}

/** 生成一个新的随机 seed（换脸用，配合 buildAvatarUrl 使用） */
export function randomSeed(): string {
  return hashSeed(
    Math.random().toString(36).slice(2) + Date.now().toString(36)
  );
}

/** 校验一个针对本应用的生成式头像 URL 是否是合法的 DiceBear 地址 */
export function isAvatarUrl(value: string | null | undefined): boolean {
  if (!value) return false;
  return value.startsWith(`${DICEBEAR_BASE}/`);
}

/**
 * 从 DiceBear 头像 URL 解析出 style 与 seed（编辑个人中心时回填用）。
 * 解析失败返回 null（非本应用生成的 URL 无法还原）。
 */
export function parseAvatarUrl(
  value: string | null | undefined
): { style: AvatarStyle; seed: string } | null {
  if (!value) return null;
  const prefix = `${DICEBEAR_BASE}/`;
  if (!value.startsWith(prefix)) return null;
  const rest = value.slice(prefix.length);
  const slashIdx = rest.indexOf("/");
  if (slashIdx === -1) return null;
  const style = rest.slice(0, slashIdx) as AvatarStyle;
  const seed = new URLSearchParams(rest.slice(slashIdx + 1)).get("seed") ?? "";
  if (!seed || !(AVATAR_STYLES as readonly string[]).includes(style)) {
    return null;
  }
  return { style, seed };
}
