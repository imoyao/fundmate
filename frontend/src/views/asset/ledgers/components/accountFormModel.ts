import type { SalesInstitution } from "@/api/ledger";

/**
 * 账户表单「销售机构」段的判定口径（#980 拆分自 `AccountFormFields.vue`）。
 *
 * 全部是纯函数 / 常量，便于单测直接断言三件事：
 * 1. 账户类型 → 可见机构类型（证券只列券商；基金平台除期货外全部）；
 * 2. 机构检索三路匹配（汉字全称 / 常用别名 / 拼音首字母简拼，大小写不敏感）；
 * 3. 银行渠道轻提示的触发条件（仅 fund_platform + 选中机构属于银行类）。
 */

/** AMAC 原始 org_type → 展示标签组（独立/银行/券商/保险/其他） */
export const ORG_TYPE_GROUP_LABELS: Record<string, string> = {
  独立基金销售机构: "独立",
  全国性商业银行: "银行",
  城市商业银行: "银行",
  农村商业银行: "银行",
  在华外资法人银行: "银行",
  证券公司: "券商",
  证券投资咨询机构: "券商",
  保险公司: "保险",
  保险代理公司和保险经纪公司: "保险",
  期货公司: "其他",
  公募基金管理公司销售子公司: "其他"
};

/** 银行类 org_type 集合（#1082 D8 银行渠道提示判定用） */
export const BANK_ORG_TYPES = new Set([
  "全国性商业银行",
  "城市商业银行",
  "农村商业银行",
  "在华外资法人银行"
]);

/**
 * 渠道分组 → 可见机构原始类型（#1082 D2/D3）：
 * - securities 仅券商（股票交易只发生在券商）
 * - fund_platform 除期货公司外全部（券商代销场外基金，靠常用置顶 + 类型标识区分）
 * - 其余类型不在表内 → 不过滤，维持现状
 */
export const CHANNEL_CATEGORY_ORG_TYPES: Record<string, string[]> = {
  securities: ["证券公司"],
  fund_platform: [
    "独立基金销售机构",
    "全国性商业银行",
    "城市商业银行",
    "农村商业银行",
    "在华外资法人银行",
    "证券公司",
    "证券投资咨询机构",
    "保险公司",
    "保险代理公司和保险经纪公司",
    "公募基金管理公司销售子公司"
  ]
};

/** AMAC 原始 org_type → 展示标签；未知类型归「其他」 */
export function orgTypeGroupLabel(orgType?: string | null): string {
  return (orgType && ORG_TYPE_GROUP_LABELS[orgType]) || "其他";
}

/** 下拉展示：优先「权威全称（常用别名）」，无别名则仅全称 */
export function institutionLabel(inst: SalesInstitution): string {
  return inst.display_name
    ? `${inst.org_name}（${inst.display_name}）`
    : inst.org_name;
}

/**
 * 按账户类型过滤机构列表。
 *
 * 兼容回退：org_type 缺失（后端旧响应）的条目保持可见，避免下拉被过滤成空。
 * 过滤放在前端而非调 API 传 org_types：ledger_type 在表单内可随时切换，
 * 四个调用方（ledgers 列表页 / 详情编辑 / 资产录入 / 导入向导）均已一次性
 * 加载全量名录经 props 传入，前端 computed 过滤零额外请求、类型切换即时生效。
 */
export function filterInstitutionsByLedgerType(
  list: SalesInstitution[],
  channelCategory: string
): SalesInstitution[] {
  const allowed = CHANNEL_CATEGORY_ORG_TYPES[channelCategory];
  if (!allowed) return list;
  const allowSet = new Set(allowed);
  return list.filter(inst => !inst.org_type || allowSet.has(inst.org_type));
}

/**
 * 文本检索（#1081，全拼为 #2980）：汉字原文 / 常用别名 / 首字母简拼 / 全拼四路匹配，
 * 大小写不敏感，空关键词视为不过滤。
 *
 * 为什么必须有全拼：机构全名是「蚂蚁（杭州）基金销售有限公司」，用户按常用别名
 * 「支付宝」记，输入 `zhifubao` —— 只匹配汉字与简拼（`ZFB`）时搜不到。
 * `pinyin_full` 由后端同时派生全名与别名的全拼（空格分隔），故一次 includes 即可。
 */
