/**
 * 导入向导的静态数据：格式引导文案 / 步骤定义 / 表格列定义。
 *
 * 这里只放「不随状态变化」的字面量。任何读 ref 的派生逻辑都不要进来——
 * 本模块零 Vue 依赖，可被单测直接 import。
 */

/** 6 种导入格式的引导文案。用工厂而非常量：调用方要 `reactive(...)` 拿到每实例独立的响应式副本，避免跨实例共享可变对象。 */
export function createFormatGuides() {
  return {
    standard_stock: {
      title: "股票标准模板格式说明",
      tips: [
        "下载 CSV 模板填写数据，或直接上传同花顺等券商导出的 Excel/CSV 文件",
        "代码格式：A股 6 位数字，港股 5 位数字，美股字母代码",
        "日期格式：YYYY-MM-DD，如 2026-01-15",
        "业务类型：买入(BUY)、卖出(SELL)、现金分红(DIVIDEND_CASH)、送股(SPLIT)"
      ]
    },
    standard_fund: {
      title: "基金标准模板格式说明",
      tips: [
        "下载 CSV 模板填写数据，或直接上传基金平台导出的 CSV 文件",
        "代码为6位基金代码（如 014330）",
        "日期格式：YYYY-MM-DD，如 2023-06-01",
        "业务类型：申购(BUY)、赎回(SELL)、现金分红(DIVIDEND_CASH)、红利再投资(DIVIDEND_REINVEST)",
        "份额、净值为选填，手续费默认为0"
      ]
    },
    ths: {
      title: "同花顺交割单导出说明",
      tips: [
        "打开同花顺客户端 → 交易记录 → 历史交割单",
        '选择日期范围，点击"导出" → 选择"导出全部"',
        '导出格式选择"制表符分隔的文本文件"',
        "直接上传导出的文件即可，无需修改"
      ]
    },
    tiantian_fund: {
      title: "天天基金导入说明",
      tips: [
        "在天天基金网页版 → 我的 → 交易查询 → 对账单查询",
        "拖动选中历史交易明细表格 → Ctrl+C 复制",
        "打开基金标准模板 CSV 文件，粘贴数据覆盖示例行",
        "保存 CSV，在 多多贝 选择“天天基金”格式上传"
      ]
    },
    alipay_fund: {
      title: "支付宝导入说明",
      tips: [
        "在支付宝 → 我的 → 账单 → 更多 → 开具交易流水证明",
        "申请“用于个人对账”的流水，下载后解压得到 .csv 文件",
        "在 多多贝 选择“支付宝”格式上传该文件即可",
        "余额宝交易将自动归入活钱，不产生持仓"
      ]
    },
    alipay_pdf: {
      title: "支付宝 PDF 导入说明",
      tips: [
        "在支付宝 → 我的 → 账单 → 开具交易流水证明",
        "申请“基金交易明细”（PDF 格式）",
        "下载后直接上传该 PDF 文件即可",
        "自动提取确认日期、份额、净值、手续费等完整信息"
      ]
    }
  };
}

/** 向导步骤条（4 步）。显式标注类型，不要用 as const——ImportSteps.vue:16 的 props 是 Array<{ title: string }>，readonly 元组会类型不兼容。 */
export const IMPORT_WIZARD_STEPS: Array<{ title: string }> = [
  { title: "选择导入账户" },
  { title: "上传交易文件" },
  { title: "预览与修正" },
  { title: "导入完成" }
];

export interface ImportTableColumn {
  prop: string;
  label: string;
  minWidth: number;
  slot?: string;
  align?: "left" | "center" | "right";
  className?: string;
}

/**
 * 表格列（#1790 → #783 §6.1 口径；2026-11-02 手续费列回归）：数据列 9 +
 * 勾选 + 操作 = **11 列**，最小宽合计 1056px（预算 1060），1200px 视口内无横向滚动。
 *
 * 数据列一律 `minWidth`——design.md「冻结列与横向滚动规范」第 4 条：只有冻结列
 * 才用固定 `width`（否则 EP 不把该列纳入余量分配，宽屏右侧留白，#1421 根因 2）；
 * §6.1 的 px 值即各列最小宽。
 *
 * 列取舍（写明理由、不静默超宽，见 #1790 取舍说明）：
 * - **2026-11-02 手续费列回归（换列，不加列）**：#1790 为守住 11 列/1060px 把
 *   手续费列退场，可见性改由金额列 tooltip 承担。实测这不够——tooltip 只能
 *   「解释」已有差额，**补录不了缺失值**，而手续费直接进买入成本与卖出已实现
 *   （pnl_service），漏记即静默少算。故移除「备注」列（内容折进产品信息第二行）、
 *   配置目标 110→106，腾出的宽度给手续费列 70px，列数仍为 11。
 * - 合同编号 / 发生金额（股票模式）仍退场——行数据完整携带、导入载荷不受影响，
 *   发生金额由金额列 tooltip 呈现。
 * - 勾选 50 / 数量单价金额各 90 / 操作 120 维持 §6.1；状态 60→68（「待补全」三字
 *   标签在 60px 内会折行）；
 *   操作类型 110→104、日期 100→112（+ 不折行：实测 109px 时文本 111px 会折成
 *   「2026-09- / 01」，读起来像两条记录）、产品信息 160→170（余量给的，备注不再被
 *   压成「备…」）。产品信息列内不再重复显示资产类型标签（「操作类型」列已有）。
 */
