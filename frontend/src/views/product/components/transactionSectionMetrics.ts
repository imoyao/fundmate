/**
 * 「交易记录」区块的渐进披露判定（#2160）。
 *
 * 为什么值得单独立锚点：首版把 `per_page: 10` 写死在组件里，**没有任何提示**——
 * 用户既不知道还有更多、也不知道一共多少条，于是把「前 10 条」当成「全部」。
 * 这类缺陷没有任何报错、截图上看不出来，只能靠断言钉住。
 *
 * 这里的每条判定都刻意选了一个**容易写错的那一侧**：
 * - `needToggle` 用 `total` 而不是已取到的条数（折叠态只取了 PREVIEW_SIZE 条，
 *   拿已取量判断会在「恰好 10 条」时永不出按钮、在「100 条」时也算错）；
 * - `shouldFetchMore` 用「取到多少」而不是「要不要展开」，避免展开态重复发请求；
 * - `showsPartial` 只在展开态为真（折叠态摆「查看全部」是给用不到的出口加噪声）。
 */

/**
 * 折叠态行数。取 10 是对齐 `ProductHoldingSection.PREVIEW_SIZE` 与季报「前十大」的
 * 既有心智，不另设魔数——同页两个区块用同一个数字，用户不需要记两套。
 */
export const PREVIEW_SIZE = 10;

/**
 * 展开态一次性取满的上限。刻意**不为「展开全部」取全量**：流水的 `total` 无上界
 * （高频交易者可达数百条），一次拉全既拖慢展开、又把几十行铺在详情页里。
 * 超出这个量级的「查全部」是 `TransactionList` 的职责——那个页面本就是为查明细
 * 设计的，且已有 `el-pagination`。此处只给出口，不复制第二个全量视图。
 */
export const EXPAND_SIZE = 50;

/**
 * 是否出「展开全部 N 条」按钮。
 *
 * 必须用 `total`（后端返回的该标的流水总数）判断，不能用已取到的条数：折叠态只取
 * PREVIEW_SIZE 条，已取量恒等于 10，拿它判断会在「恰好 10 条」时永远不出按钮，
 * 在「100 条」时也只按已取到的量算，两个方向都错。
 */
export function needToggle(total: number): boolean {
  return total > PREVIEW_SIZE;
}

/** 折叠时只渲染前 PREVIEW_SIZE 行；展开时渲染已取到的全部 */
export function visibleRows<T>(rows: T[], expanded: boolean): T[] {
  return !expanded ? rows.slice(0, PREVIEW_SIZE) : rows;
}

/** 展开时是否还需要补取：已取量少于目标量才发请求，避免展开态重复取数 */
export function shouldFetchMore(current: number, total: number): boolean {
  return current < Math.min(total, EXPAND_SIZE);
}

/**
 * 展开后仍看不全 → 明示当前看到的是切片，并给出「查看全部流水」的第 3 级出口。
 * 只在展开态为真：折叠态摆这条链接，是在给一个多数用不到的出口加噪声。
 */
export function showsPartial(
  expanded: boolean,
  fetched: number,
  total: number
): boolean {
  return expanded && fetched < total;
}
