import { defineStore } from "pinia";
import {
  type multiType,
  type positionType,
  store,
  isUrl,
  isEqual,
  isNumber,
  isBoolean,
  getConfig,
  routerArrays,
  storageLocal,
  responsiveStorageNameSpace
} from "../utils";
import { usePermissionStoreHook } from "./permission";
import { sanitizeTags, isRenderableTag } from "@/utils/tagCache";

/** 固定标签（首页等）：缓存为空/全是脏数据时用它兜底 */
function defaultTags(): any[] {
  return sanitizeTags([
    ...routerArrays,
    ...usePermissionStoreHook().flatteningRoutes.filter(v => v?.meta?.fixedTag)
  ] as any);
}

export const useMultiTagsStore = defineStore("pure-multiTags", {
  state: () => {
    const tagsKey = `${responsiveStorageNameSpace()}tags`;
    const cached = storageLocal().getItem<StorageConfigs>(
      `${responsiveStorageNameSpace()}configure`
    )?.multiTagsCache
      ? (storageLocal().getItem<StorageConfigs>(tagsKey) as any)
      : null;

    // 缓存清洗（2026-10-30）：历史版本写进缓存的「无标题条目」会渲染成空白标签块，
    // 且只存在用户本地，干净的 CI/新装环境永远复现不到（用户反馈「好久了」）。
    // 清洗结果**写回缓存**：脏数据只清一次，不会每次刷新又长回来。
    const tags = cached ? sanitizeTags(cached) : defaultTags();
    if (cached && tags.length !== cached.length) {
      storageLocal().setItem(tagsKey, tags);
    }

    return {
      // 存储标签页信息（路由信息）
      multiTags: tags.length ? tags : defaultTags(),
      multiTagsCache: storageLocal().getItem<StorageConfigs>(
        `${responsiveStorageNameSpace()}configure`
      )?.multiTagsCache
    };
  },
  getters: {
    getMultiTagsCache(state) {
      return state.multiTagsCache;
    }
  },
  actions: {
    multiTagsCacheChange(multiTagsCache: boolean) {
      this.multiTagsCache = multiTagsCache;
      if (multiTagsCache) {
        storageLocal().setItem(
          `${responsiveStorageNameSpace()}tags`,
          this.multiTags
        );
      } else {
        storageLocal().removeItem(`${responsiveStorageNameSpace()}tags`);
      }
    },
    tagsCache(multiTags) {
      this.getMultiTagsCache &&
        storageLocal().setItem(
          `${responsiveStorageNameSpace()}tags`,
          multiTags
        );
    },
    handleTags<T>(
      mode: string,
      value?: T | multiType,
      position?: positionType
    ): T {
      switch (mode) {
        case "equal":
          this.multiTags = value;
          this.tagsCache(this.multiTags);
          break;
        case "push":
          {
            const tagVal = value as multiType;
            // 不添加到标签页
            if (tagVal?.meta?.hiddenTag) return;
            // 如果是外链无需添加信息到标签页
            if (isUrl(tagVal?.name)) return;
            // 没有可用标题一律拒绝：旧写法 `tagVal?.meta?.title.length` 只保护了 `meta`，
            // `title` 为 undefined 时会在 `.length` 上抛 TypeError（控制台红色报错、
            // 标签静默丢失）；空字符串则会被渲染成一个没有文字的空白标签块。
            if (!isRenderableTag(tagVal)) return;
            // showLink:false 不添加到标签页
            if (isBoolean(tagVal?.meta?.showLink) && !tagVal?.meta?.showLink)
              return;
            const tagPath = tagVal.path;
            const tagHasExits = this.multiTags.some(tag => {
              return (
                tag.path === tagPath &&
                isEqual(tag?.query, tagVal?.query) &&
                isEqual(tag?.params, tagVal?.params)
              );
            });

            if (tagHasExits) return;

            // 动态路由可打开的最大数量
            const dynamicLevel = tagVal?.meta?.dynamicLevel ?? -1;
            if (dynamicLevel > 0) {
              if (
                this.multiTags.filter(e => e?.path === tagPath).length >=
                dynamicLevel
              ) {
                // 如果当前已打开的动态路由数大于dynamicLevel，替换第一个动态路由标签
                const index = this.multiTags.findIndex(
                  item => item?.path === tagPath
                );
                index !== -1 && this.multiTags.splice(index, 1);
              }
            }
            this.multiTags.push(value);
            this.tagsCache(this.multiTags);
            if (
              getConfig()?.MaxTagsLevel &&
              isNumber(getConfig().MaxTagsLevel)
            ) {
              if (this.multiTags.length > getConfig().MaxTagsLevel) {
                this.multiTags.splice(1, 1);
              }
            }
          }
          break;
        case "splice":
          if (!position) {
            const index = this.multiTags.findIndex(v => v.path === value);
            if (index === -1) return;
            this.multiTags.splice(index, 1);
          } else {
            this.multiTags.splice(position?.startIndex, position?.length);
          }
          this.tagsCache(this.multiTags);
          return this.multiTags;
        case "slice":
          return this.multiTags.slice(-1);
      }
    }
  }
});

export function useMultiTagsStoreHook() {
  return useMultiTagsStore(store);
}
