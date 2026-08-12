<template>
  <el-dialog
    v-model="visible"
    class="ocr-import-dialog"
    title="AI 批量导入"
    width="640px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <!-- 顶部：剩余次数提示 -->
    <div class="usage-banner" :class="usageStateClass">
      <IconifyIconOffline icon="ep:picture" class="usage-banner__icon" />
      <span>
        今日还可使用
        <strong>{{ remaining }} </strong>
        次{{ remainingText }}
      </span>
    </div>

    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <!-- ── 图片识别 ── -->
      <el-tab-pane name="image" label="上传图片">
        <el-upload
          drag
          accept="image/*"
          :auto-upload="false"
          :limit="1"
          :show-file-list="true"
          :on-change="onFileChange"
          :on-remove="onFileRemove"
          class="ocr-upload"
        >
          <IconifyIconOffline icon="ep:upload" class="el-icon--upload" />
          <div class="el-upload__text">拖拽图片到此处，或<em>点击选择</em></div>
          <template #tip>
            <div class="el-upload__tip">
              支持券商 / 天天基金等 App 持仓截图，文件不超过 5MB
            </div>
          </template>
        </el-upload>
      </el-tab-pane>

      <!-- ── 文本解析 ── -->
      <el-tab-pane name="text" label="粘贴文本">
        <el-input
          v-model="textContent"
          type="textarea"
          :rows="8"
          resize="vertical"
          placeholder="粘贴基金列表文本，例如：&#10;110011 易方达中小盘&#10;005827 易方达蓝筹精选"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 识别结果确认 -->
    <div v-if="candidates.length > 0" class="result-section">
      <div class="result-head">
        <span>识别到 {{ candidates.length }} 条，可勾选导入</span>
      </div>
      <div class="candidate-list">
        <div
          v-for="item in candidates"
          :key="item.code"
          class="candidate-row"
          :class="{ 'is-exists': item.exists }"
          @click="toggleCandidate(item)"
        >
          <el-checkbox
            :model-value="item.selected"
            :disabled="item.exists"
            @change="toggleCandidate(item)"
          />
          <span class="candidate-code">{{ item.code }}</span>
          <span class="candidate-name">{{ item.name }}</span>
          <el-tag v-if="item.exists" size="small" type="info">已在自选</el-tag>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        v-if="candidates.length === 0"
        type="primary"
        :loading="recognizing"
        :disabled="!canRecognize"
        @click="handleRecognize"
      >
        识别
      </el-button>
      <el-button
        v-else
        type="primary"
        :loading="importing"
        :disabled="selectedCount === 0"
        @click="handleImport"
      >
        导入选中（{{ selectedCount }}）
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import type { UploadFile } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { parseImportText, recognizeImage, getOcrUsage } from "@/api/ocr";
import { createWatchlistItem, getWatchlistItems } from "@/api/watchlist";
import type { OcrImportItem } from "@/api/ocr";

