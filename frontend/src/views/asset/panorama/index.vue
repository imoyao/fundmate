<template>
  <div
    class="panorama p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 -->
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2
          class="text-2xl font-bold"
          :style="{ color: 'var(--text-primary)' }"
        >
          资产总览
        </h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary-ink)' }">
          多维度审视你的财富版图
        </p>
      </div>
      <div class="flex items-center gap-2">
        <!-- #1798：/analysis 的静态入口（路由名跳转，拍平后最稳妥）。
             #2150：文案随页面标题改名（智能分析 → 复盘）——两页的跳转关系是
             双向的（本页按钮 → 复盘页；复盘页指路条 → 本页），文案必须对齐，
             否则用户点「智能分析」过去的页面标题写着「复盘」，会以为自己走错了。 -->
        <el-button @click="$router.push({ name: 'AssetAnalysis' })">
          <IconifyIconOffline icon="ep:data-analysis" class="mr-1" /> 复盘
        </el-button>
        <el-button :loading="loading" @click="fetchData">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
        </el-button>
      </div>
    </div>

    <!-- 总览大卡片（含资产大类构成柱状图） -->
    <OverviewSummaryCard
      class="mb-6"
      :total-assets="totalAssets"
      :total-liabilities="totalLiabilities"
      :total-pnl="totalPnl"
      :latest-snapshot="latestSnapshot"
      :distributions="distributions"
    />

    <!-- 桑基图 -->
    <div
      class="rounded-2xl p-6 mb-4"
      :style="{
        backgroundColor: 'var(--bg-card)',
        boxShadow: 'var(--shadow-raised)',
        border: '1px solid var(--border-light)'
      }"
    >
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold" :style="{ color: 'var(--text-primary)' }">
          资产构成流向
        </h3>
        <SegmentedControl
          v-model="sankeyDisplayMode"
          :options="sankeyDisplayOptions"
          size="small"
          aria-label="资产构成流向展示口径"
        />
      </div>
      <SankeyChart :data="sankeyData" :display-mode="sankeyDisplayMode" />
    </div>

    <!-- 基金风格分布（#2628）：家庭级、按持仓市值加权；无箱体的持仓进「未覆盖」不补 0 -->
    <StyleDistributionCard />

    <!-- 「资产透视」区块（原 `AssetInsightPanel`）已于 #2034 收尾时**删除**：
         它的两张环形图，标题与数据字段各有对不上的地方（#2032）——
         左图写「资产分布」而画的是产品类型（`type_distribution`），
         右图写「基金类型分布」而画的是五笔钱 / 配置目标（`allocation_distribution`）；
         而这两套数据在本页下方「多维视图」里各有**标题与字段对得上**的视图
         （「产品类型」「配置目标」）。留着就是同一份数据在首屏重复第二遍，
         且名字叫错——本卡（#2034）处理的正是「同一口径画两遍」这一形态。 -->

    <!-- 多维视图表格 -->
    <div
      class="rounded-2xl p-6"
      :style="{
        backgroundColor: 'var(--bg-card)',
        boxShadow: 'var(--shadow-raised)',
        border: '1px solid var(--border-light)'
      }"
    >
      <div class="flex items-center justify-between mb-5">
        <SegmentedControl
          v-model="detailView"
          :options="detailViewOptions"
          aria-label="多维视图切换"
        />
        <el-button
          v-if="detailView === 'account'"
          text
          size="small"
          @click="$router.push('/asset/ledgers')"
        >
          管理账户
        </el-button>
      </div>

      <CategoryBalanceTable
        v-if="detailView === 'category'"
        :distributions="distributions"
        :total-assets="totalAssets"
        :total-liabilities="totalLiabilities"
      />
      <DetailGroupList
        v-else
        :detail-view="detailView"
        :total-assets="totalAssets"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import SankeyChart from "@/components/Charts/SankeyChart.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import OverviewSummaryCard from "./components/OverviewSummaryCard.vue";
