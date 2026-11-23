/**
 * 「补全信息」弹窗对**一组**流水的静态缺口判断（对账工作台域 F，2026-11-13）。
 *
 * 为什么需要它：分组键是 `(ledger_id, symbol or '')`（后端
 * `dangling_ref_service.py:404-407`），组内 symbol 必然相同 ⇒ 对有代码的组，
 * 「标的代码」输入框永远补 0 条，用户填了也不生效，页面却照旧给一个空输入框
 * （owner 2026-11-12 截图：`SZ128021 → SZ128021`，统计行同时说「无需改动 7 条」）。
 *
 * 本文件做三件纯事，都不问后端：
 * 1. 从组内流水算出「这组缺什么」——`DanglingRefTransaction` 每条都带
 *    symbol / trade_date，前端本就知道答案，不需要让用户对着空表单猜；
 * 2. 从预览的 changes 里挑出**真正会变**的行——后端把未变化的行也一并返回
 *    （`_plan_enrichment` 对每一条都给 before/after），前端无条件列出来就会被
 *    读成「7 条变更」；
 * 3. 判定一组流水处在哪个**阶段**（漏斗，2026-11-13）：阶段键由第 3 节的
 *    `danglingNextStep` 唯一派生，队列聚合 / 阶段面板 / 执行区共用。
 *
 * 判据不 import API 类型（与 `danglingRefRemediationGuard` 同一取舍）：只吃最小
 * 形状，单测在 node 环境独立跑，不拉 axios / 环境变量。
 */

/** 组内一条流水的最小形状：判断缺口只需要这两个字段 */
export interface EnrichTxnLike {
  symbol?: string | null;
  trade_date?: string | null;
}

export interface GroupNeeds {
  txnCount: number;
  /** 缺标的代码的条数（null / 空串 / 全空白都算缺） */
  needSymbol: number;
  /** 缺交易日期的条数（null / 空串都算缺） */
  needDate: number;
  /** 组内已有的标的代码（首个非空值，去首尾空白）；全组都没代码时为 null */
  symbol: string | null;
  /** 可补字段数为 0：此时不接受提交，也不该渲染输入框 */
  complete: boolean;
}

function isBlank(value: string | null | undefined): boolean {
  return !value || !value.trim();
}

/**
 * 算出一组流水还缺什么。
 *
 * 空数组视为「没有可判断的对象」，`complete` 恒为 false —— 空组由 guard 的
 * `txnCount === 0` 先挡住并说「该组没有可处理的交易」，不该在这里冒充
 * 「都已填写」。
 */
export function inspectGroupNeeds(txns: readonly EnrichTxnLike[]): GroupNeeds {
  let needSymbol = 0;
  let needDate = 0;
  let symbol: string | null = null;
  for (const txn of txns) {
    if (isBlank(txn.symbol)) {
      needSymbol += 1;
    } else if (symbol === null) {
      symbol = (txn.symbol as string).trim();
    }
    if (!txn.trade_date) needDate += 1;
  }
  return {
    txnCount: txns.length,
    needSymbol,
    needDate,
    symbol,
    complete: txns.length > 0 && needSymbol === 0 && needDate === 0
  };
}

/**
 * 这组流水的「下一步真正该做什么」。
 *
 * 为什么需要它：域 F 的不可回补组有两种完全不同的成因——
 * ① **缺标的代码**：能靠补字段解决；② **代码齐了、但没有同标的的现存持仓行**：
 * 补字段一点用都没有，真正要做的是「按流水重建持仓」。
 *
 * 此前界面把两种都翻成「补全信息」，于是 ② 的用户被送进一个「没有可补的字段」的
 * 死弹窗，弹窗让他「去补建持仓」，而唯一的入口在另一个卡片上（2026-11-13 owner 截图：
 * 两边来回踢皮球）。判据在这里收成一条，列表动作 / 分组卡 / 弹窗都读同一个结论。
 *
/**
 * 四种状态，每一种在界面上都必须有出口：
 * - `reattach`：已有可挂回的现存持仓 → 回补关联
 * - `fill`：缺标的代码 → 补全信息
 * - `rebuild`：代码齐全但没有持仓行 → 按流水重建持仓
 * - `empty`：空组（后端不该给出，防御用）→ 不给动作
 *
 * 另有一个**不属于**本派生的阶段 `mislink`（见 `DanglingStage`）：
 * 那类组根本不是悬空流水（`position_id` 指着的持仓**存在**，只是标的对不上），
 * 它的下一步由后端检出结果给出，不经过 `danglingNextStep`。
 */
