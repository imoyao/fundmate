/**
 * 行展开的「手风琴」（accordion）：同一时刻只允许一个详情面板展开。
 *
 * ## 为什么自己写
 *
 * `el-table` 的展开列**没有** `accordion` 属性（读过 element-plus 2.14.7 的
 * `table/defaults.d.ts` 与 `store/expand.mjs`：只认 `type="expand"` + `row-key`），
 * 所以「打开新的、旧的自动关闭」只能手写。
 *
 * ## 这里的坑：element-plus 的**同步重入**
 *
 * `toggleRowExpansion(row, false)` 会在**同步**里再 emit 一次 `expand-change`
 * （`store/expand.mjs` 第 27 行：`toggleRowStatus` 成功后立刻 `instance.emit(...)`）。
 * 于是「在回调里顺手把旧行收掉」会**重入自己的回调**——上一版就死在这里：
 * 收起旧行触发的那次重入，把「刚展开的新行」也当成要收的，于是用户点开一行，
 * 它立刻自己关掉。
 *
 * ## 解法：用事件自带的语义判断，不加标志位
 *
 * `expand-change(row, expandedRows)` 的第二个参数是**当前全部已展开的行**
 * （`expandRows.value.slice()`）。于是「这一行是刚展开还是刚收起」有唯一答案：
 * 它在不在 `expandedRows` 里。
 *
 * - 在   → 刚展开 → 列表里其它行都是残留，需要收起；
 * - 不在 → 刚收起 → 什么都不做。
 *
 * 「收起旧行」触发的同步重入事件正好落进「刚收起」这一支，于是它自动变成空操作：
 * 既不会把刚展开的新行误关，也不需要额外的状态位去猜「这次是不是我自己干的」。
 *
 * 判定逻辑抽成纯函数 `planAccordion`（不依赖 DOM / 不依赖 Vue），单测可直接覆盖。
 */
import type { TransactionRow } from "./model";

/** `el-table` 实例上我们真正用到的那一个方法 */
export interface ExpandableTable {
  /**
   * 展开 / 收起某一行。
   *
   * `row` 故意用 `any`：element-plus 自己的签名是 `<T extends DefaultRow>`，
   * 而 `DefaultRow = Record<PropertyKey, any>`——接口（而非 type alias）没有
   * 隐式索引签名，`TransactionRow` 赋不过去，用 `any` 才与 el-table 的实例类型对得上。
   */
  toggleRowExpansion: (row: any, expanded: boolean) => void;
}

/** 手风琴的判定结果 */
export interface AccordionPlan {
  /** 这一行刚被展开（`false` = 刚被收起） */
  isExpanded: boolean;
  /** 需要被收起的其它行（刚展开那行之外的残留展开） */
  toCollapse: TransactionRow[];
}

/**
 * 同一行吗？
 *
 * element-plus 的身份语义是**引用相等**（无 `rowKey` 时 `statusArr.indexOf(row)`）。
 * 但 `expandRows` 是 `ref([])` 包出来的 reactive 数组，`slice()` 出来的是**代理对象**，
 * 与传入的原始行可能不是同一个引用；因此再比一次 `id` 兜底（表内 id 唯一）。
 */
function sameRow(a: TransactionRow, b: TransactionRow): boolean {
  return a === b || a.id === b.id;
}

/**
 * 手风琴的**纯判定**：给定「刚被切换的行」与「当前全部已展开的行」，
 * 算出这一行是展开了还是收起了，以及哪些行需要被收起。
 */
export function planAccordion(
  toggled: TransactionRow,
  expandedRows: readonly TransactionRow[]
): AccordionPlan {
  const isExpanded = expandedRows.some(row => sameRow(row, toggled));
  if (!isExpanded) {
    return { isExpanded: false, toCollapse: [] };
  }
  return {
    isExpanded: true,
    toCollapse: expandedRows.filter(row => !sameRow(row, toggled))
  };
}

export interface ExpandAccordionOptions {
  /**
   * 取 `el-table` 实例。
   *
   * 传**取值函数**而不是实例：模板 ref 在 setup 阶段还是 `null`，
   * 等挂载之后才有值。闭包取值能把「实例还没就绪」这件事留在调用点，
   * 本模块不必知道 Vue 的生命周期。
   */
  getTable: () => ExpandableTable | null | undefined;
  /** 某行刚被展开：通知容器按需取这一行的详情 */
  onExpand: (row: TransactionRow) => void;
}

/**
 * 手风琴控制器。
 *
 * 没有响应式状态，因此不叫 `use*`——它只是个把「事件」翻译成「动作」的纯工厂。
 * 好处是**不依赖 Vue 运行时**，单测里可以直接跑（vitest 是 `environment: "node"`，
 * 挂不了组件）。
 */
export function createExpandAccordion(options: ExpandAccordionOptions) {
  /**
   * `el-table` 的 `expand-change` 回调。
   *
   * 第二个参数有两种形态：`el-table` 把该事件声明成
   * `((row, expandedRows: Row[]) => void) & ((row, expanded: boolean) => void)`
   * ——树的展开事件给 boolean，表格的给数组。只接数组会在类型检查里报
   * 「`boolean` 不能赋给 `Row[]`」，所以这里按联合类型收下再判。
   */
  function handleExpandChange(
    row: TransactionRow,
    expanded: TransactionRow[] | boolean
  ) {
    if (!Array.isArray(expanded)) {
      // 树形态：布尔表示「这一行现在是不是展开的」。
      // 本组件只用于表格（`type="expand"` 展开列），这里按最简语义处理。
      if (expanded) options.onExpand(row);
      return;
    }

    const plan = planAccordion(row, expanded);
    // 刚被收起：不取详情、也不动其它行。
    // 「收起旧行」触发的同步重入事件走的正是这一支 —— 刚展开的那行因此不会被误关。
    if (!plan.isExpanded) return;

    const table = options.getTable();
    if (table) {
      for (const other of plan.toCollapse) {
        table.toggleRowExpansion(other, false);
      }
    }
    options.onExpand(row);
  }

  return { handleExpandChange };
}
