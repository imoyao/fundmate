<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import {
  ref,
  watch,
  onMounted,
  TransitionGroup,
  type Component,
  type FunctionalComponent
} from "vue";

const route = useRoute();
const levelList = ref([]);
const router = useRouter();

const getBreadcrumb = (): void => {
  // 直接基于 vue-router 已解析的 matched 链生成面包屑。
  // matched 包含完整的嵌套父级，且 path 已被解析为绝对路径，
  // 不受静态路由经 formatTwoStageRoutes 拍平的影响，
  // 因此绝对/相对 path 的页面（含 :id 动态详情页）都能正确显示多级面包屑，
  // 避免此前相对 path 子页因 findRouteByPath 精确匹配失败而整条消失的问题。
  const matched = router.currentRoute.value.matched.filter(
    item => item?.meta?.title
  );

  // 去除相邻重复的 title（如父级 redirect 到子级导致「投资管理 / 投资管理」）
  const deduped = [];
  matched.forEach(item => {
    const last = deduped[deduped.length - 1];
    if (last && last.meta?.title === item.meta?.title) return;
    deduped.push(item);
  });

  levelList.value = deduped;
};

const handleLink = item => {
  const { redirect, name, path } = item;
  if (redirect) {
    router.push(redirect as any);
  } else {
    if (name) {
      if (item.query) {
        router.push({
          name,
          query: item.query
        });
      } else if (item.params) {
        router.push({
          name,
          params: item.params
        });
      } else {
        router.push({ name });
      }
    } else {
      router.push({ path });
    }
  }
};

/**
 * 后台（隐藏）标签页改用无动画渲染：Chrome 对 hidden 页面暂停 rAF，而 Vue 过渡
 * 的 enter/leave 依赖 nextFrame（双 rAF）推进——后台导航会把 transition-group
 * 卡死在半程（面包屑残留旧页面标题，如「总览/资产总览/个人中心/」叠在一起，
 * 且恢复可见前不会清理）。隐藏时用户本就看不到动画，直接渲染子项即可；
 * 恢复可见后的下一次导航自动切回 transition-group，动画照常。
 * 注意：仅把 name 置空无效——卡点在 rAF 而非 CSS，Vue 仍会等 nextFrame。
 * 用方法而非 computed——visibility 无响应式依赖，computed 会缓存首次求值；
 * 方法在每次渲染时执行，取到导航发生时的实时 visibility。
 * （同类修复见 lay-content 的 transitionMain。）
 */
const PlainGroup: FunctionalComponent = (_props, { slots }) =>
  slots.default ? slots.default() : [];

const getBreadcrumbTransition = (): Component =>
  typeof document !== "undefined" && document.hidden
    ? PlainGroup
    : TransitionGroup;

onMounted(() => {
  getBreadcrumb();
});

watch(
  () => route.path,
  () => {
    getBreadcrumb();
  },
  {
    deep: true
  }
);
</script>

<template>
  <el-breadcrumb class="leading-[50px]! select-none" separator="/">
    <component :is="getBreadcrumbTransition()" name="breadcrumb">
      <el-breadcrumb-item
        v-for="(item, index) in levelList"
        :key="item.path"
        class="inline! items-stretch!"
      >
        <a
          v-if="index !== levelList.length - 1"
          @click.prevent="handleLink(item)"
        >
          {{ item.meta.title }}
        </a>
        <span v-else>{{ item.meta.title }}</span>
      </el-breadcrumb-item>
    </component>
  </el-breadcrumb>
</template>
