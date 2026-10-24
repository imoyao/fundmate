<script setup lang="ts">
import { emitter } from "@/utils/mitt";
import { useTags } from "../../hooks/useTag";
import { onClickOutside } from "@vueuse/core";
import TagChrome from "./components/TagChrome.vue";
import { ref, watch, unref, onBeforeUnmount } from "vue";
import { useTagScroll } from "./tagView/useTagScroll";
import { useTagMenu } from "./tagView/useTagMenu";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import { delay, useResizeObserver } from "@pureadmin/utils";

import ArrowDown from "~icons/ri/arrow-down-s-line";
import ArrowRightSLine from "~icons/ri/arrow-right-s-line";
import ArrowLeftSLine from "~icons/ri/arrow-left-s-line";

const {
  Close,
  route,
  router,
  visible,
  showTags,
  instance,
  multiTags,
  tagsViews,
  buttonTop,
  buttonLeft,
  showModel,
  translateX,
  isFixedTag,
  pureSetting,
  activeIndex,
  getTabStyle,
  isScrolling,
  iconIsActive,
  linkIsActive,
  currentSelect,
  scheduleIsActive,
  getContextMenuStyle,
  closeMenu,
  onMounted,
  onMouseenter,
  onMouseleave,
  onContentFullScreen
} = useTags();

const contextmenuRef = ref();

const {
  tabDom,
  containerDom,
  scrollbarDom,
  isShowArrow,
  dynamicTagView,
  handleScroll,
  handleWheel
} = useTagScroll({ instance, route, multiTags, translateX, isScrolling });

const {
  showMenuModel,
  openMenu,
  handleCommand,
  selectTag,
  deleteMenu,
  toggleContentFullScreen
} = useTagMenu({
  route,
  router,
  multiTags,
  tagsViews,
  currentSelect,
  visible,
  buttonTop,
  buttonLeft,
  containerDom,
  closeMenu,
  onContentFullScreen,
  dynamicTagView
});

/** 侧边栏切换时，把目标路由对应的标签补进标签栏 */
function dynamicRouteTag(value: string): void {
  const hasValue = multiTags.value.some(item => item.path === value);
  if (hasValue) return;

  function concatPath(arr: object[], path: string) {
    arr.forEach((arrItem: any) => {
      if (arrItem.path === path) {
        useMultiTagsStoreHook().handleTags("push", {
          path,
          meta: arrItem.meta,
          name: arrItem.name
        });
      } else if (arrItem.children && arrItem.children.length > 0) {
        concatPath(arrItem.children, path);
      }
    });
  }
  concatPath(router.options.routes as any, value);
}

/** 触发 tags 标签切换：按 name/query/params 优先，退化为 path */
function tagOnClick(item: any): void {
  const { name, path } = item;
  if (name) {
    if (item.query) {
      router.push({ name, query: item.query });
    } else if (item.params) {
      router.push({ name, params: item.params });
    } else {
      router.push({ name });
    }
  } else {
    router.push({ path });
  }
  emitter.emit("tagOnClick", item);
}

onClickOutside(contextmenuRef, closeMenu, { detectIframe: true });

watch(route, () => {
  activeIndex.value = -1;
  void dynamicTagView();
});

onMounted(() => {
  if (!instance) return;

  // 根据当前路由初始化操作标签页的禁用状态
  showMenuModel(route.fullPath);

  // 触发隐藏标签页
  emitter.on("tagViewsChange", (key: any) => {
    if (unref(showTags as any) === key) return;
    (showTags as any).value = key;
  });

  // 改变标签风格
  emitter.on("tagViewsShowModel", key => {
    showModel.value = key;
  });

  // 接收侧边栏切换传递过来的参数
  emitter.on("changLayoutRoute", (indexPath: string) => {
    dynamicRouteTag(indexPath);
    setTimeout(() => {
      showMenuModel(indexPath);
    });
  });

  useResizeObserver(scrollbarDom, dynamicTagView);
  delay().then(() => dynamicTagView());
});

onBeforeUnmount(() => {
  // 解绑公共事件，防止多次触发
  emitter.off("tagViewsChange");
  emitter.off("tagViewsShowModel");
  emitter.off("changLayoutRoute");
});
</script>

