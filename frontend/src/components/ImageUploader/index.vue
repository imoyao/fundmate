<template>
  <div class="image-uploader" @paste="handlePaste">
    <el-upload
      drag
      accept="image/*"
      :auto-upload="false"
      :limit="1"
      :show-file-list="false"
      :on-change="onFileChange"
      :on-remove="onFileRemove"
      class="image-uploader__upload"
    >
      <IconifyIconOffline
        icon="mdi:cloud-upload-outline"
        class="image-uploader__icon"
      />
      <div class="image-uploader__text">
        拖拽图片到此处，或<em>点击选择</em>
      </div>
      <!-- 底部说明：普通说明与快捷操作分两行、不同层级，避免视觉粘连 -->
      <template #tip>
        <div class="image-uploader__tip">
          <p class="image-uploader__tip-line">{{ tip }}</p>
          <p class="image-uploader__tip-hint">
            高效技巧：可直接 Ctrl+V 粘贴截图
          </p>
        </div>
      </template>
    </el-upload>

    <!-- 已选/粘贴图片预览 -->
    <div v-if="modelValue" class="image-uploader__preview">
      <img :src="previewUrl" class="image-uploader__preview-img" alt="" />
      <div class="image-uploader__preview-meta">
        <span class="image-uploader__preview-name">{{ modelValue.name }}</span>
        <span class="image-uploader__preview-size"
          >{{ (modelValue.size / 1024).toFixed(0) }} KB</span
        >
      </div>
      <el-button text type="primary" @click="clearFile">重新选择</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 通用单图上传组件（Web 端）。
 *
 * 三种来源：① 点击选择本地文件 ② 拖拽 ③ 剪贴板粘贴（Ctrl+V 截图）。
 * 供 OCR 截图导入 / 持仓截图导入等场景复用，v-model 绑定 File | null。
 *
 * 移动端说明（暂不支持剪贴板粘贴，2026-08-13 决策）：
 * - iOS Safari 的 ClipboardEvent.clipboardData.items 不暴露图片，getAsFile() 恒为空，
 *   故剪贴板粘贴为桌面端能力；
 * - 后续若需移动端 H5 支持，走 navigator.clipboard.read()（要求 HTTPS + 用户手势 + 权限）
 *   或原生相册选择（el-upload 的 capture 属性），本组件 Web 端实现不受影响。
 */
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type { UploadFile } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";

const props = withDefaults(
  defineProps<{
    /** 当前选中的图片文件（v-model） */
    modelValue: File | null;
    /** 上传区提示文案（默认含 5MB 上限提示） */
    tip?: string;
  }>(),
  { tip: "支持 App 持仓截图，文件不超过 5MB" }
);

const emit = defineEmits<{
  "update:modelValue": [value: File | null];
  change: [file: File | null];
}>();

const previewUrl = ref("");

// 文件变化时生成预览图（dataURL），清除时清空
watch(
  () => props.modelValue,
  val => {
    if (val) {
      const reader = new FileReader();
      reader.onload = () => {
        previewUrl.value = reader.result as string;
      };
      reader.readAsDataURL(val);
    } else {
      previewUrl.value = "";
    }
  },
  { immediate: true }
);

const setFile = (file: File) => {
  emit("update:modelValue", file);
  emit("change", file);
};

const clearFile = () => {
  emit("update:modelValue", null);
  emit("change", null);
};

const onFileChange = (file: UploadFile) => {
  const raw = file.raw;
  if (raw) setFile(raw);
};
const onFileRemove = () => clearFile();

// 剪贴板粘贴（桌面端）：从 clipboardData 提取图片文件
const handlePaste = (e: ClipboardEvent) => {
  const items = e.clipboardData?.items;
  if (!items) return;
  for (const item of Array.from(items)) {
    if (item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) {
        setFile(file);
        ElMessage.success("已读取剪贴板图片");
        e.preventDefault();
        return;
      }
    }
  }
};
</script>

<style scoped>


/* 呼吸感：边框在 --border-default 与 --brand-400 之间缓慢呼吸 */
@keyframes upload-breathe {
  0%,
  100% {
    border-color: var(--border-default);
  }

  50% {
    border-color: var(--brand-400);
  }
}

.image-uploader__upload {
  :deep(.el-upload-dragger) {
    /* 高度压缩：--space-standard 内边距，聚焦核心拖拽区 */
    padding: var(--space-standard);
    background: var(--bg-soft);
    border: 1px dashed var(--border-default);
    border-radius: var(--radius-md);
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease;
    animation: upload-breathe 2.4s ease-in-out infinite; /* 呼吸虚线框：引导上传 */
  }

  :deep(.el-upload-dragger:hover) {
    background: var(--brand-100);
    border-color: var(--brand-700);
    animation: none; /* 交互中暂停呼吸 */
  }

  :deep(.el-upload-dragger.is-dragover) {
    background: var(--brand-100);
    border-color: var(--brand-700);
    animation: none;
  }
}

.image-uploader__icon {
  margin-bottom: var(--space-3);
  font-size: 40px;
  color: var(--brand-700);
}

.image-uploader__text {
  margin-top: 0;
  font-size: var(--text-body);
  color: var(--text-secondary); /* 弱化引导句 */

  em {
    font-style: normal;
    font-weight: 600;
    color: var(--brand-700); /* 强化交互点 */
  }
}

/* 底部说明：两行独立层级，避免视觉粘连 */
.image-uploader__tip {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-top: var(--space-3);

  &-line {
    margin: 0;
    font-size: var(--text-label);
    color: var(--text-tertiary);
  }

  &-hint {
    margin: 0;
    font-size: var(--text-label);
    color: var(--brand-700);
  }
}

/* ============================================
   已选/粘贴图片预览条
   ============================================ */
.image-uploader__preview {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-compact);
  margin-top: var(--space-3);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);

  &-img {
    width: 72px;
    height: 48px;
    object-fit: cover;
    border-radius: var(--radius-sm);
  }

  &-meta {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  &-name {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-small);
    color: var(--text-primary);
    white-space: nowrap;
  }

  &-size {
    font-size: var(--text-label);
    color: var(--text-tertiary);
  }
}

/* ============================================
   上传区：软表面 + 虚线边框 + 品牌色 hover（对齐 design.md）
   ============================================ */
</style>