export type DanglingNextStep = "reattach" | "fill" | "rebuild" | "empty";

export interface NextStepInput {
  /** 组内已有的标的代码（`inspectGroupNeeds().symbol`） */
  symbol: string | null;
  /** 后端判据：同账本存在同标的的现存持仓行（`DanglingRefGroup.fixable`） */
  fixable: boolean;
  txnCount: number;
}

export function danglingNextStep(input: NextStepInput): DanglingNextStep {
  if (input.txnCount === 0) return "empty";
  if (input.fixable) return "reattach";
  return isBlank(input.symbol) ? "fill" : "rebuild";
}

/* ── 阶段归属（漏斗，2026-11-13） ───────────────────────────────────────
 *
 * spec：docs/working-notes/recon-funnel-2026-11-13.md §3.1。
 * 为什么放这里：一个组只属于一个阶段（fill / reattach / rebuild），队列聚合、
 * 阶段面板、执行区都从同一条判据取阶段——阶段归属与动作名若各算一次，
 * 卡片会写着 A、点进去做 B（2026-11-13 刚修过的漂移）。动作名
 * `DANGLING_ACTION_LABEL` 因此与阶段键同文件收口，改判据必须同步看见动作名。
 */

/**
 * 阶段键 = `danglingNextStep` 去掉 `empty`，另加 `mislink` 与 `unowned`。
 *
 * `mislink`（挂错标的）**不是**悬空流水的下一步：它的组由后端 `/mislinked/` 检出，
 * `position_id` 指着的持仓存在、只是属于别的标的。把它并进 `danglingNextStep`
 * 会让「缺代码 → 补全」这类派生判据去解释一个根本不是悬空的组（真库里
 * 24 条 symbol_norm 不等的挂接中 21 条是场所标注问题，派生器无从分辨）。
 * 故它的阶段归属由组上的 `mislinked` 标记直接给出，见 `groupStage`。
 *
 * `unowned`（无归属，#3126）同理：组上**没有任何持仓指针**（`dangling_position_ids`
 * 与 `candidates` 均为空、`fixable` 恒 false）。**必须短路**：阶段只表示「这一组是哪一类」，
 * 具体能做什么由 `unownedOutcome` 按组判定（补字段 / 重建 / 等夜间回填 / 只能删除）；
 * 若交给派生规则，「代码齐 + fixable=false → rebuild」会把一个净额 ≤ 0 的组也派生成
 * rebuild，等于给用户一条点了就红的路。它的归属由组上的 `unowned` 标记直接给出，
 * 补全之后也永远停在 `unowned`（列表重拉后该组要么已挂回、要么仍无归属）。
 */
export type DanglingStage =
  Exclude<DanglingNextStep, "empty"> | "mislink" | "unowned";

/** 阶段的固定展示顺序：先补字段，再到无归属，再挂回、改错挂，最后才是重建（漏斗从轻到重） */
export const DANGLING_STAGES: readonly DanglingStage[] = [
  "fill",
  "unowned",
  "reattach",
  "mislink",
  "rebuild"
];

/**
 * 阶段归属。**必须**由 `danglingNextStep` 派生（empty → null），禁止另写一份
 * 条件——在 SFC / 调用点里重写判据即视为漂移（design.md「一个数据只有一个
 * 可用入口」）。
 */