export const FUND_TABLE_COLUMNS: ImportTableColumn[] = [
  {
    prop: "status",
    label: "状态",
    minWidth: 68,
    slot: "status",
    align: "center"
  },
  {
    prop: "product",
    label: "产品信息",
    // 宽度保持 160 不用加（#2836）：备注从「代码行」挪到「名称行」后，省下了
    // `# 113649` 占的约 66px，同样 160px 下 4 字名称 + 6 字备注正好放得下
    // （160 - 24 内边距 - 48 名称 - 6 间距 = 82px ≈ 6.8 个中文字）。
    minWidth: 160,
    slot: "product"
  },
  {
    prop: "opType",
    label: "操作类型",
    // #2836：104 → 116。「债转股」(36) + 间距(6) + 「可转债」标签(48) +
    // 单元格内边距(24) = 114，104 下标签被截成「可转」——资产类型直接丢失。
    // 只加 12px：宽度预算 1060 是硬的（1200 视口不横向滚动），见
    // feeColumnLayout.spec.ts；这 12px 从日期列让（112→96，日期定长 88px 够用）。
    minWidth: 104,
    slot: "opType"
  },
  {
    prop: "trade_date",
    label: "日期",
    minWidth: 112,
    // 日期是定长 10 字符 + 制表数字，折成「2026-09- / 01」比截断更糟：两行看起来像两条记录
    className: "col-date"
  },
  {
    prop: "quantity",
    label: "份额",
    minWidth: 90,
    slot: "quantity",
    align: "right"
  },
  {
    prop: "price",
    label: "确认净值",
    minWidth: 90,
    slot: "price",
    align: "right"
  },
  {
    prop: "amount",
    label: "金额",
    minWidth: 90,
    slot: "amount",
    align: "right"
  },
  {
    prop: "fee",
    label: "手续费",
    minWidth: 66,
    slot: "fee",
    align: "right"
  },
  {
    prop: "allocation",
    label: "配置目标",
    minWidth: 106,
    slot: "allocation"
  }
];

export const STOCK_TABLE_COLUMNS: ImportTableColumn[] = [
  {
    prop: "status",
    label: "状态",
    // #2836：68 → 72。新增的「金额不符」是最长的一枚状态标签（4 字 = 48px），
    // 加内边距 24px 需要 72；68 下它会被截成「金额不…」。
    minWidth: 72,
    slot: "status",
    align: "center"
  },
  {
    prop: "product",
    label: "产品信息",
    // 宽度保持 160 不用加（#2836）：备注从「代码行」挪到「名称行」后，省下了
    // `# 113649` 占的约 66px，同样 160px 下 4 字名称 + 6 字备注正好放得下
    // （160 - 24 内边距 - 48 名称 - 6 间距 = 82px ≈ 6.8 个中文字）。
    minWidth: 160,
    slot: "product"
  },
  {
    prop: "opType",
    label: "操作类型",
    // #2836：104 → 116。「债转股」(36) + 间距(6) + 「可转债」标签(48) +
    // 单元格内边距(24) = 114，104 下标签被截成「可转」——资产类型直接丢失。
    // 只加 12px：宽度预算 1060 是硬的（1200 视口不横向滚动），见
    // feeColumnLayout.spec.ts；这 12px 从日期列让（112→96，日期定长 88px 够用）。
    minWidth: 104,
    slot: "opType"
  },
  {
    prop: "trade_date",
    label: "日期",
    // 日期是定长 10 字符 + 制表数字，折成「2026-09- / 01」比截断更糟：两行看起来像两条记录
    // #2836：112 → 96，把宽度让给「操作类型」列（可转债标签被截成「可转」）。
    // 实测 10 字符制表数字约 64px + 内边距 24px = 88px，96 仍有余量。
    minWidth: 112,
    className: "col-date"
  },
  {
    prop: "quantity",
    label: "数量",
    minWidth: 90,
    slot: "quantity",
    align: "right"
  },
  {
    prop: "price",
    label: "单价",
    minWidth: 90,
    slot: "price",
    align: "right"
  },
  {
    prop: "amount",
    label: "交易金额",
    minWidth: 90,
    slot: "amount",
    align: "right"
  },
  {
    prop: "fee",
    label: "手续费",
    minWidth: 66,
    slot: "fee",
    align: "right"
  },
  {
    prop: "allocation",
    label: "配置目标",
    minWidth: 106,
    slot: "allocation"
  }
];

/** 按模式选列。列定义是模块级共享常量，两个分支都只读，没有可变风险。 */
export function columnsForMode(isFundMode: boolean): ImportTableColumn[] {
  return isFundMode ? FUND_TABLE_COLUMNS : STOCK_TABLE_COLUMNS;
}
