import { onMounted, watch, type Ref } from "vue";
import { REALTIME_BANNER_DISMISS_KEY } from "@/components/RealtimeWarningBanner/constants";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { useWatchlistData } from "@/composables/useWatchlistData";
import type { useWatchlistToolbar } from "@/composables/useWatchlistToolbar";
import type { useWatchlistStickyLayout } from "@/views/asset/watchlist/composables/useWatchlistStickyLayout";
import type { useWatchlistPageActions } from "@/views/asset/watchlist/composables/useWatchlistPageActions";
import { narrowToHolding } from "@/views/asset/watchlist/watchlistAssetTypes";

interface PageInitOptions {
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  toolbar: ReturnType<typeof useWatchlistToolbar>;
  data: ReturnType<typeof useWatchlistData>;
  actions: ReturnType<typeof useWatchlistPageActions>;
  sticky: ReturnType<typeof useWatchlistStickyLayout>;
  /** 实时估值开关（useWatchlistValuation 的 realtime.enabled） */
  realtimeEnabled: Ref<boolean>;
}

/**
 * 自选页生命周期域（#980 批 B2 拆分自 index.vue，零行为变更）：
 * 首屏取数顺序、持仓分组的类型约束、分组切换刷新、吸顶/列拖拽接线。
 *
 * 为什么单列成 composable：这几十行的顺序本身就是**修过的 bug**（见下方每一步的
 * 注释），散在 .vue 里既挤压页面装配的可读性，也容易被后续改动无意打乱时序。
 * 集中之后「先分组后列表」「约束必须初始跑一次」这类不变量只有一个落点。
 *
 * ⚠️ 调用位置：本 composable 内部有 onMounted / watch，必须在 setup 期间同步调用。
 */
export function useWatchlistPageInit(options: PageInitOptions) {
  const { groups, tags, toolbar, data, actions, sticky, realtimeEnabled } =
    options;

  // 实时估值功能被「关闭→重新开启」时，清除横幅关闭标记，让提示横幅重新出现。
  // （key 只能从 RealtimeWarningBanner.vue 的具名导出引用）
  watch(realtimeEnabled, (now, prev) => {
    if (prev === false && now === true) {
      try {
        localStorage.removeItem(REALTIME_BANNER_DISMISS_KEY);
      } catch {
        /* 隐私模式下忽略存储异常 */
      }
    }
  });

  onMounted(async () => {
    // 先恢复本地记忆的每页条数，确保首屏 fetch 即使用户上次的选择（#1335）
    await data.initPageSize();
    tags.fetchTags();
    actions.fetchHoldingGaps();

    // ── #2329：分组必须**先于**列表就绪 ─────────────────────────────
    // 旧写法把 groups.fetchGroups() 与 data.fetchData() 并发发出，而
    // fetchParams 对系统分组是查 allGroups 拿过滤语义的（useWatchlistData.ts）。
    // 挂载那一刻 allGroups 还是 []，查不到就把分组条件**静默丢掉**，
    // 首屏请求退化成「不带 status」⇒「持仓」Tab 高亮、列表却是「全部」的内容
    // （用户实测混进了「基金经理」这类非持仓行）。
    //
    // 为什么只在持仓犯病：自定义分组的 group_id 由 key 字符串直接推导、不依赖
    // allGroups；系统分组「全部」的 filter 本就是空对象、无差异。只有
    // holding / watching / cleared / favorite 会中招，而默认落 holding ——
    // 所以用户观感就是「持仓分组特有」。
    //
    // await 之后 allGroups 才有值，watch(activeGroup) 也才注册得起（见下）。
    const groupsOk = await groups.fetchGroups();
    if (!groupsOk) {
      // 分组拿不到 ⇒ 无法保证请求里的分组语义与 Tab 高亮一致。此时**回退到「全部」**
      // 而不是让「持仓」Tab 亮着却展示未过滤的内容：拿不到与「就是空的」必须可区分，
      // 宁可显示一个诚实的「全部」，也不谎报「持仓」（对应 AGENTS.md「判据必须有失败态」）。
      groups.setActiveGroup("all");
    }
    data.fetchData();

    // 持仓分组只含真实持仓（stock/fund/etf/bond/index），不含「基金经理」等非持仓
    // 类型——持仓时剔掉非持仓类型，其余持仓类型一律保留并生效（#1449：此前整体清空
    // 非 stock/fund 类型，导致 ETF/可转债等持仓类型筛选在持仓分组下形同虚设）。
    //
    // 本函数是「剔除非持仓类型」的**唯一写入点**（#2329）：筛选弹层与快捷胶囊栏只
    // 收窄各自的可选列表、不改这里的状态，避免多处互写打架。
    // 必须既在初始态跑一次、也在切换时跑：旧实现只在 watch 里跑，而 watch 对
    // 「值没变」不触发，首屏（activeGroup 初值即 holding）永远享受不到这道约束。
    const applyHoldingTypeConstraint = () => {
      if (groups.activeGroup.value !== "holding") return;
      const kept = narrowToHolding(toolbar.selectedAssetTypes.value);
      // 仅在真的需要剔除时才写回，避免无谓地让 computed / 胶囊栏重算
      if (kept.length !== toolbar.selectedAssetTypes.value.length) {
        toolbar.selectedAssetTypes.value = kept;
      }
    };
    applyHoldingTypeConstraint();

    watch(groups.activeGroup, () => {
      applyHoldingTypeConstraint();
      data.currentPage.value = 1;
      data.fetchData();
    });
    sticky.initHeaderDrag();
    sticky.bindStickyObserver();
    sticky.bindPageMinHObserver();
  });
}