export function danglingStageOf(input: NextStepInput): DanglingStage | null {
  const step = danglingNextStep(input);
  return step === "empty" ? null : step;
}

/**
 * 组级阶段判断吃的最小形状。刻意不 import `DanglingRefGroup`（本文件的
 * 「判据不 import API 类型」纪律）：结构兼容即可，单测在 node 环境独立跑。
 */
export interface DanglingStageGroupLike {
  /** 组内标的代码；空串 / null 都算缺 */
  symbol: string | null;
  /** 后端判据：同账本存在同标的的现存持仓行 */
  fixable: boolean;
  /** 组内流水条数 */
  txn_count: number;
  /** 错挂组标记（只在 `/mislinked/` 的组上有）；有它 ⇒ 阶段直接是 `mislink` */
  mislinked?: boolean;
  /** 无归属组标记（只在 `/unowned/` 的组上有）；有它 ⇒ 阶段直接是 `unowned` */
  unowned?: boolean;
}

/** 一个组属于哪个阶段；空组（txn_count === 0）返回 null（不展示） */
export function groupStage(
  group: DanglingStageGroupLike
): DanglingStage | null {
  if (group.txn_count === 0) return null;
  // 错挂组不参与「悬空流水下一步」的派生：它的 `fixable` 含义不同
  // （有同标的持仓可改挂），照派生规则会被判成 `reattach`，点进去却做「改挂」。
  if (group.mislinked) return "mislink";
  // 无归属组同理**必须短路**：阶段只表示类别，动作由 `unownedOutcome` 按组判定
  // （补字段 / 重建 / 等夜间回填 / 只能删除）。若交给派生规则，「代码齐 +
  // fixable=false → rebuild」会把净额 ≤ 0 的组也派生成 rebuild——一条点了就红的路。
  if (group.unowned) return "unowned";
  return danglingStageOf({
    symbol: group.symbol,
    fixable: group.fixable,
    txnCount: group.txn_count
  });
}

/**
 * 组卡的稳定唯一键。
 *
 * `key` 是后端复合主键 `ledger|symbol`，核对差异的覆盖判定按它比对，**不能**把
 * 标的名拼进去；但 symbol 为空的组会按标的名拆成多组（真库 2026-11-15：293 条
 * 缺码流水分属 114 个标的），此时 key 会重复 —— 用它做 `:key` / 折叠面板 name
 * 会让多张卡互相串台。`group_id` 是后端给的唯一键，缺省时退回 `key`。
 */
export function groupUniqueKey(group: {
  key: string;
  group_id?: string;
}): string {
  return group.group_id ?? group.key;
}

/**
 * 按阶段分桶。空组落不进任何桶（groupStage 为 null 直接跳过）；
 * 桶内保持输入顺序，不排序——展示顺序由 DANGLING_STAGES 决定。
 */
export function bucketByStage<T extends DanglingStageGroupLike>(
  groups: readonly T[]
): Record<DanglingStage, T[]> {
  const buckets: Record<DanglingStage, T[]> = {
    fill: [],
    unowned: [],
    reattach: [],
    mislink: [],
    rebuild: []
  };
  for (const group of groups) {
    const stage = groupStage(group);
    if (stage) buckets[stage].push(group);
  }
  return buckets;
}

