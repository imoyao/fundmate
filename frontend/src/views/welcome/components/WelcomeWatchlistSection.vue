<!--
  WelcomeWatchlistSection · 首页第四排「持仓市值最大资产 / 置顶资产」区块
  （#980 批 B10 从 `views/welcome/index.vue` 抽出）

  为什么整块（含「添加自选」弹窗）一起搬，而不是只搬模板：
  `watchlistTitle` / `watchlistHint` 都由 `WatchlistWidget` 的 expose（`hasPinned`）派生，
  `showAddWatchlistModal` 与 `watchlistWidgetKey` 又只被这一块使用。留在页面里等于让页面
  持有一组「只为一个区块服务」的状态，既难读也让它无法单独演进。

  `AddToWatchlistModal` 放在组件内而不是页面根部：它是 el-dialog（teleport 到 body），
  位置不影响 DOM 层级，但让「打开入口」与「弹窗本体」留在同一个组件里，改交互时不用两处跳。
-->
<template>
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-8">
    <!-- 持仓市值最大资产（风险预警改由顶部消息播报承载，本页不再保留静态风险热力图） -->
    <div
      class="lg:col-span-12 flex flex-col gap-3 card-hover card-enter h-full"
    >
      <!-- info tooltip 承载「怎么置顶 / 怎么取消置顶」这类指引（#1954）。
           此前这段说明是WatchlistWidget 内部一块带 border-b 的文字区，与表头线
           挤在一起像多余的分割线，且文案承诺了组件根本没有的能力
           （「可拖动排序或取消置顶」——首页 widget 既无拖拽也无取消置顶入口，
           用户按提示去找两个都找不到）。
           改为挂在区块标题的 info 图标上：需要时 hover 可读，不占版面、不抢视线。 -->
      <SectionHeader :title="watchlistTitle" :info="watchlistHint">
        <template #action>
          <div class="flex items-center gap-2">
            <el-button
              size="small"
              type="primary"
              plain
              @click="showAddWatchlistModal = true"
            >
              <template #icon><IconifyIconOffline icon="ep:plus" /></template
              >添加
            </el-button>
            <el-button
              size="small"
              link
              @click="router.push('/the-road-not-taken')"
              >特别关注</el-button
            >
            <el-button size="small" link @click="router.push('/watchlist')"
              >查看全部</el-button
            >
          </div>
        </template>
      </SectionHeader>
      <WatchlistWidget
        ref="watchlistWidgetRef"
        :key="watchlistWidgetKey"
        class="flex-1"
        @add="showAddWatchlistModal = true"
        @select="onWatchlistSelect"
      />
    </div>

    <!-- 添加自选弹窗。放在根 div **内部**而不是与之并列：本组件必须是单根，
         否则父页面的 scope id 无法继承到根节点，页面上 `:deep(.card-enter)` /
         `:deep(.card-hover)` 这类规则会整片失效（动画与 hover 静默不动，不报错）。
         它是 el-dialog（teleport 到 body），留在 grid 里不占格子。 -->
    <AddToWatchlistModal
      v-model="showAddWatchlistModal"
      @submitted="onWatchlistChanged"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
// `IconifyIconOffline` 走全局注册（与拆分前的页面一致，不在此处显式 import）：
// 换一个同名但来自 `@/components/ReIcon` 的实现会改变图标渲染方式。
import SectionHeader from "@/components/SectionHeader/index.vue";
import WatchlistWidget from "@/components/WatchlistWidget/index.vue";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import { resolveDetailPath } from "@/utils/productDetailNav";
import type { HomeSummaryItem } from "@/api/types";

defineOptions({ name: "WelcomeWatchlistSection" });

const router = useRouter();

const showAddWatchlistModal = ref(false);
const watchlistWidgetKey = ref(0);
const watchlistWidgetRef = ref<InstanceType<typeof WatchlistWidget> | null>(
  null
);

// 动态标题
const watchlistTitle = computed(() => {
  if (!watchlistWidgetRef.value) return "自选资产";
  return watchlistWidgetRef.value.hasPinned ? "置顶资产" : "持仓市值最大资产";
});

/**
 * 区块指引文案（挂SectionHeader 的 info tooltip，#1954）。
 * 两种状态给的指引不同——有置顶时用户想的是「怎么取消/调顺序」，
 * 无置顶时想的是「怎么置顶」。直接由 widget 的 expose 派生，不另存状态。
 */
const watchlistHint = computed(() =>
  watchlistWidgetRef.value?.hasPinned
    ? "置顶的资产会固定排在最前。取消置顶、调整顺序请到「我的自选」页操作。"
    : "当前展示持仓市值最大的资产。在「我的自选」页点击图钉即可置顶，置顶后会固定显示在这里。"
);

// ===== 事件处理 =====
// 行点击 → 跳产品详情（#1965）：本页承接 WatchlistWidget 的 `select` 事件。
// #1954 曾摘掉这个挂载，因为当时详情页不存在、`onWatchlistSelect` 是个空函数 +
// `// TODO: 跳转到资产详情`——整行 cursor-pointer、行内按钮有 hover 反馈，点了却什么都不
// 发生，是「像 demo」的直接来源。现详情页已落地（路由 #1964 / 接线 #1965），按当时的
// 约定把它接回来，并且**不再是空函数**。
const onWatchlistSelect = async (item: HomeSummaryItem) => {
  try {
    // 摘要行的 asset_type 可能为空、也没有 market → 内部回后端问权威品类，
    // 不在前端按 symbol 形态猜（那正是 #1497 错标成一堆无关基金的根因）
    const path = await resolveDetailPath({
      symbol: item.symbol,
      assetType: item.asset_type,
      venue: item.venue
    });
    if (!path) {
      ElMessage.warning("该品类详情页暂未开放");
      return;
    }
    await router.push(path);
  } catch {
    ElMessage.warning("未找到该产品，可能已下架或代码有误");
  }
};

const onWatchlistChanged = () => {
  watchlistWidgetKey.value++;
};
</script>
