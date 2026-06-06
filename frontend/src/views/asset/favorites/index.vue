<template>
  <div class="favorites-page" :style="{ backgroundColor: 'var(--bg-primary)' }">
    <!-- 顶部区域：诗句 + 标题 -->
    <div class="mb-8">
      <!-- 诗句卡片 -->
      <el-alert
        class="poem-card mb-6 !bg-[#faf7f2] !border-[#e5d9c5] !rounded-2xl !p-6"
        type="info"
        :closable="false"
        show-icon
      >
        <template #icon>
          <IconifyIconOffline icon="ep:reading" class="text-[#b8a99a] text-xl" />
        </template>
        <div class="text-center py-2">
          <p class="text-[#8b7d6b] text-base leading-loose italic tracking-wide font-serif">
            “也许多少年后在某个地方，我会轻声叹息将往事回顾，<br />一片树林里分出两条路，而我选择了人迹更少的一条，<br />从此决定了我一生的道路。”
          </p>
          <p class="text-[#b8a99a] text-xs mt-3">—— 罗伯特·弗罗斯特《未选择的路》</p>
        </div>
      </el-alert>


    </div>

    <!-- 顶部筛选栏 -->
    <div class="filter-bar">
      <el-radio-group v-model="filter" @change="store.setFilter(filter)">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="stock">股票</el-radio-button>
        <el-radio-button value="fund">基金</el-radio-button>
      </el-radio-group>
      <el-select v-model="sort" @change="store.setSort(sort)" size="small" class="sort-select">
        <el-option label="最近更新" value="updated_at" />
        <el-option label="标记时间" value="favorite_at" />
        <el-option label="持有天数" value="holding_days" />
      </el-select>
      <el-input
        v-model="search"
        placeholder="搜索资产..."
        size="small"
        class="search-input"
        @input="store.setSearch(search)"
      />
    </div>

    <!-- 瀑布流容器 -->
    <div v-loading="store.loading" class="waterfall-container">
      <template v-if="store.filteredList.length">
        <Waterfall
          :list="store.filteredList"
          :gutter="20"
          :width="280"
          :breakpoints="{
            1400: { rowPerView: 4 },
            1000: { rowPerView: 3 },
            700: { rowPerView: 2 },
            0: { rowPerView: 1 },
          }"
        >
          <template #default="{ item }">
            <BaseFavoriteCard
              :item="item"
              @view-analysis="onViewAnalysis"
              @write-note="onWriteNote"
              @unfavorite="onUnfavorite"
            />
          </template>
        </Waterfall>
      </template>
      <div v-else class="empty-state">暂无特别关注资产</div>
    </div>

    <!-- 笔记编辑弹窗 -->
    <NoteEditor v-model:visible="noteEditorVisible" :item="currentItem" @saved="onNoteSaved" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useFavoritesStore } from '@/store/favorites';
import { V3waterfall  as Waterfall }  from 'v3-waterfall'
import BaseFavoriteCard from "./components/BaseFavoriteCard.vue"
import NoteEditor from './components/NoteEditor.vue';
import { ElMessage } from 'element-plus';
import { updateWatchlistItem } from '@/api/watchlist';
import 'v3-waterfall/dist/style.css'
const store = useFavoritesStore();
store.fetchList();

const filter = ref('all');
const sort = ref('updated_at');
const search = ref('');

const noteEditorVisible = ref(false);
const currentItem = ref<any>(null);

const onViewAnalysis = (item: any) => {
  ElMessage.info('清仓分析模块开发中');
};
const onWriteNote = (item: any) => {
  currentItem.value = item;
  noteEditorVisible.value = true;
};
const onUnfavorite = async (item: any) => {
  try {
    await updateWatchlistItem(item.id, { favorite: false });
    store.fetchList();
    ElMessage.success('已加回普通自选');
  } catch (e) {
    ElMessage.error('操作失败');
  }
};
const onNoteSaved = () => {
  store.fetchList();
};
</script>

<style scoped>
.poem-card :deep(.el-alert__icon) {
  align-self: flex-start;
  margin-top: 4px;
}
.poem-card :deep(.el-alert__content) {
  width: 100%;
}

/* 让瀑布流背景统一，取消页面多余的 padding */
.favorites-page {
  min-height: 100vh;
  padding: 0;
  margin: 0;
}
/* scoped 穿透写法 */
:deep(.v3-waterfall-item) {
  width: auto !important;
  max-width: none !important;
}

/* 瀑布流容器适配 */
.waterfall-container {
  width: 100%;
  padding: 16px;
  box-sizing: border-box;
}

.starred-card {
  background: var(--bg-card);
  border-radius: 16px; /* 圆角更柔和 */
  padding: 0 0 12px 0; /* 移除上左右内边距，用内部元素自己控制 */
  border-top: 5px solid; /* 色条稍粗，更显眼 */
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
  transition: all 0.3s ease;
  overflow: hidden;
}
.card-header {
  padding: 16px 16px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.sparkline-area {
  padding: 12px 16px;
}
.placeholder-chart {
  height: 80px; /* 占位图更高，视觉重心更稳 */
  background: var(--bg-hover);
  border-radius: 12px;
}
.notes-summary {
  padding: 8px 16px 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.card-actions {
  padding: 12px 16px 0;
  border-top: 1px solid var(--divider-default); /* 分割线 */
  display: flex;
  gap: 8px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background: var(--bg-card);
  margin-bottom: 24px;
  border-radius: 12px;
}
.sort-select {
  width: 120px;
}
.search-input {
  width: 200px;
}
.empty-state {
  text-align: center;
  padding: 80px 0;
  color: var(--text-tertiary);
}
</style>
