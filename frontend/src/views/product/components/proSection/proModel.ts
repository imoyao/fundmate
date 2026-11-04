import type { ProStatusResult } from "@/api/products";

/**
 * 「高级洞察 Pro」区块的状态推导（#980 拆分，纯函数）。
 *
 * 这一段是付费墙 / 介绍卡 / 进度行三处显示的**唯一判据来源**。散在组件里时，
 * 「entitled 取后端事实、不取 env 覆盖」这条拍板约束只能靠注释守着；
 * 抽成纯函数后能用测试钉住——env 覆盖只管遮罩，不许影响介绍卡两态。
 */

/** 一期只对基金家族开放（模块全是基金向分析）；扩品类改这里，勿改挂载点 */
export const PRO_ASSET_TYPES = ["fund", "etf"];

/** 四模块展示元数据——纯呈现层；可用性 / 落地 Phase 以后端状态位为唯一真相 */
export const MODULE_META = [
  {
    key: "performance",
    title: "深度绩效与归因",
    desc: "权益分拆 XIRR、交易行为画像、持有期回撤——全部基于你自己的真实持仓与流水（账户级口径）。"
  },
  {
    key: "risk",
    title: "偏离与风险控制",
    desc: "净值乖离率、波动率、VaR——你的持仓成本与基金风险指标并示，偏离过高时克制提示。"
  },
  {
    key: "allocation",
    title: "资产配置与相关性",
    desc: "大类资产画像、持仓穿透、相关性矩阵——识别「看起来分散、实则同涨同跌」的组合。"
  },
  {
    key: "report",
    title: "智能报告与自动化",
    desc: "投资报告导出与异动提醒——把一页分析变成可留存、可回顾的结论。"
  }
] as const;

export type ProModuleKey = (typeof MODULE_META)[number]["key"];

/** 品类门控：四模块都是基金向分析，其余品类接入是 Phase 2+ 的品类扩展决策 */
export function isProEnabled(assetType: string | null | undefined): boolean {
  return PRO_ASSET_TYPES.includes(assetType ?? "");
}

/** 模块是否已上线（决定徽章档位与卡片是否降权）；状态位未就绪按未上线处理（#2303） */
export function moduleAvailable(
  status: ProStatusResult | null,
  key: ProModuleKey
): boolean {
  return status?.modules?.[key]?.available === true;
}

/** 模块徽标文案；状态位未就绪时返回 null（不渲染徽标，不编造） */
export function badgeText(
  status: ProStatusResult | null,
  key: ProModuleKey
): string | null {
  const module = status?.modules?.[key];
  if (!module) return null;
  return module.available ? "已上线" : `Phase ${module.phase} 建设中`;
}

/**
 * 已开通家庭（#2523）。
 *
 * 判据取**后端权益事实** `paywall_required`（#2324：家庭一份权益都没开通 ⇒
 * true；未登录同样按未开通），**不取 env / URL 覆盖**——那两个只决定遮罩显不显示
 * （e2e / 本地预览用），不改变「这个家庭有没有权益」这个事实。两者混用会出
 * 现「e2e 关了遮罩，介绍卡也跟着消失」的串味。
 *
 * 状态位取不到（null）时按**未开通**处理：介绍卡是区块的兜底内容，
 * 「问不出来」时不能把区块掏空（宁缺勿假的反面是宁空勿假，这里空区块比多四张卡更糟）。
 */
export function isEntitled(status: ProStatusResult | null): boolean {
  return status?.paywall_required === false;
}

/** 已上线模块数（已开通态进度行） */
export function liveModuleCount(status: ProStatusResult | null): number {
  return MODULE_META.filter(m => moduleAvailable(status, m.key)).length;
}

/**
 * 首个未上线模块（按 MODULE_META 顺序；全上线为 null）。
 *
 * 已开通态用「模块进度」一行代替四张介绍卡（#2523）：介绍卡是获客件，付费用户
 * 看进度不看推销；但「哪个模块在建」这个状态位信号不能丢——它来自后端
 * `modules[*].phase`，与徽标同源。
 */
export function nextPendingModule(
  status: ProStatusResult | null
): { title: string; phase: number } | null {
  const meta = MODULE_META.find(m => !moduleAvailable(status, m.key));
  if (!meta) return null;
  const mod = status?.modules?.[meta.key];
  return mod ? { title: meta.title, phase: mod.phase } : null;
}

/**
 * 模块进度行文案（**整串在这里拼，不在模板里跨行插值**——Vue 的 condense 模式
 * 会吃掉跨行文本节点里的换行+缩进，「Phase\n4」会渲染成「Phase4」；单插值从根上
 * 没这个歧义，e2e 也能逐字断言）。
 */
export function progressText(status: ProStatusResult | null): string {
  const base = `已上线 ${liveModuleCount(status)}/${MODULE_META.length}`;
  const pending = nextPendingModule(status);
  return pending
    ? `${base} · ${pending.title} Phase ${pending.phase} 建设中`
    : base;
}
