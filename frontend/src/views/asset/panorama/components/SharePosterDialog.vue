<!--
  SharePosterDialog · 持仓全景长图海报（#1016）

  接收父组件已加载的全景数据，点「生成海报」用原生 Canvas 画长图，弹窗预览 + 下载。
  不自己发请求（数据与页面同源，避免第二份事实源）；不引 html2canvas（见 posterCanvas.ts 说明）。
-->
<template>
  <el-button @click="openDialog">
    <IconifyIconOffline icon="ep:picture-filled" class="mr-1" /> 生成海报
  </el-button>

  <el-dialog
    v-model="visible"
    title="持仓全景海报"
    width="440px"
    align-center
    class="poster-dialog"
    destroy-on-close
  >
    <div class="poster-preview">
      <img v-if="dataUrl" :src="dataUrl" alt="持仓全景海报预览" />
      <div v-else class="poster-empty">正在生成…</div>
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :disabled="!dataUrl" @click="download">
        <IconifyIconOffline icon="ep:download" class="mr-1" /> 下载图片
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { DistributionsData } from "@/api/summary";
import { buildPosterData } from "./posterModel";
import { renderPoster } from "./posterCanvas";

defineOptions({ name: "SharePosterDialog" });

const props = defineProps<{
  totalAssets: number;
  totalLiabilities: number;
  netAssets: number;
  totalPnl: number;
  distributions: DistributionsData | null;
}>();

/** 分布条配色：与全景页资产大类柱状图同族（品牌红 + 暖色系）。 */
const POSTER_COLORS = [
  "#e34f38",
  "#f0a202",
  "#3a7ca5",
  "#6b8e5a",
  "#8f6fb3",
  "#c98b5e"
];

const visible = ref(false);
const dataUrl = ref("");

function localDate(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function openDialog(): void {
  dataUrl.value = "";
  visible.value = true;
  try {
    const canvas = document.createElement("canvas");
    const data = buildPosterData({
      date: localDate(),
      totalAssets: props.totalAssets,
      totalLiabilities: props.totalLiabilities,
      netAssets: props.netAssets,
      totalPnl: props.totalPnl,
      categories: props.distributions?.category_distribution ?? [],
      colors: POSTER_COLORS
    });
    dataUrl.value = renderPoster(canvas, data);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "海报生成失败");
  }
}

function download(): void {
  if (!dataUrl.value) return;
  const a = document.createElement("a");
  a.href = dataUrl.value;
  a.download = `持仓全景-${localDate()}.png`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
</script>

<style scoped>
.poster-preview {
  display: flex;
  justify-content: center;
  min-height: 200px;
  max-height: 60vh;
  overflow: auto;
  background: var(--bg-soft, #f5f0eb);
  border-radius: 12px;
  padding: 12px;
}

.poster-preview img {
  width: 100%;
  max-width: 375px;
  height: auto;
  display: block;
}

.poster-empty {
  color: var(--text-tertiary-ink, #716a60);
  font-size: 14px;
  align-self: center;
}
</style>
