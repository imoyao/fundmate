// 同类优选的列定义（#980 拆分自 index.vue 的 tableColumns / columnGroups）。
//
// 列即排序入口（#2298 排序进表头）：每列 key 与后端 `fund_risk_ranking.SORTABLE_METRICS`
// 对齐；`kind` 决定染色（return 染涨跌，ratio/risk 一律中性——不替用户判好坏）；
// `dir` 决定首击方向（high ⇒ desc，low ⇒ asc）。
//
// 这里是**纯数据**：改文案不影响任何行为，改 key 必须同时改后端白名单。

/** 表格列 = 排序入口（#2298 排序进表头）：每列 key 与后端
 *  `fund_risk_ranking.SORTABLE_METRICS` 对齐（annual_return 后端亦支持，True=降序）。
 *  曾经可排、但没有列展示的「索提诺」随分段控制器一并下线——按看不见的列排序没有意义。
 *
 *  2026-10-17 UI 优化（详见文件头「涨跌色边界」）：
 *  - `label` 去掉 `(%)`：单位统一到工具栏说明，表头更短、不被横向截断；
 *  - `kind`：`return` = 区间收益列（染涨跌色，配 +/- 符号）；`ratio` / `risk` = 中性色；
 *  - `dir`：指标方向（越高 / 越低越好），进表头 tooltip 与底部指标说明；
 *  - `bar`：夏普 / 卡玛画数据条（优中选优的核心指标，长度 = 列内相对位置）；
 *  - `hint`：面向普通用户的指标解释（2026-10-17 表头 tooltip）——夏普/卡玛这类术语
 *    只摆数字不解释，多数用户读不懂「这个数高好还是低好」；
 *  - `desc`：底部折叠面板的长说明。 */
export interface RankingColumn {
  key: string;
  label: string;
  /** return = 区间收益列（染涨跌色）；ratio / risk = 中性色（合规：不做好差评价） */
  kind: "ratio" | "risk" | "return";
  /** 指标方向：越高 / 越低越好（进表头 tooltip 与底部说明） */
  dir: "high" | "low";
  /** 是否画数据条（夏普 / 卡玛：优中选优的核心指标） */
  bar?: boolean;
  /** 表头 tooltip 短解释（hover 即现，无常驻图标） */
  hint: string;
  /** 底部折叠面板长说明 */
  desc: string;
}

export const tableColumns: RankingColumn[] = [
  {
    key: "sharpe",
    label: "夏普",
    kind: "ratio",
    dir: "high",
    bar: true,
    hint: "每承担 1 份年化波动，获得多少超出无风险利率的回报。大于 1 尚可、大于 2 较好；越高越好，只在同类内可比",
    desc: "夏普 =（年化收益 − 无风险利率）÷ 年化波动率。衡量「每承担一份波动换来多少超额回报」，只在同一基金类型内可比。"
  },
  {
    key: "calmar",
    label: "卡玛",
    kind: "ratio",
    dir: "high",
    bar: true,
    hint: "赚的钱抵不抵得过最深的亏损——年化收益 ÷ 最大回撤，数字越大越划算",
    desc: "卡玛 = 年化收益 ÷ |最大回撤|。衡量「盈利对最深亏损的覆盖能力」，越高越好。"
  },
  {
    key: "return_drawdown_ratio",
    label: "波回比",
    kind: "ratio",
    dir: "high",
    hint: "年化收益 ÷（波动率 × 最大回撤）：平时涨跌的幅度和最深一次亏损都算进分母，数字越大越好",
    desc: "波回比 = 年化收益 ÷（年化波动率 × 最大回撤）。同时惩罚「日常颠簸」与「最深亏损」，越高越好。"
  },
  {
    key: "ulcer_index",
    label: "UI",
    kind: "risk",
    dir: "low",
    hint: "溃疡指数：回撤的深度与持续时间合成的值。数字越大，持有过程越煎熬",
    desc: "溃疡指数 UI = √(平均(每日回撤²))，可读作「长期平均回撤幅度」。UI = 18 意味着相当长时间里账户常比前高低约 18%。越低越好。"
  },
  {
    key: "max_drawdown",
    label: "最大回撤",
    kind: "risk",
    dir: "high",
    hint: "区间内从高点到低点最多亏多少。负数存储，越浅（越接近 0）越好",
    desc: "最大回撤 = 区间内从历史高点到其后最低点的最大跌幅，以负数存储（-8 优于 -25）。只反映最深那一次亏损，不计时间。"
  },
  {
    key: "annual_return",
    label: "年化收益",
    kind: "return",
    dir: "high",
    hint: "区间收益折算成的年平均值。正为盈、负为亏",
    desc: "年化收益 = 区间收益按年折算的平均值，反映该窗口内的盈利能力。"
  },
  {
    key: "ret_1m",
    label: "近1月",
    kind: "return",
    dir: "high",
    hint: "近 30 个自然日的净值涨跌幅（累计净值）；历史不足该窗口显示 —",
    desc: "近 30 个自然日的净值涨跌幅（累计净值口径）；起点取边界日当天或之后的第一个净值日，历史不足该窗口显示 —。"
  },
  {
    key: "ret_3m",
    label: "近3月",
    kind: "return",
    dir: "high",
    hint: "近 90 个自然日的净值涨跌幅（累计净值）；历史不足该窗口显示 —",
    desc: "近 90 个自然日的净值涨跌幅（累计净值口径）；起点取边界日当天或之后的第一个净值日，历史不足该窗口显示 —。"
  },
  {
    key: "ret_1y",
    label: "近1年",
    kind: "return",
    dir: "high",
    hint: "近 365 个自然日的净值涨跌幅（累计净值）；历史不足该窗口显示 —",
    desc: "近 365 个自然日的净值涨跌幅（累计净值口径）；起点取边界日当天或之后的第一个净值日，历史不足该窗口显示 —。"
  }
];

/** 表头分组（2026-10-17 第二轮）：`keys` 必须与 `tableColumns` 的键**同序全覆盖**——
 *  分组行 colspan 按 keys 长度展开，与指标行逐列对齐；少一个键表头就会错位。
 *  列顺序即按组重排（波回比从 UI 之后提前到卡玛之后），分组才连得起来。
 *  分组是纯展示层：不改排序行为、不改口径。 */
export interface ColumnGroup {
  label: string;
  tip: string;
  /** 必须与 tableColumns 的键同序全覆盖 */
  keys: string[];
}

export const columnGroups: ColumnGroup[] = [
  {
    label: "风险调整收益",
    tip: "把风险与亏损换算掉的收益效率，均按指标窗口计算；只在同类内可比，越高越好",
    keys: ["sharpe", "calmar", "return_drawdown_ratio"]
  },
  {
    label: "风险",
    tip: "持有期间的亏损深度与煎熬程度，按指标窗口计算；越低越好",
    keys: ["ulcer_index", "max_drawdown"]
  },
  {
    label: "收益",
    tip: "年化收益按指标窗口折算；近1月 / 近3月 / 近1年为对应自然日的区间净值涨跌幅",
    keys: ["annual_return", "ret_1m", "ret_3m", "ret_1y"]
  }
];