<template>
  <div v-if="!showTags" ref="containerDom" class="tags-view">
    <span v-show="isShowArrow" class="arrow-left">
      <IconifyIconOffline
        :icon="ArrowLeftSLine"
        role="button"
        tabindex="0"
        aria-label="向左滚动标签"
        @keydown.enter="handleScroll(200)"
        @click="handleScroll(200)"
      />
    </span>
    <div
      ref="scrollbarDom"
      class="scroll-container"
      :class="showModel === 'chrome' && 'chrome-scroll-container'"
      @wheel.prevent="handleWheel"
    >
      <div ref="tabDom" class="tab select-none" :style="getTabStyle">
        <div
          v-for="(item, index) in multiTags"
          :ref="'dynamic' + index"
          :key="index"
          :class="[
            'scroll-item is-closable',
            linkIsActive(item),
            showModel === 'chrome' && 'chrome-item',
            isFixedTag(item) && 'fixed-tag'
          ]"
          role="button"
          tabindex="0"
          @contextmenu.prevent="openMenu(item, $event)"
          @mouseenter.prevent="onMouseenter(index)"
          @mouseleave.prevent="onMouseleave(index)"
          @keydown.enter="tagOnClick(item)"
          @click="tagOnClick(item)"
        >
          <template v-if="showModel !== 'chrome'">
            <span
              class="tag-title dark:text-text_color_primary! dark:hover:text-primary!"
            >
              {{ item.meta.title }}
            </span>
            <span
              v-if="
                isFixedTag(item)
                  ? false
                  : iconIsActive(item, index) ||
                    (index === activeIndex && index !== 0)
              "
              class="el-icon-close"
              role="button"
              tabindex="0"
              aria-label="关闭标签"
              @keydown.enter.stop="deleteMenu(item)"
              @click.stop="deleteMenu(item)"
            >
              <IconifyIconOffline :icon="Close" />
            </span>
            <span
              v-if="showModel !== 'card'"
              :ref="'schedule' + index"
              :class="[scheduleIsActive(item)]"
            />
          </template>
          <div v-else class="chrome-tab">
            <div class="chrome-tab__bg">
              <TagChrome />
            </div>
            <span class="tag-title">
              {{ item.meta.title }}
            </span>
            <span
              v-if="isFixedTag(item) ? false : index !== 0"
              class="chrome-close-btn"
              role="button"
              tabindex="0"
              aria-label="关闭标签"
              @keydown.enter.stop="deleteMenu(item)"
              @click.stop="deleteMenu(item)"
            >
              <IconifyIconOffline :icon="Close" />
            </span>
            <span class="chrome-tab-divider" />
          </div>
        </div>
      </div>
    </div>
    <span v-show="isShowArrow" class="arrow-right">
      <IconifyIconOffline
        :icon="ArrowRightSLine"
        role="button"
        tabindex="0"
        aria-label="向右滚动标签"
        @keydown.enter="handleScroll(-200)"
        @click="handleScroll(-200)"
      />
    </span>
    <!-- 右键菜单按钮 -->
    <transition name="el-zoom-in-top">
      <ul
        v-show="visible"
        ref="contextmenuRef"
        :key="Math.random()"
        :style="getContextMenuStyle"
        class="contextmenu"
      >
        <div
          v-for="(item, key) in tagsViews.slice(0, 6)"
          :key="key"
          style="display: flex; align-items: center"
        >
          <li
            v-if="item.show"
            role="button"
            tabindex="0"
            @keydown.enter="selectTag(key, item)"
            @click="selectTag(key, item)"
          >
            <IconifyIconOffline :icon="item.icon" />
            {{ item.text }}
          </li>
        </div>
      </ul>
    </transition>
    <!-- 右侧功能按钮 -->
    <!-- 内容区全屏常显入口（2026-09-05）：
         此前只能从下方倒三角下拉里点「内容区全屏」，几乎不可发现。
         现把该操作提为常显切换按钮，紧邻倒三角左侧：
         图标刻意与浏览器全屏（ri/fullscreen，头像旁）区分，用「内容扩展开/收起」语义；
         倒三角菜单里的原项保留（提供一致的键盘/菜单路径，双入口互不冲突）。 -->
    <el-tooltip
      :content="pureSetting.hiddenSideBar ? '退出内容区全屏' : '内容区全屏'"
      placement="bottom"
    >
      <span
        class="arrow-down mr-2"
        role="button"
        tabindex="0"
        :aria-label="
          pureSetting.hiddenSideBar ? '退出内容区全屏' : '内容区全屏'
        "
        @click="toggleContentFullScreen"
        @keydown.enter.prevent="toggleContentFullScreen"
        @keydown.space.prevent="toggleContentFullScreen"
      >
        <IconifyIconOffline
          :icon="pureSetting.hiddenSideBar ? 'ep:fold' : 'ep:expand'"
          class="dark:text-white"
        />
      </span>
    </el-tooltip>
    <el-dropdown
      trigger="click"
      placement="bottom-end"
      @command="handleCommand"
    >
      <span class="arrow-down">
        <IconifyIconOffline :icon="ArrowDown" class="dark:text-white" />
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="(item, key) in tagsViews"
            :key="key"
            :command="{ key, item }"
            :divided="item.divided"
            :disabled="item.disabled"
          >
            <IconifyIconOffline :icon="item.icon" />
            {{ item.text }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<style lang="scss" scoped>
@import url("./index.scss");
</style>
