/**
 * 纪律提示卡的展示派生逻辑（#2603）。
 *
 * 提到纯模块的原因与 `views/asset/family/familyMemberModel.ts` 相同：vitest 的 node
 * 环境拉不起渲染器（会连带 router / supabase），组件里可测的判定必须落在这里。
 *
 * 本模块刻意**不认识任何具体规则 code**：
 * 前端只按 `severity` 上色、按 `title` / `message` 展示，新增规则不需要改前端。
 * 所以「加一条风格规则不需要动前端」这件事，在这里有可测的落点——
 * 任何 code 的提示都原样变成一条展示项，没有过滤、没有白名单。
 */

/** 提示条目（与后端 `services/insight/rules.py` 出参同构，此处不 import api 以免拉起 http 客户端） */
export interface RuleTipItem {
  code: string;
  severity: string;
  title: string;
  message: string;
  rationale?: string;
  evidence?: Record<string, unknown>;
}

/** 快照摘要（只取本模块用到的字段） */
export interface RuleTipSnapshot {
  holding_count: number;
  penetration_ratio: number;
  style_coverage_pct?: number;
}

/** 一条可直接渲染的提示 */
export interface RuleTipView {
  key: string;
  severity: string;
  title: string;
  message: string;
}

/** 风格数据覆盖率的门槛（%），与后端 `STYLE_MIN_COVERAGE_PCT` 同值 */
export const STYLE_COVERAGE_FLOOR = 50;

/**
 * 把后端提示原样转成展示项：**不按 code 过滤、不按 code 分支**。
 * 空列表原样返回空数组（「没有提示」由组件另行区分「算不出来」的文案）。
 */
export function toTipViews(
  items: RuleTipItem[] | null | undefined
): RuleTipView[] {
  if (!items || !items.length) return [];
  return items.map(item => ({
    key: item.code,
    severity: item.severity,
    title: item.title,
    message: item.message
  }));
}

/**
 * 无提示时的文案。
 *
 * 必须区分三种情况，混成一句「暂无提示」会让人以为已经体检过了：
 * - 没有持仓 → 压根没有可体检的对象；
 * - 有持仓但没触发 → 这是**结论**（已体检、没问题）；
 * - 数据不足（行业穿透率低 / 风格覆盖率低）→ 该维度的规则压根没跑，
 *   如实说明「数据不足」而不是让用户以为「查过了没问题」。
 */
export function describeEmptyTips(
  snapshot: RuleTipSnapshot | null | undefined
): string {
  const count = snapshot?.holding_count ?? 0;
  if (count === 0) return "还没有投资持仓，暂无可体检的对象。";
  const industryText = snapshot?.penetration_ratio
    ? "行业穿透数据可用"
    : "行业数据覆盖不足";
  const style = snapshot?.style_coverage_pct ?? 0;
  const styleText =
    style >= STYLE_COVERAGE_FLOOR ? "风格数据可用" : "风格数据覆盖不足";
  return `已检查 ${count} 只持仓、${industryText}、${styleText}，当前没有触发提醒。`;
}
