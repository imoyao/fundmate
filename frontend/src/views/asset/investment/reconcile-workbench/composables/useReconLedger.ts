import { ref } from "vue";
import { getLedgers } from "@/api/ledger";

/**
 * 账本名缓存（2026-11-07 第二轮）。
 *
 * 抽屉里的「来龙去脉」和「投资轨迹」都要显示账本名，两个组件各取一次
 * `GET /api/ledgers/` 会重复请求；放模块级缓存，一次取齐、多处读。
 * 取不到时**降级显示编号**，绝不因为查名字失败就让整个抽屉打不开。
 */
const names = ref<Record<number, string>>({});
let inflight: Promise<void> | null = null;

export function useReconLedger() {
  function ensure(): Promise<void> {
    if (inflight) return inflight;
    inflight = getLedgers(true)
      .then(res => {
        const list = res?.data ?? [];
        const next: Record<number, string> = {};
        for (const item of list) {
          if (item?.id != null && item?.name) {
            next[Number(item.id)] = String(item.name);
          }
        }
        names.value = next;
      })
      .catch(() => {
        /* 拿不到账本名就显示编号，不阻断抽屉 */
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  }

  function nameOf(id: number | null | undefined): string {
    if (id === null || id === undefined || !Number.isFinite(id)) {
      return "未归账本";
    }
    return names.value[Number(id)] ?? `账本编号 ${id}`;
  }

  return { ensure, nameOf };
}