export function filterInstitutionsByKeyword(
  list: SalesInstitution[],
  keyword: string
): SalesInstitution[] {
  const kw = keyword.trim().toLowerCase();
  if (!kw) return list;
  return list.filter(
    inst =>
      inst.org_name.toLowerCase().includes(kw) ||
      (inst.display_name ?? "").toLowerCase().includes(kw) ||
      (inst.pinyin_short ?? "").toLowerCase().includes(kw) ||
      (inst.pinyin_full ?? "").toLowerCase().includes(kw)
  );
}

/**
 * 默认排序：按名称拼音首字母 A→Z（#2026-11-07 用户反馈「排名乱序」）。
 *
 * 旧口径把 15 家常用机构按人工 `common_sort` 置顶、其余按 `org_name` 的
 * Unicode 码点序排 —— 码点序是笔画/部首序，**不是拼音序**，看起来就是乱的。
 * 现改用后端 AMAC job 派生的 `pinyin_short`（真库 394/394 覆盖，如 `ZSYX`），
 * 缺失（旧环境未回填）排最后，同音再按中文名兜底。不修改入参数组。
 */
export function sortInstitutionsByPinyin(
  list: SalesInstitution[]
): SalesInstitution[] {
  return [...list].sort((a, b) => {
    const pa = (a.pinyin_short ?? "").toLowerCase();
    const pb = (b.pinyin_short ?? "").toLowerCase();
    // 缺失拼音的条目统一沉底，避免 null 被当成空串排到 A 组最前
    if (!pa && pb) return 1;
    if (pa && !pb) return -1;
    if (pa !== pb) return pa < pb ? -1 : 1;
    return a.org_name.localeCompare(b.org_name, "zh-Hans-CN");
  });
}

/** 「仅看常用」快捷筛选：常用标志来自后端 AMAC 策展，不再参与默认排序 */
export function pickCommonInstitutions(
  list: SalesInstitution[]
): SalesInstitution[] {
  return list.filter(inst => inst.is_common);
}

/** fund_platform 账户选中银行类机构时的轻提示开关（#1082 D8） */
export function shouldShowBankChannelHint(
  channelCategory: string,
  salesInstitutionId: number | null | undefined,
  institutions: SalesInstitution[]
): boolean {
  if (channelCategory !== "fund_platform" || salesInstitutionId == null) {
    return false;
  }
  const inst = institutions.find(i => i.id === salesInstitutionId);
  return !!inst?.org_type && BANK_ORG_TYPES.has(inst.org_type);
}

/**
 * 类型切换后，已选机构是否仍在新类型的可见范围内。
 *
 * 注意：调用方 emit 后 `props.channelCategory` 不会同步回流，必须基于**新值**判断，
 * 不能复用 visibleInstitutions（其仍依赖旧 props 值）。
 * org_type 缺失视为始终可见，与 filterInstitutionsByLedgerType 的回退语义一致。
 */
export function isInstitutionAllowedForLedgerType(
  inst: SalesInstitution | undefined,
  channelCategory: string
): boolean {
  const allowed = CHANNEL_CATEGORY_ORG_TYPES[channelCategory];
  if (!allowed) return true;
  if (!inst?.org_type) return true;
  return allowed.includes(inst.org_type);
}

/**
 * 是否显示「关联现金账户 / 活期+ / 费率」这类证券侧字段。
 *
 * 入参是 channel_category（用户可见分组），**不是** ledger_type：模型铁律规定
 * 分组 / 标签 / 显隐只读 channel_category。注意前后端判据并非同一套——后端按
 * ledger_type 校验（stock / fund 可关联），这里是「只在证券 / 基金平台展示证券侧
 * 字段」的产品可见性策略（futures 分组派生 stock 但不展示，属既有决策）。
 * ledger_category_guard 保证编辑时两字段不矛盾，故不会出现「字段可见却被后端拒绝」。
 * 改动 constants.py 映射表时须复核本函数（#2975）。
 */
export function canLinkCashAccount(category: string): boolean {
  return category === "securities" || category === "fund_platform";
}
