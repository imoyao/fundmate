/**
 * 全面盘点页（InventoryHome）数据层。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。收敛页面全部读写副作用：
 * 大类汇总 / 家庭分布 / 持仓分组 / 投资明细分页 / 按大类的资产明细（带缓存）/ 资产删除，
 * 并统一挂 `usePageRefresh` 全局刷新订阅。
 *
 * 页面只消费本 composable 暴露的响应式状态与动作，不再直连 API。
 */

import { computed, ref, watch, type Ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteAsset,
  getAssets,
  getAssetsSummary,
  type AssetRecord
} from "@/api/assets";
import { getPositions } from "@/api/positions";
import type { Position } from "@/api/types";
import {
  getDistributions,
  getPositionGroups,
  type DistributionsData
} from "@/api/summary";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { INVESTMENT_MAJOR_KEYS } from "@/constants";
import { INVESTMENT_PAGE_SIZE } from "./constants";
import {
  buildInvestmentGroups,
  getErrorMessage,
  type AssetGroupRaw,
  type InvestmentGroup
} from "./helpers";

/** 单次取回某大类的资产明细上限（大类下资产量级有限，一次取回避免翻页） */
const CATEGORY_ASSET_LIMIT = 500;

export function useInventoryData(activeCategory: Ref<string>) {
  /** 大类汇总金额：`{ 大类 key: 金额 }` */
  const assetsSummary = ref<Record<string, number>>({});
  /** 家庭级多维市值分布（标签栏金额口径依赖） */
  const distributions = ref<DistributionsData | null>(null);
  /** 持仓 `type` 维度分组的原始响应（投资分布卡片消费） */
  const investmentGroupsRaw = ref<AssetGroupRaw[]>([]);

  /** 投资明细分页数据（后端分页；market_value/pnl 后端暂不产出，见 Position 类型注释的已知 bug） */
  const investmentPositions = ref<Position[]>([]);
  const investmentTotal = ref(0);
  const investmentPage = ref(1);
  const investmentLoading = ref(false);

  /** 当前大类的资产明细 */
  const currentAssets = ref<AssetRecord[]>([]);
  /** 按大类的资产明细缓存；资产增删改后须整体失效 */
  const assetCache = ref<Record<string, AssetRecord[]>>({});

  /** 投资分布卡片数据（仅投资理财大类有意义） */
  const investmentGroups = computed<InvestmentGroup[]>(() =>
    activeCategory.value === "investment"
      ? buildInvestmentGroups(investmentGroupsRaw.value)
      : []
  );

  /**
   * 标签栏金额（#863 口径 A 对齐）。
   *
   * 投资理财 = 持仓市值（剔除货基 / 逆回购现金等价物）+ 投资理财大类资产，
   * 直接复用后端 `get_distributions` 的 `category_distribution`「投资理财」切片（已扣现金等价物），
   * 避免标签栏比后端高一档（货基 / 逆回购应归入「流动资金」而非「投资理财」）。
   * distributions 尚未加载时回退到旧口径，保证首屏不空。
   */
  function getCategoryTotal(key: string): number {
    if (key === "investment") {
      const invEntry = distributions.value?.category_distribution?.find(
        d => d.name === "投资理财"
      );
      if (invEntry) return invEntry.value;
      return (
        (distributions.value?.positions_total_mv || 0) +
        (assetsSummary.value["investment"] || 0)
      );
    }
    return assetsSummary.value[key] || 0;
  }

  /** 投资明细：后端真实分页拉取（对齐分页信封 `{ data: Position[], total, page, per_page, message }`） */
  async function loadInvestmentPage(page: number) {
    investmentLoading.value = true;
    try {
      const res = await getPositions({ page, per_page: INVESTMENT_PAGE_SIZE });
      investmentPositions.value = res?.data ?? [];
      investmentTotal.value = res?.total ?? investmentPositions.value.length;
    } catch (e) {
      console.error("加载投资明细分页失败", e);
      investmentPositions.value = [];
    } finally {
      investmentLoading.value = false;
    }
  }

  /** 按需加载该大类的具体资产数据（命中缓存则直接复用） */
  async function loadCategoryAssets(category: string) {
    if (assetCache.value[category]) {
      currentAssets.value = assetCache.value[category];
      return;
    }
    try {
      // #1354：投资理财一次取回全部子集（investment + 5 个历史细分类），
      // 避免银行理财/信托等存量记录散落在没有入口的大类里查不到
      const major =
        category === "investment" ? INVESTMENT_MAJOR_KEYS : category;
      const res = await getAssets({
        major_category: major,
        per_page: CATEGORY_ASSET_LIMIT
      });
      const items = (res?.data ?? []) as AssetRecord[];
      assetCache.value[category] = items;
      currentAssets.value = items;
    } catch (e) {
      console.error("加载分类资产失败", e);
    }
  }

  /**
   * 只请求基础汇总、分布与投资分组接口（不再全量拉取资产列表）。
   *
   * 资产可能刚被增删改，因此每次都先整体失效分类缓存再拉当前大类，否则列表里还留着已删记录。
   */
  async function fetchData() {
    try {
      const [summaryRes, distRes, groupsRes] = await Promise.all([
        getAssetsSummary(),
        getDistributions(),
        getPositionGroups("type")
      ]);

      // 同时兼容后端返回的【数组格式】和【旧对象格式】
      const summaryData = summaryRes?.data ?? {};
      let summaryDict: Record<string, number> = {};
      if (Array.isArray(summaryData)) {
        // 情况1：后端返回数组（[{code, value}, ...]）
        summaryData.forEach((item: { code: string; value: number }) => {
          summaryDict[item.code] = item.value;
        });
      } else {
        // 情况2：后端返回旧对象（{ cash: 0, fixed: ... }）
        summaryDict = summaryData;
      }
      assetsSummary.value = summaryDict;

      distributions.value = distRes?.data ?? null;
      investmentGroupsRaw.value = groupsRes?.data ?? [];

      await loadInvestmentPage(investmentPage.value);

      assetCache.value = {};
      await loadCategoryAssets(activeCategory.value);
    } catch (e) {
      console.error(e);
    }
  }

  /** 删除单条资产（二次确认 → 删除 → 整页刷新） */
  async function removeAsset(row: AssetRecord) {
    try {
      await ElMessageBox.confirm(
        `确定要删除资产「${row.name}」吗？此操作不可恢复。`,
        "删除确认",
        {
          confirmButtonText: "确认删除",
          cancelButtonText: "取消",
          type: "warning"
        }
      );
      await deleteAsset(row.id);
      ElMessage.success("资产已删除");
      await fetchData();
    } catch (e) {
      if (e !== "cancel") {
        ElMessage.error(getErrorMessage(e, "删除失败"));
      }
    }
  }

  // 切换大类：拉该大类资产明细 + 投资明细分页复位到第 1 页
  watch(activeCategory, newVal => {
    loadCategoryAssets(newVal);
  });
  watch(activeCategory, () => {
    investmentPage.value = 1;
  });

  // 投资明细分页切换时重新拉取
  watch(investmentPage, page => {
    loadInvestmentPage(page);
  });

  // 账户 / 持仓数据变更后全局自动刷新
  usePageRefresh(() => {
    fetchData();
  });

  return {
    assetsSummary,
    distributions,
    investmentGroupsRaw,
    investmentGroups,
    investmentPositions,
    investmentTotal,
    investmentPage,
    investmentLoading,
    currentAssets,
    getCategoryTotal,
    fetchData,
    removeAsset
  };
}
