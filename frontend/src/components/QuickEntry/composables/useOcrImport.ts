/**
 * 导入动作（#980 拆分产物）：把勾选的候选逐条落成自选条目。
 *
 * 逐条 POST 而不是批量接口：后端没有批量创建，且逐条才能精确区分
 * 「成功 / 已存在（409）/ 失败」，结果文案要能点名失败代码。
 *
 * 409 视为「跳过」而不是失败——用户重复导入同一批是常见操作，
 * 报错会让人以为出问题了。
 */

import { ref } from "vue";
import type { Ref } from "vue";
import { ElMessage } from "element-plus";
import { createWatchlistItem } from "@/api/watchlist";
import { buildCreatePayload, summarizeImport } from "../ocrImportModel";
import type { OcrCandidate } from "../ocrImportModel";

export interface UseOcrImportOptions {
  candidates: Ref<OcrCandidate[]>;
  /** 导入时要一并归入的自定义分组 id */
  selectedGroupIds: Ref<number[]>;
  /** 有成功条目时回调（父层用于刷新列表 + emit imported） */
  onImported: (count: number) => void;
  /** 收尾：无论成功失败都复位弹窗（清候选 / 清文案 / 记脏基线） */
  onFinished: () => void;
}

export function useOcrImport(options: UseOcrImportOptions) {
  const { candidates, selectedGroupIds, onImported, onFinished } = options;
  const importing = ref(false);

  async function handleImport(): Promise<void> {
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
        await createWatchlistItem(
          buildCreatePayload(item, selectedGroupIds.value)
        );
        success++;
      } catch (e: unknown) {
        if (
          (e as { response?: { status?: number } })?.response?.status === 409
        ) {
          skipped++;
        } else {
          failed.push(item.code);
        }
      }
    }
    importing.value = false;

    const { level, message } = summarizeImport({ success, skipped, failed });
    if (level === "error") ElMessage.error(message);
    else ElMessage.success(message);

    if (success > 0) onImported(success);
    onFinished();
  }

  return { importing, handleImport };
}