import CategoryBalanceTable from "./components/CategoryBalanceTable.vue";
import DetailGroupList from "./components/DetailGroupList.vue";
import StyleDistributionCard from "./components/StyleDistributionCard.vue";
import {
  getSummary,
  getSankeyData,
  getDistributions,
  getSnapshots,
  postSnapshot,
  type AssetSnapshotItem,
  type DistributionsData
} from "@/api/summary";
import { ElMessage } from "element-plus";

defineOptions({ name: "AssetPanorama" });

const totalAssets = ref(0);
const totalLiabilities = ref(0);
const totalPnl = ref(0);
// 不用 `any`：distributions 是后端下发的固定结构，`any` 会让下游三个消费方
// （摘要卡 / 分类表 / 分组列表）都失去类型检查。字段口径见 `DistributionsData`。
const distributions = ref<DistributionsData | null>(null);
const sankeyData = ref<{ nodes: any[]; links: any[] }>({
  nodes: [],
  links: []
});
const loading = ref(false);
// 最新资产快照（惰性记录 + 同比展示）；积累期无历史时相关字段为 null
const latestSnapshot = ref<AssetSnapshotItem | null>(null);

/** 桑基图展示口径；选项数组显式标注取值类型，供 SegmentedControl 泛型推断（否则数组字面量会把 value 拓宽成 string） */
type SankeyDisplayMode = "amount" | "percent" | "hidden";

const sankeyDisplayMode = ref<SankeyDisplayMode>("amount");
const detailView = ref("category");

const sankeyDisplayOptions: { label: string; value: SankeyDisplayMode }[] = [
  { label: "金额", value: "amount" },
  { label: "比例", value: "percent" },
  { label: "隐藏金额", value: "hidden" }
];

const detailViewOptions = [
  { label: "资产大类", value: "category" },
  { label: "产品类型", value: "type" },
  { label: "账户", value: "account" },
  { label: "配置目标", value: "allocation" }
];

async function fetchData() {
  loading.value = true;
  try {
    const [sumRes, sankeyRes, distRes, snapRes] = await Promise.all([
      getSummary(),
      getSankeyData(),
      getDistributions(),
      getSnapshots()
    ]);

    let sankeyRaw: any = {};
    const sankData = (sankeyRes as any)?.data;
    sankeyRaw = sankData && typeof sankData === "object" ? sankData : {};

    totalAssets.value = (sumRes as any)?.data?.total_assets_cny || 0;
    totalLiabilities.value = (sumRes as any)?.data?.total_liabilities_cny || 0;
    totalPnl.value = (sumRes as any)?.data?.total_pnl_cny || 0;
    distributions.value = distRes?.data ?? null;
    sankeyData.value = {
      nodes: sankeyRaw.nodes || [],
      links: sankeyRaw.links || []
    };

    // 快照列表升序，取最后一条作为最新同比基准
    const snapRaw = (snapRes as any)?.data;
    const snapList: AssetSnapshotItem[] = Array.isArray(snapRaw)
      ? snapRaw
      : snapRaw?.data || [];
    latestSnapshot.value = snapList[snapList.length - 1] || null;
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  fetchData();
  // 后台每日调度器(daily-snapshot.yml, 北京凌晨01:00)已负责落账；此处仅作可观测的补写兜底
  // 验收#1182-②：失败打印告警，不再静默吞异常
  // 每日去重（#1324 review）：前端按日期打标记，避免每次进入页面都打接口造成无谓压力
  // 用本地日期（非 toISOString 的 UTC 日期）：UTC+8 用户在本地 00:00–07:59 会落入上一 UTC 日，
  // 导致同自然日去重键错位、兜底快照重复触发（#1330 review）
  const now = new Date();
  const localDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const snapKey = `snapshot_fallback_${localDate}`;
  let postedToday = false;
  try {
    postedToday = !!localStorage.getItem(snapKey);
  } catch {
    /* 隐私模式 localStorage 不可用，降级为每次兜底补写 */
  }
  if (!postedToday) {
    try {
      localStorage.setItem(snapKey, "1");
    } catch {
      /* 同上，忽略 */
    }
    postSnapshot().catch(e =>
      console.warn("[snapshot] 惰性快照失败(后台定时任务将补写):", e)
    );
  }
});
</script>
