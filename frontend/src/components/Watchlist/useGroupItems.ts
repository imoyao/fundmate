import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  getWatchlistItems,
  addItemToGroup,
  removeItemFromGroup,
  type WatchlistItem,
  type WatchlistGroup
} from "@/api/watchlist";
import { buildAssetSubtitle } from "@/utils/assetDisplay";

/**
 * 自定义分组「组内产品增删」的数据层（#980 拆分自 `GroupItemsDialog.vue`）。
 *
 * 两条数据来源刻意不同，勿合并：
 * - 本组成员：按 `group_id` 调 `getWatchlistItems`，与主列表同源（后端 SQL JOIN group_links），
 *   杜绝「主列表有、弹窗空」（#1449 Bug 2）；
 * - 候选池：不带 group_id 的全量自选，候选判定纯前端按 id 排除本组。
 *
 * 「全部自选」池翻页以「本页行数 < per_page」为终止条件，不依赖 `res.total`，
 * 避免 total 缺失时只拉第一页导致候选不全。
 */
export function useGroupItems(
  getGroup: () => WatchlistGroup | null,
  onChanged: () => void
) {
  const loading = ref(false);
  const keyword = ref("");
  /** 本组产品：直接按 group_id 拉取（后端 SQL JOIN group_links，与主列表同源，确保一致） */
  const inGroupItems = ref<WatchlistItem[]>([]);
  /** 「全部自选」全量池：不带分组过滤，候选判定纯前端按 id 排除本组 */
  const pool = ref<WatchlistItem[]>([]);

  const groupId = computed(() => getGroup()?.id ?? null);

  function subtitleOf(item: WatchlistItem): string {
    return buildAssetSubtitle(item);
  }

  function matchKeyword(item: WatchlistItem, kw: string): boolean {
    const haystack = [item.symbol, item.display_name, subtitleOf(item)]
      .filter((v): v is string => Boolean(v))
      .join(" ")
      .toLowerCase();
    return haystack.includes(kw);
  }

  /** 本组产品（受搜索词过滤，便于大分组内定位） */
  const inGroup = computed(() => {
    const kw = keyword.value.trim().toLowerCase();
    return inGroupItems.value.filter(item =>
      kw ? matchKeyword(item, kw) : true
    );
  });

  /** 可添加候选：排除本组成员、以及无自选记录 id 的虚拟持仓行 */
  const candidates = computed(() => {
    const memberIds = new Set(
      inGroupItems.value.map(i => i.id).filter((id): id is number => id != null)
    );
    const kw = keyword.value.trim().toLowerCase();
    return pool.value.filter(item => {
      if (item.id == null) return false; // 虚拟持仓行无法加入分组
      if (memberIds.has(item.id)) return false;
      return kw ? matchKeyword(item, kw) : true;
    });
  });

  /** 拉取本组成员：按 group_id（SQL JOIN，与主列表同源），杜绝「列表有、弹窗空」 */
  async function fetchInGroup(): Promise<void> {
    const gid = groupId.value;
    if (gid == null) {
      inGroupItems.value = [];
      return;
    }
    const all: WatchlistItem[] = [];
    const perPage = 200;
    const MAX_PAGES = 50; // 安全阀：防止极端数量下无限翻页
    let page = 1;
    let fetched = 0;
    let total = Infinity;
    while (page <= MAX_PAGES && fetched < total) {
      const res = await getWatchlistItems({
        group_id: gid,
        page,
        per_page: perPage
      });
      const rows = (res.data ?? []) as WatchlistItem[];
      if (rows.length === 0) break;
      all.push(...rows);
      fetched += rows.length;
      total = res.total ?? fetched;
      page++;
    }
    inGroupItems.value = all;
  }

  /**
   * 拉取「全部自选」全量池（不带 group_id）。
   * 翻页以「本页行数 < perPage」为终止条件，不依赖 res.total，
   * 避免 total 缺失时只拉第一页导致候选区不全（#1449 Bug 2 加固）。
   */
  async function fetchPool(): Promise<void> {
    const all: WatchlistItem[] = [];
    const perPage = 200;
    const MAX_PAGES = 50;
    let page = 1;
    while (page <= MAX_PAGES) {
      const res = await getWatchlistItems({ page, per_page: perPage });
      const rows = (res.data ?? []) as WatchlistItem[];
      if (rows.length === 0) break;
      all.push(...rows);
      if (rows.length < perPage) break; // 末页已取尽，停止翻页
      page++;
    }
    pool.value = all;
  }

  /** 每次打开重新拉取（分组名单可能在本抽屉外被改动），并清空搜索词 */
  async function reload(): Promise<void> {
    keyword.value = "";
    loading.value = true;
    try {
      await Promise.all([fetchInGroup(), fetchPool()]);
    } catch (e) {
      ElMessage.error("获取自选列表失败");
      console.error("获取自选列表错误：", e);
    } finally {
      loading.value = false;
    }
  }

  async function addItem(item: WatchlistItem): Promise<void> {
    const gid = groupId.value;
    if (gid == null || item.id == null) return;
    try {
      await addItemToGroup(item.id, gid);
      // 乐观更新：本组成员列表直接加，pool 内对应 item.group_ids 同步，避免整表重拉
      if (!inGroupItems.value.some(i => i.id === item.id)) {
        inGroupItems.value.push(item);
      }
      const target = pool.value.find(i => i.id === item.id);
      if (target) target.group_ids = [...(target.group_ids ?? []), gid];
      onChanged();
    } catch (e) {
      ElMessage.error("添加失败，请重试");
      console.error("添加产品到分组失败：", e);
    }
  }

  async function removeItem(item: WatchlistItem): Promise<void> {
    const gid = groupId.value;
    if (gid == null || item.id == null) return;
    try {
      await removeItemFromGroup(item.id, gid);
      inGroupItems.value = inGroupItems.value.filter(i => i.id !== item.id);
      const target = pool.value.find(i => i.id === item.id);
      if (target) {
        target.group_ids = (target.group_ids ?? []).filter(id => id !== gid);
      }
      onChanged();
    } catch (e) {
      ElMessage.error("移除失败，请重试");
      console.error("从分组移除产品失败：", e);
    }
  }

  return {
    loading,
    keyword,
    groupId,
    inGroup,
    candidates,
    reload,
    addItem,
    removeItem
  };
}
