/**
 * 录入通用资产页的纯函数层（#980 拆分）。
 *
 * 收进来的都是「来自 URL 的不可信输入 + 两套子类枚举」这类容易静默出错的东西：
 * `?category=` / `?minor=` / `?type=` 由盘点页快捷录入拼出，也可能是手敲的，
 * 值不属于枚举就必须忽略——写成「取到就用」会把脏值落库，而房产 / 贵金属详情页
 * 正是按 `minor_category` 过滤的，一个非法值就能让那条资产从详情页消失。
 *
 * 这里只 import 常量，不 import 组件 / 路由 / 请求。
 */
import {
  ALLOCATION_OPTIONS,
  INVESTMENT_MINOR_CATEGORIES,
  MAJOR_CATEGORY_OPTIONS
} from "@/constants";
// 仅取类型：提交载荷的形状以接口定义为准，避免两边各写一份字段表
import type { AssetCreateInput } from "@/api/assets";
// 固定资产子类目录复用盘点页快捷录入的单一来源（house/car/gold），避免双维护
import { ASSET_TYPE_MAP } from "../inventory/constants";

/** 固定资产子类候选（写入 minor_category，房产/贵金属详情页按此过滤，#1798） */
export const FIXED_SUBTYPE_OPTIONS = ASSET_TYPE_MAP.fixed ?? [];

/** 表单数据形状（与后端 createAsset 的入参一一对应） */
export interface AssetEntryFormModel {
  name: string;
  major_category: string;
  /** 细分：投资理财（#1354）/ 固定资产子类（#1798） */
  minor_category: string | null;
  amount: number;
  allocation: string | null;
  ledger_id: number | null;
  /** 后端回填的账户名快照，提交时以 ledger_id 为准 */
  account_name: string;
  notes: string;
}

export function createEmptyForm(): AssetEntryFormModel {
  return {
    name: "",
    major_category: "cash",
    minor_category: null,
    amount: 0,
    allocation: null,
    ledger_id: null,
    account_name: "",
    notes: ""
  };
}

/** 校验值是否属于投资理财细分子类，拦截 URL / 篡改传入的非法值（#1355 AI review） */
export function isValidMinorCategory(
  value: string | undefined
): value is string {
  return (
    !!value && INVESTMENT_MINOR_CATEGORIES.some(opt => opt.value === value)
  );
}

/** 校验值是否属于固定资产子类（house/car/gold），拦截 URL / 篡改传入的非法值（#1798） */
export function isValidFixedSubtype(
  value: string | undefined
): value is string {
  return !!value && FIXED_SUBTYPE_OPTIONS.some(opt => opt.key === value);
}

/**
 * 大类切换后，当前细分是否还适用。
 *
 * 不适用的细分必须清掉，否则会把投资细分写到别的大类、或把固定资产子类写到投资理财。
 * 判据是「新大类 + 旧细分」的组合，不是单独看任一边。
 */
export function minorCategoryAppliesTo(
  major: string,
  minor: string | null | undefined
): minor is string {
  if (!minor) return false;
  if (major === "investment") return isValidMinorCategory(minor);
  if (major === "fixed") return isValidFixedSubtype(minor);
  return false;
}

/**
 * 从 URL query 解析初始大类与细分。
 *
 * 三个参数各有各的坑：
 * - `?category=`：大类本身不做枚举校验（页面大类下拉会兜住非法值），
 *   只看是不是非空字符串；
 * - `?minor=`：可能因重复参数变成数组，取第一个；且必须属于投资细分子类；
 * - `?type=`：盘点页快捷录入推的 house/car/gold，必须属于固定资产子类
 *   （此前该参数被静默丢弃，#1798）。
 *
 * 解析不出就退回默认（cash + 无细分），不抛错。
 */
export function parseInitialFromQuery(query: {
  category?: unknown;
  minor?: unknown;
  type?: unknown;
}): Pick<AssetEntryFormModel, "major_category" | "minor_category"> {
  const first = (v: unknown): string | undefined => {
    const raw = Array.isArray(v) ? v[0] : v;
    return raw?.toString().trim() || undefined;
  };

  const major_category = first(query.category) ?? "cash";
  let minor_category: string | null = null;

  const minor = first(query.minor);
  if (major_category === "investment" && isValidMinorCategory(minor)) {
    minor_category = minor;
  }

  const type = first(query.type);
  if (major_category === "fixed" && isValidFixedSubtype(type)) {
    minor_category = type;
  }

  return { major_category, minor_category };
}

/**
 * 提交载荷。
 *
 * 两条条件字段的规则：
 * - `minor_category` 只会由投资理财 / 固定资产两个子类选择器写入（切换大类时即清空），
 *   有值才带，不送空串；
 * - `allocation` 只在非负债时带——负债没有配置目标这一说。
 */
export function buildAssetPayload(form: AssetEntryFormModel): AssetCreateInput {
  const payload: AssetCreateInput = {
    major_category: form.major_category,
    name: form.name,
    amount: form.amount,
    // 关键：以 ledger_id 为准，account_name 只是快照
    ledger_id: form.ledger_id,
    account_name: form.account_name || undefined,
    notes: form.notes || undefined
  };
  if (form.minor_category) payload.minor_category = form.minor_category;
  if (form.major_category !== "liability" && form.allocation) {
    payload.allocation = form.allocation;
  }
  return payload;
}

/** 下拉展示：优先「权威全称（常用别名）」，无别名则仅全称 */
export function institutionLabel(inst: {
  org_name: string;
  display_name?: string | null;
}): string {
  return inst.display_name
    ? `${inst.org_name}（${inst.display_name}）`
    : inst.org_name;
}

/**
 * 销售机构检索：汉字 / 常用别名 / 拼音首字母三路匹配（#1081）。
 * 关键词为空时返回全量——下拉初次展开要能看到完整名录。
 */
export function filterInstitutions<
  T extends {
    org_name: string;
    display_name?: string | null;
    pinyin_short?: string | null;
  }
>(list: T[], rawKeyword: string): T[] {
  const kw = rawKeyword.trim().toLowerCase();
  if (!kw) return list;
  return list.filter(
    inst =>
      inst.org_name.toLowerCase().includes(kw) ||
      (inst.display_name ?? "").toLowerCase().includes(kw) ||
      (inst.pinyin_short ?? "").toLowerCase().includes(kw)
  );
}

/** 大类下拉选项（供模板遍历，避免页面与子组件各 import 一次） */
export const MAJOR_OPTIONS = MAJOR_CATEGORY_OPTIONS;
export const ALLOCATION_OPTS = ALLOCATION_OPTIONS;