/**
 * 无归属组（`unowned`，#3126）**这一组**能做什么。
 *
 * 为什么需要它：无归属组的阶段判定只能回答「它属于哪一类」，不能回答「这一组
 * 有哪个出口」。字段齐不齐、净额正不正、同账本有没有候选持仓，三者组合出四种
 * 完全不同的下一步；此前界面把它们一律翻成「补全标的 → 补全信息弹窗」，字段
 * 已齐的组就得到一个空弹窗 + 禁用按钮（owner 2026-11-19 截图：只剩一句「这些
 * 交易没有挂到任何持仓上」）。死胡同不是文案问题，是**没有出口**。
 *
 * 四种出口（每一种都必须有按钮或一句原因）：
 * - `fill`：组内还有缺字段 → 补全信息（仍是最轻的一步）
 * - `rebuild`：字段齐、同账本无同标的持仓、净额为正 → 按流水重建持仓
 * - `wait`：同账本已有唯一对应持仓 → 夜间回填会按标的自动挂回，不需要动作
 * - `deleteOnly`：净额 ≤ 0（重建不出有效持仓）或候选持仓多于一条（系统不替你选）
 *   → 只能删除
 *
 * `actionLabel` 为 `null` 表示「没有可点的主动作」，此时 `reason` 必须说清为什么
 * ——删除按钮始终在，这是本阶段唯一的兜底出口，不是被藏起来的第二条路。
 */
export type UnownedOutcome =
  "fill" | "rebuild" | "wait" | "deleteOnly" | "empty";

export interface UnownedOutcomeInput {
  /** 组内缺什么：调用方传 `inspectGroupNeeds(group.transactions)` 的结果 */
  needs: GroupNeeds;
  /** 组内净额（份，`DanglingRefGroup.net_units`，卖出为负） */
  netUnits: number;
  /** 后端组标签（`DanglingRefGroup.flags`） */
  flags: readonly string[];
}

export interface UnownedDecision {
  outcome: UnownedOutcome;
  /** 主动作按钮文字；`null` = 没有可点的主动作（删除仍可用） */
  actionLabel: string | null;
  /** 一句人话原因：无动作时必须给，有动作时也要说清「为什么是它」 */
  reason: string;
}

/**
 * 净额的最小可重建单位（份）：与后端 `dangling_ref_rebuild_service.MIN_NET_MIN_UNITS = 1`
 * （最小单位，1 份 = 10000）等价。不能用 `> 0` ——`net_units` 是 float，尾数会让
 * 「前端说能建、后端说净额不足」分叉。
 */
const MIN_NET_UNITS = 0.0001;

/** 缺字段的清单化说法（`fill` 的原因要具体到条数，不能只说「缺字段」） */
function missingFieldsLabel(needs: GroupNeeds): string {
  const parts: string[] = [];
  if (needs.needSymbol > 0) parts.push(`${needs.needSymbol} 条缺标的代码`);
  if (needs.needDate > 0) parts.push(`${needs.needDate} 条缺交易日期`);
  return parts.join("、");
}

export function unownedOutcome(input: UnownedOutcomeInput): UnownedDecision {
  const { needs, netUnits, flags } = input;
  // 顺序有意义：先「有没有东西可处理」，再「能不能补」，最后才按后端事实分岔
  if (needs.txnCount === 0) {
    return {
      outcome: "empty",
      actionLabel: null,
      reason: "该组没有可处理的交易"
    };
  }
  if (!needs.complete) {
    return {
      outcome: "fill",
      actionLabel: "补全信息",
      reason: `组内 ${missingFieldsLabel(needs)}，补齐后才能判断归属`
    };
  }
  if (flags.includes("auto_attach_after_enrich")) {
    return {
      outcome: "wait",
      actionLabel: null,
      reason:
        "同账本已有唯一对应的持仓，系统会在夜间回填里按标的自动挂回；这里不用再补字段"
    };
  }
  if (flags.includes("no_candidate")) {
    if (netUnits >= MIN_NET_UNITS) {
      return {
        outcome: "rebuild",
        actionLabel: "按流水重建持仓",
        reason: "组内没有可挂回的持仓行，但流水净额为正，可按流水重建持仓"
      };
    }
    return {
      outcome: "deleteOnly",
      actionLabel: null,
      reason: "这批流水买卖已对冲（净额 ≤ 0），重建不出有效持仓；只能删除"
    };
  }
  // 字段齐、也没有 `no_candidate` 标签：同账本有多条同标的持仓（后端只给单候选
  // 打 `auto_attach_after_enrich`），夜间回填同样不会替你选。
  return {
    outcome: "deleteOnly",
    actionLabel: null,
    reason: "同账本有多条同标的持仓，系统不会替你选该挂哪一条；这些流水只能删除"
  };
}

