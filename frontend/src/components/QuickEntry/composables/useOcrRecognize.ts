/**
 * 识别链路（#980 拆分产物）：图片 / 文本两种输入 → 候选列表。
 *
 * 这里只有「把用户给的东西变成候选」这件事：文件转 base64、调识别接口、
 * 逐条探测是否已在自选、拼装候选。额度展示与导入动作不在这里
 * （见 useOcrQuota / useOcrImport），本 composable 只在自己的关键节点回调 `fetchUsage`。
 *
 * 三条容易改坏的既有口径：
 * 1. **失败也刷新额度**：识别失败后端会返还配额，不刷就会显示虚低；
 * 2. **空代码必须跳过探测**：后端对空 symbol 会跳过过滤返回整页数据，
 *    会被误判成「已存在」——无代码的候选（如只有组合名的投顾行）一律当新项；
 * 3. **文本 tab 的空结果走行内错误**（不弹全局），图片 tab 无行内锚点才用轻提示。
 */

import { computed, ref } from "vue";
import type { Ref } from "vue";
import { ElMessage } from "element-plus";
import { parseImportText, recognizeImage } from "@/api/ocr";
import type { OcrImportItem } from "@/api/ocr";
import { getWatchlistItems } from "@/api/watchlist";
import { buildCandidates } from "../ocrImportModel";
import type { OcrCandidate } from "../ocrImportModel";

type OcrTab = "image" | "text";

export interface UseOcrRecognizeOptions {
  activeTab: Ref<OcrTab>;
  imageFile: Ref<File | null>;
  textContent: Ref<string>;
  /** 文本域行内错误（切 tab / 重新识别时由调用方清空） */
  textError: Ref<string>;
  /** 额度是否已用尽（用尽时不许再点识别） */
  occupied: Ref<boolean>;
  remaining: Ref<number>;
  /** 识别成功 / 失败 / 空结果后都要刷新余量 */
  fetchUsage: () => void | Promise<void>;
}

export function useOcrRecognize(options: UseOcrRecognizeOptions) {
  const {
    activeTab,
    imageFile,
    textContent,
    textError,
    occupied,
    remaining,
    fetchUsage
  } = options;

  const recognizing = ref(false);
  const candidates = ref<OcrCandidate[]>([]);

  const canRecognize = computed(() => {
    if (occupied.value || remaining.value <= 0) return false;
    if (activeTab.value === "image") return !!imageFile.value;
    return textContent.value.trim().length > 0;
  });

  const selectedCount = computed(
    () => candidates.value.filter(c => c.selected).length
  );

  function toggleCandidate(item: OcrCandidate): void {
    if (item.exists) return;
    item.selected = !item.selected;
  }

  function clearCandidates(): void {
    candidates.value = [];
  }

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

  /**
   * 探测哪些代码已存在于自选（批量候选逐条查询，避免重复导入）。
   * 串行而非并发：命中率靠的是「一条条问」，并发会把后端打出一串短请求风暴，
   * 而批量上限本就只有十几条。
   */
  async function probeExisting(items: OcrImportItem[]): Promise<Set<string>> {
    const set = new Set<string>();
    for (const it of items) {
      const key = (it.symbol || it.code || "").trim();
      if (!key) continue;
      try {
        // 用标准化 symbol 探测（场内如 SH600519），与后端查重口径一致
        const res = await getWatchlistItems({ symbol: key, per_page: 1 });
        const data = (res as { data?: unknown[] }).data ?? [];
        if (data.length > 0) set.add(key);
      } catch {
        // 网络异常不阻断已存在判断，保守当作新项
      }
    }
    return set;
  }

  async function handleRecognize(): Promise<void> {
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
        items =
          (res.data as { items: OcrImportItem[]; usage: unknown }).items ?? [];
      } else {
        const text = textContent.value.trim();
        if (!text) {
          ElMessage.warning("请输入文本内容");
          return;
        }
        const res = await parseImportText(text);
        items =
          (res.data as { items: OcrImportItem[]; usage: unknown }).items ?? [];
      }

      if (items.length === 0) {
        // 文本：行内错误提示（不弹全局）；图片：无行内锚点，保留全局轻提示
        if (activeTab.value === "text") {
          textError.value = "未识别到有效代码，请检查每行是否包含 6 位代码";
        } else {
          ElMessage.info("未能识别出基金，请检查图片清晰度或文本格式");
        }
        // 识别成功但无有效内容：本次配额已消耗，刷新余量展示
        void fetchUsage();
        return;
      }

      const existingSet = await probeExisting(items);
      candidates.value = buildCandidates(items, existingSet);
      // 识别成功已消耗 1 次配额，同步刷新余量展示
      void fetchUsage();
    } catch (e: unknown) {
      // 兜底：识别失败（超时/服务不可用）后端会返还配额，刷新余量避免显示虚低
      void fetchUsage();
      const err = e as {
        code?: string;
        message?: string;
        response?: { status?: number; data?: { message?: string } };
      };
      const status = err?.response?.status;
      if (status === 503) {
        ElMessage.error("AI 识别服务暂时繁忙，请稍后重试（失败不消耗次数）");
      } else if (status === 429) {
        // 可能是配额用完（3004）或限流（3005），用后端 message 区分
        const msg =
          err?.response?.data?.message || "今日 AI 识别次数已用完，请明日再试";
        ElMessage.warning(msg);
      } else if (
        err?.code === "ECONNABORTED" ||
        err?.message?.includes("timeout")
      ) {
        ElMessage.error(
          "识别超时，图片内容可能较多，请稍后重试（失败不消耗次数）"
        );
      } else {
        const msg =
          err?.response?.data?.message || err?.message || "识别失败，请重试";
        ElMessage.error(msg);
      }
    } finally {
      recognizing.value = false;
    }
  }

  return {
    recognizing,
    candidates,
    canRecognize,
    selectedCount,
    toggleCandidate,
    clearCandidates,
    handleRecognize
  };
}
