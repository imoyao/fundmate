<!--
  RoadEmptyState · 空状态

  design.md「空状态与加载态」硬规范：严禁干瘪的「暂无数据」，必须使用
  珊瑚红单色细线鹦鹉螺插画 + 品牌收尾定调文案。
  插画复用仓库既有资产 assets/login/nautilus-light.svg（单色 #E34F38 线稿），
  不新增外部依赖，也不引入 emoji。
-->
<template>
  <div class="road-empty">
    <img class="road-empty__art" :src="nautilus" alt="" aria-hidden="true" />
    <p class="road-empty__slogan">潮有涨落，壳有深浅。算得清，才无患。</p>
    <p class="road-empty__desc">
      {{
        filtered
          ? "当前筛选下还没有标的，换个胶囊看看，或者把状态切回「全部状态」。"
          : "把特别耗费过精力、或曾经长期持有的标的标记「特别关注」，它们会出现在这里，等你回头看看。"
      }}
    </p>
    <div class="road-empty__actions">
      <el-button
        v-if="!filtered"
        size="small"
        type="primary"
        @click="$emit('go-watchlist')"
        >去自选标记特别关注</el-button
      >
      <el-button
        v-if="devMode"
        size="small"
        plain
        @click="$emit('toggle-preview')"
      >
        {{ previewMode ? "关闭设计预览" : "看看设计示例" }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import nautilus from "@/assets/login/nautilus-light.svg";

// 示例预览入口仅开发模式可见（生产构建隐藏）
const devMode = import.meta.env.DEV;

defineProps<{
  /** 因筛选导致为空（而非本就没有数据）时，文案与操作相应变化 */
  filtered: boolean;
  previewMode: boolean;
}>();

defineEmits<{
  (e: "go-watchlist"): void;
  (e: "toggle-preview"): void;
}>();
</script>

<style scoped>
/* 品牌呼吸动效（design.md：6-8s scale 呼吸） */
@keyframes road-breathe {
  0%,
  100% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.03);
  }
}

@media (prefers-reduced-motion: reduce) {
  .road-empty__art {
    animation: none;
  }
}

.road-empty {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  padding: 56px 24px 64px;
  text-align: center;
}

.road-empty__art {
  width: 168px;
  height: auto;
  margin-bottom: 8px;
  opacity: 0.9;
  animation: road-breathe 7s ease-in-out infinite;
}

.road-empty__slogan {
  font-family: Georgia, "Songti SC", "Noto Serif SC", serif;
  font-size: 15px;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}

.road-empty__desc {
  max-width: 420px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-tertiary);
}

.road-empty__actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}
</style>