/**
 * 单个队列项的**执行区决策**：主动作文字、要不要接重建弹窗、无归属组的单组出口。
 *
 * 为什么收在这里而不是 `.vue` 的 computed：`ReconItemAction.vue` 贴着 400 行门禁
 * （`scripts/check_vue_size.mjs`，只减不增），而这段判断是纯函数——放在 SFC 里会让
 * 「每个组都有出口」这条判据散在模板与脚本两处。写法上仍以 `unownedOutcome` 为唯一
 * 真相源：本函数只做「无归属组 → 按组判定 / 其它阶段 → 沿用队列导航名」的分派。
 */
export interface DanglingActionDecision {
  /** 无归属组的单组出口；其它阶段为 null */
  unowned: UnownedDecision | null;
  /** 主动作按钮文字；null = 这一组没有主动作（删除仍可用） */
  primaryLabel: string | null;
  /** 是否要给重建弹窗接线（重建阶段，或无归属组判定为 rebuild） */
  rebuildTarget: boolean;
}

export function decideDanglingAction(
  stage: DanglingStage | null | undefined,
  group: {
    transactions: readonly EnrichTxnLike[];
    net_units: number;
    flags: readonly string[];
  } | null,
  navLabel: string
): DanglingActionDecision {
  if (stage !== "unowned" || !group) {
    // 其它阶段「导航名即动作名」：队列卡上的字样就是点下去会做的事
    return {
      unowned: null,
      primaryLabel: navLabel,
      rebuildTarget: stage === "rebuild"
    };
  }
  const unowned = unownedOutcome({
    needs: inspectGroupNeeds(group.transactions),
    netUnits: group.net_units,
    flags: group.flags
  });
  return {
    unowned,
    primaryLabel: unowned.actionLabel,
    rebuildTarget: unowned.outcome === "rebuild"
  };
}

/**
 * 阶段 → 队列卡动作名。与阶段键同文件，保证「写着什么动作」与「处在什么
 * 阶段」永远一起改。`empty` 不需要动作名（空组不产出队列项）。
 *
 * ⚠️ 这是**队列导航名**（队列卡 / 阶段小节标题），不是单组动作名：一个阶段
 * 里不同组能做的事可以不同，导航名不能预设某一组能做什么。单组动作由
 * `unownedOutcome` 按组给出（`unowned` 阶段尤其如此：补字段 / 重建 / 等回填 /
 * 只能删除四种出口）。
 */
export const DANGLING_ACTION_LABEL: Record<DanglingStage, string> = {
  fill: "补全信息",
  unowned: "逐组处理",
  reattach: "确认挂回",
  mislink: "改挂到正确标的",
  rebuild: "重建持仓"
};

/** 预览 changes 一行的最小形状（对应 `DanglingRefEnrichPreview.changes`） */
export interface EnrichChangeLike {
  symbol_before?: string | null;
  symbol_after?: string | null;
  trade_date_before?: string | null;
  trade_date_after?: string | null;
}

function normalize(value: string | null | undefined): string {
  return (value ?? "").trim();
}

/**
 * 这一行是否真的会被写。null / 空串 / 纯空白一律等价 —— 后端「不填」时
 * after 原样回填 before，两者字符串相等；只在语义相同、写法不同时才需要归一化。
 */
export function changeActuallyWrites(row: EnrichChangeLike): boolean {
  return (
    normalize(row.symbol_before) !== normalize(row.symbol_after) ||
    normalize(row.trade_date_before) !== normalize(row.trade_date_after)
  );
}

/** 预览里只保留真正会变的行（保持后端顺序，不排序） */
export function pickChangedRows<T extends EnrichChangeLike>(
  rows: readonly T[]
): T[] {
  return rows.filter(changeActuallyWrites);
}
