/**
 * 全面盘点页（InventoryHome）静态目录数据与表格基线样式。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。本文件**只放数据**，不含逻辑：
 * - `INVENTORY_CATEGORIES`：顶部大类标签栏的目录（标签 / 配色变量 / 注释文案）
 * - `ASSET_TYPE_MAP`：各大类下的快捷录入类型（图标 / 配色变量）
 * - `INVENTORY_TABLE_*_STYLE`：页内多处 `el-table` 共用的表头 / 单元格字号字重
 *
 * 说明（#1501）：表格的**视觉基线**（边框 / 表头底色 / 行 hover / 文字色）一律由
 * `src/style/el-table.css` 统一维护，页面不得再用 `:deep(.el-table ...)` 覆盖；
 * 这里只保留基线未定义的字号 / 字重两项。
 */

/** 顶部标签栏的一个资产大类 */
export interface InventoryCategory {
  /** 大类 key，与后端 `major_category` 对齐 */
  key: string;
  label: string;
  /** 选中态底色 CSS 变量名（含 `--` 前缀） */
  bgVar: string;
  /** 选中态描边 CSS 变量名（含 `--` 前缀） */
  borderVar: string;
  /** 大类注释文案 */
  desc: string;
}

/** 快捷录入类型（「快捷操作」卡片与资产录入页的 `type` 参数共用） */
export interface AssetTypeOption {
  key: string;
  icon: string;
  label: string;
  color: string;
}

/**
 * 「快捷操作」卡片的一项。
 *
 * 投资理财大类为固定入口（带副文案说明），其他大类直接由 `ASSET_TYPE_MAP` 映射而来。
 */
export interface QuickActionItem extends AssetTypeOption {
  /** 副文案；其他大类的入口卡不带说明 */
  desc?: string;
}

export const INVENTORY_CATEGORIES: InventoryCategory[] = [
  {
    key: "investment",
    label: "投资理财",
    bgVar: "--category-investment-bg",
    borderVar: "--category-investment",
    desc: "追求保值增值的钱。股票、基金、可转债、银行定期存款、大额存单、银行理财、国债等。这些钱牺牲了部分流动性以换取更高收益。"
  },
  {
    key: "cash",
    label: "流动资金",
    bgVar: "--category-cash-bg",
    borderVar: "--category-cash",
    desc: "用于日常消费和应急的活钱。银行卡活期、微信/支付宝余额、余额宝等随时可取的货币基金请放这里。如果这笔钱3个月内肯定不用，建议记入投资理财。"
  },
  {
    key: "fixed",
    label: "固定资产",
    bgVar: "--category-fixed-bg",
    borderVar: "--category-fixed",
    desc: "用于投资或自用的、流动性低的实物类资产。"
  },
  {
    key: "liability",
    label: "负债",
    bgVar: "--category-liability-bg",
    borderVar: "--category-liability",
    desc: "家庭需偿还的债务，如信用卡、房贷、车贷、个人借款等。"
  },
  {
    key: "receivable",
    label: "应收款",
    bgVar: "--category-receivable-bg",
    borderVar: "--category-receivable",
    desc: "家庭资产中应收未收的款项，如借给他人的钱，为他人垫付的资金。"
  },
  {
    key: "insurance",
    label: "保险项目",
    bgVar: "--category-insurance-bg",
    borderVar: "--category-insurance",
    desc: "家庭保障类资产，如寿险、健康险、年金险等。"
  }
];

export const ASSET_TYPE_MAP: Record<string, AssetTypeOption[]> = {
  cash: [
    {
      key: "bank",
      icon: "ep:bank",
      label: "活期/余额宝",
      color: "var(--add-type-cash)"
    },
    {
      key: "money_fund",
      icon: "ep:money",
      label: "货币基金",
      color: "var(--add-type-money-fund)"
    },
    {
      key: "cash_other",
      icon: "ep:wallet",
      label: "其他现金",
      color: "var(--add-type-cash-other)"
    }
  ],
  investment: [
    {
      key: "stock",
      icon: "ep:trend-charts",
      label: "股票",
      color: "var(--asset-cat-stock)"
    },
    {
      key: "fund",
      icon: "ep:money",
      label: "基金",
      color: "var(--asset-cat-fund)"
    },
    {
      key: "bond",
      icon: "ep:document",
      label: "可转债",
      color: "var(--asset-cat-bond)"
    },
    {
      key: "etf",
      icon: "ep:pie-chart",
      label: "ETF",
      color: "var(--asset-cat-etf)"
    },
    {
      key: "crypto",
      icon: "ep:coin",
      label: "虚拟货币",
      color: "var(--asset-cat-crypto)"
    },
    {
      key: "saving",
      icon: "ep:bank",
      label: "定期/理财",
      color: "var(--asset-cat-saving)"
    }
  ],
  fixed: [
    {
      key: "house",
      icon: "ep:house",
      label: "房产",
      color: "var(--add-type-house)"
    },
    { key: "car", icon: "ep:van", label: "汽车", color: "var(--add-type-car)" },
    {
      key: "gold",
      icon: "ep:medal",
      label: "黄金",
      color: "var(--add-type-gold)"
    }
  ],
  receivable: [
    {
      key: "personal_loan",
      icon: "ep:user",
      label: "个人借款",
      color: "var(--add-type-personal-loan)"
    },
    {
      key: "prepaid",
      icon: "ep:credit-card",
      label: "预付款",
      color: "var(--add-type-prepaid)"
    }
  ],
  liability: [
    {
      key: "credit_card",
      icon: "ep:credit-card",
      label: "信用卡",
      color: "var(--add-type-credit-card)"
    },
    {
      key: "mortgage",
      icon: "ep:house",
      label: "房屋贷款",
      color: "var(--add-type-mortgage)"
    },
    {
      key: "car_loan",
      icon: "ep:van",
      label: "汽车贷款",
      color: "var(--add-type-car-loan)"
    }
  ],
  insurance: [
    {
      key: "life",
      icon: "ep:shield",
      label: "寿险",
      color: "var(--add-type-life)"
    },
    {
      key: "health",
      icon: "ep:first-aid-kit",
      label: "健康险",
      color: "var(--add-type-health)"
    },
    {
      key: "annuity",
      icon: "ep:document",
      label: "年金险",
      color: "var(--add-type-annuity)"
    }
  ]
};

/** 投资明细表格每页条数（数据层分页请求与分页器共用同一常量，避免两处各写 10） */
export const INVESTMENT_PAGE_SIZE = 10;

/** `el-table` 表头基线样式（页内三处表格共用，避免逐处复制） */
export const INVENTORY_TABLE_HEADER_STYLE = {
  color: "var(--text-tertiary)",
  fontWeight: "500",
  fontSize: "13px"
};

/** `el-table` 单元格基线样式 */
export const INVENTORY_TABLE_CELL_STYLE = {
  color: "var(--text-secondary)"
};
