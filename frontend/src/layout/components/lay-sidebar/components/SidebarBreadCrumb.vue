<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import { ref, watch, onMounted } from "vue";
import { storeToRefs } from "pinia";
import { usePermissionStoreHook } from "@/store/modules/permission";
import { buildBreadcrumb, type BreadcrumbCrumb } from "@/utils/breadcrumb";

const route = useRoute();
const router = useRouter();
const levelList = ref<BreadcrumbCrumb[]>([]);
// 面包屑读「完整路由树」（含 hidden / showLink:false），不是侧边栏的 wholeMenus——
// 后者被 filterTree 剪过，隐藏页在树里根本不存在，只能靠前缀猜父级（详见组件外层注释）
const { breadcrumbMenus } = storeToRefs(usePermissionStoreHook());

/**
 * 兜底：路由树不可用（首屏尚未组装 `breadcrumbMenus`）时退回 `route.matched`。
 *
 * 这条路经**必须**剔掉根 Layout（`path === "/"`）：静态路由被 `formatTwoStageRoutes`
 * 拍平挂到根下，matched 恒为 `[/, 当前页]`，而根节点的 title 是「资产概览」——
 * 留着它，任何页面都会显示成「资产概览 / 某页」，这正是 2026-10-30 实机盘查里
 * 「导入持仓」「股票」「产品详情」等页面的错父级。
 */
function matchedFallback(): BreadcrumbCrumb[] {
  const matched = router.currentRoute.value.matched.filter(
    item => item?.meta?.title && item.path !== "/"
  );
  if (!matched.length) return [];

  // 去除相邻重复 title（父级 redirect 到子级会导致「投资组合 / 投资组合」）
  const deduped: typeof matched = [];
  matched.forEach(item => {
    const last = deduped[deduped.length - 1];
    if (last && last.meta?.title === item.meta?.title) return;
    deduped.push(item);
  });

  return deduped.map((item, index) => {
    const isLast = index === deduped.length - 1;
    return {
      title: item.meta.title as string,
      to: isLast ? null : item.redirect ? String(item.redirect) : item.path,
      key: item.path
    };
  });
}

/**
 * 生成面包屑。
 *
 * 优先用侧边栏菜单树（层级与用户看到的一致）；取不到再退回 matched；
 * 两级都空时**至少渲染当前页标题**——宁可少一级，也不能让面包屑位置空着。
 */
const getBreadcrumb = (): void => {
  const path = route.path;
  const currentTitle = route.meta?.title as string | undefined;

  const fromMenu = buildBreadcrumb(
    breadcrumbMenus.value as any,
    path,
    currentTitle
  );
  if (fromMenu.length) {
    levelList.value = fromMenu;
    return;
  }

  const fallback = matchedFallback();
  if (fallback.length) {
    levelList.value = fallback;
    return;
  }

  levelList.value = currentTitle
    ? [{ title: currentTitle, to: null, key: path }]
    : [];
};

const handleLink = (item: BreadcrumbCrumb) => {
  if (!item.to) return;
  router.push(item.to);
};

/**
 * 这里**不再包 transition-group**（2026-10-30 移除）。
 *
 * 旧实现用 `<TransitionGroup name="breadcrumb">` 给每一级做进出过渡，配套 CSS
 * 里 `.breadcrumb-leave-active { position: absolute }`——离场的面包屑被绝对定位
 * 留在 DOM 里等 0.3s 过渡收尾，而 Vue 过渡靠 double-rAF 推进：标签页在后台、
 * 或连续导航让两次过渡重叠时，leave 回调不会执行，旧面包屑就永久留在列表里。
 *
 * 实测证据（Playwright 逐个点击侧边栏 19 个叶子，dev :8850）：
 *   移除前 → 点「我的自选」读到
 *            `资产管理/品类持仓/同类优选/观察名单/我的自选`
 *            ——前三级是上一页残留，正是「面包屑不对」的真身；
 *            19 项里 1 项失败。
 *   移除后 → 同一脚本 19/19 全对，且只改 `location.hash` 导航时 0 控制台报错。
 *
 * 面包屑是 2~3 个短词的位置指示，本来就不需要动画。去掉过渡后渲染与路由同步，
 * 顺带解决了「后台标签页里面包屑卡住不更新」的老问题（此前用 PlainGroup 绕）。
 */
onMounted(() => {
  getBreadcrumb();
});

watch(
  // 同时盯 path 与路由树：首屏 breadcrumbMenus 是异步就绪的，只盯 path 会让
  // 先到的那一帧用 matched 兜底，等菜单组装好后**不会再刷新**。
  () => [route.path, breadcrumbMenus.value.length] as const,
  () => {
    getBreadcrumb();
  },
  { deep: true, immediate: false }
);
</script>

<template>
  <el-breadcrumb class="leading-[50px]! select-none" separator="/">
    <el-breadcrumb-item
      v-for="item in levelList"
      :key="item.key"
      class="inline! items-stretch!"
    >
      <a v-if="item.to" @click.prevent="handleLink(item)">
        {{ item.title }}
      </a>
      <span v-else>{{ item.title }}</span>
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>