const props = defineProps<{
  modelValue: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  imported: [count: number];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const activeTab = ref<"image" | "text">("image");
const imageFile = ref<File | null>(null);
const textContent = ref("");
const recognizing = ref(false);
const importing = ref(false);

const remaining = ref(0);
const quota = ref(5);
const occupied = ref(false);

const remainingText = computed(() => {
  if (occupied.value) return "（额度已用尽，请明日再试）";
  if (remaining.value <= 2) return "（额度紧张，谨慎使用）";
  return "";
});
const usageStateClass = computed(() => {
  if (occupied.value) return "is-used-up";
  if (remaining.value <= 2) return "is-low";
  return "";
});

interface Candidate extends OcrImportItem {
  exists: boolean;
  selected: boolean;
}
const candidates = ref<Candidate[]>([]);

const canRecognize = computed(() => {
  if (occupied.value || remaining.value <= 0) return false;
  if (activeTab.value === "image") return !!imageFile.value;
  return textContent.value.trim().length > 0;
});

const selectedCount = computed(
  () => candidates.value.filter(c => c.selected).length
);

const onFileChange = (file: UploadFile) => {
  imageFile.value = file.raw ?? null;
  candidates.value = [];
};
const onFileRemove = () => {
  imageFile.value = null;
  candidates.value = [];
};

const handleTabChange = () => {
  candidates.value = [];
};

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // 去掉 data URL 前缀，保留纯 base64
      const base64 = result.split(",")[1] ?? result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const toggleCandidate = (item: Candidate) => {
  if (item.exists) return;
  item.selected = !item.selected;
};

const handleRecognize = async () => {
  if (remaining.value <= 0) {
    ElMessage.warning("今日 AI 导入额度已用完，请明日再试");
    return;
  }
  recognizing.value = true;
  try {
    let items: OcrImportItem[] = [];
    if (activeTab.value === "image") {
      if (!imageFile.value) {
        ElMessage.warning("请先选择图片");
        return;
      }
      const base64 = await fileToBase64(imageFile.value);
      const res = await recognizeImage(base64);
      items = res.data?.items ?? [];
    } else {
      const text = textContent.value.trim();
      if (!text) {
        ElMessage.warning("请输入文本内容");
        return;
      }
      const res = await parseImportText(text);
      items = res.data?.items ?? [];
    }

    if (items.length === 0) {
      ElMessage.info("未能识别出基金，请检查图片清晰度或文本格式");
      return;
    }

    const existingSet = await probeExisting(items);
    candidates.value = items.map(it => ({
      ...it,
      exists: existingSet.has(it.code),
      selected: !existingSet.has(it.code)
    }));
    // 识别成功已消耗 1 次配额，同步刷新余量展示
    void fetchUsage();
  } catch (e: any) {
    const msg = e?.response?.data?.message || e?.message || "识别失败，请重试";
    ElMessage.error(msg);
  } finally {
    recognizing.value = false;
  }
};

// 探测哪些代码已存在于自选（对批量候选，逐条查询看是否已存在，避免重复导入）
async function probeExisting(items: OcrImportItem[]): Promise<Set<string>> {
  const set = new Set<string>();
  for (const it of items) {
    try {
      const res = await getWatchlistItems({ symbol: it.code, per_page: 1 });
      const data = (res as any).data ?? [];
      if (data.length > 0) set.add(it.code);
    } catch {
      // 网络异常不阻断已存在判断，保守当作新项
    }
  }
  return set;
}

const handleImport = async () => {
  const toImport = candidates.value.filter(c => c.selected && !c.exists);
  if (toImport.length === 0) {
    ElMessage.info("没有需要导入的资产");
    return;
  }
  importing.value = true;
  let success = 0;
  let skipped = 0;
  const failed: string[] = [];
  for (const item of toImport) {
    try {
      await createWatchlistItem({
        symbol: item.code,
        asset_type: item.type || (item.code.startsWith("5") ? "etf" : "fund"),
        venue: "OTC",
        add_reason: "AI 批量导入"
      });
      success++;
    } catch (e: any) {
      if (e?.response?.status === 409) {
        skipped++;
      } else {
        failed.push(item.code);
      }
    }
  }
  importing.value = false;

  if (failed.length > 0) {
    ElMessage.error(
      `导入完成：成功 ${success} 条，跳过已存在 ${skipped} 条，失败 ${
        failed.length
      } 条（${failed.join("、")}）`
    );
  } else {
    ElMessage.success(
      `导入成功 ${success} 条${skipped > 0 ? `，跳过已存在 ${skipped} 条` : ""}`
    );
  }

  if (success > 0) {
    emit("imported", success);
  }
  reset();
};

const fetchUsage = async () => {
  try {
    const res = await getOcrUsage();
    const data = res.data;
    remaining.value = data?.remaining ?? 0;
    quota.value = data?.quota ?? 5;
    occupied.value = data?.remaining <= 0;
  } catch {
    remaining.value = 5;
    quota.value = 5;
    occupied.value = false;
  }
};

const reset = () => {
  candidates.value = [];
  textContent.value = "";
  imageFile.value = null;
};

onMounted(() => {
  if (visible.value) {
    fetchUsage();
  }
});
</script>

<style scoped>
.ocr-import-dialog :deep(.el-dialog__body) {
  padding: 20px;
  font-size: 15px;
}

.usage-banner {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: 8px;

  &__icon {
    color: var(--text-tertiary);
  }

  strong {
    color: var(--text-primary);
  }

  &.is-low {
    color: var(--color-warning, #d97706);
    background: color-mix(
      in srgb,
      var(--color-warning, #d97706) 10%,
      var(--bg-soft)
    );
    border-color: color-mix(
      in srgb,
      var(--color-warning, #d97706) 35%,
      var(--border-light)
    );
  }

  &.is-used-up {
    color: var(--text-tertiary);
  }
}

.ocr-upload :deep(.el-upload-dragger) {
  background: var(--bg-soft);
  border-color: var(--border-default);
}

.result-section {
  margin-top: 16px;
}

.result-head {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--border-light);
  border-radius: 8px;
}

.candidate-row {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px 12px;
  font-size: 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);

  &:hover {
    background: var(--bg-soft);
  }

  &.is-exists {
    opacity: 0.6;
  }

  .candidate-code {
    font-family: var(--font-mono);
    font-weight: 600;
    color: var(--text-primary);
  }

  .candidate-name {
    flex: 1;
    color: var(--text-secondary);
  }
}
</style>
