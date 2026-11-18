<!--
  DiscrepancyBanner · 全局「数据需要核对」提醒（挂在布局上，除对账中心外全局可见）

  设计约束（#2866 用户实测反馈）：
  - 这里是**提醒 + 入口**，不是详情页。三类问题（域 B 对账差异 / 域 F 交易记录
    信息不完整 / 域 G 缺账本流水）合并成一条紧凑横幅，明细一律去对账中心看。
  - 不铺明细行、不提供「展开全部」、不放大段说明；最多两行文字 + 一个按钮。
  - 三类各自独立取数、独立 catch 降级；显隐只由域 B 的 loading 决定，避免新接口
    超时把整条提醒拖没（#2866 的教训）。
-->
<script setup lang="ts">
import { computed } from "vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import { useDiscrepancyBanner } from "./useDiscrepancyBanner";
import { useDanglingRefBanner } from "./useDanglingRefBanner";
import { useOrphanLedgerBanner } from "./useOrphanLedgerBanner";

defineOptions({ name: "DiscrepancyBanner" });

const { loading, dismissed, count, routeAllowed, dismiss, goToWorkbench } =
  useDiscrepancyBanner();

/** 后两类只取计数，不参与显隐判定：任一接口慢/挂都不该吞掉整条提醒 */
const { count: danglingCount } = useDanglingRefBanner();
const { count: orphanCount } = useOrphanLedgerBanner();

interface NoticePart {
  label: string;
  count: number;
  domain: "B" | "F" | "G";
}

/** 只列真有数据的类别，0 条不占版面 */
const parts = computed<NoticePart[]>(() =>
  (
    [
      { label: "对账差异", count: count.value, domain: "B" },
      {
        label: "交易记录信息不完整",
        count: danglingCount.value,
        domain: "F"
      },
      { label: "缺账本流水", count: orphanCount.value, domain: "G" }
    ] as NoticePart[]
  ).filter(p => p.count > 0)
);

const visible = computed(
  () =>
    routeAllowed.value &&
    !loading.value &&
    !dismissed.value &&
    parts.value.length > 0
);

/** 入口落到条目最多的一类，用户第一眼先看到量最大的那批 */
const targetDomain = computed(() => {
  if (!parts.value.length) return "B";
  return [...parts.value].sort((a, b) => b.count - a.count)[0].domain;
});

function goToDetails(): void {
  goToWorkbench(targetDomain.value);
}
</script>

<template>
  <SoftBanner
    v-if="visible"
    class="recon-banner"
    variant="warning"
    icon="ep:warning-filled"
    dense
    dismissible
    @close="dismiss"
  >
    <div class="recon-notice">
      <div class="recon-notice__text">
        <p class="recon-notice__title">有 {{ parts.length }} 类数据需要核对</p>
        <p class="recon-notice__meta">
          <template v-for="(part, index) in parts" :key="part.domain">
            <span v-if="index > 0" class="recon-notice__sep">·</span>
            {{ part.label }}
            <strong class="recon-notice__num">{{ part.count }}</strong>
          </template>
        </p>
      </div>
      <button type="button" class="recon-notice__action" @click="goToDetails">
        去查看 <span aria-hidden="true">→</span>
      </button>
    </div>
  </SoftBanner>
</template>

<style scoped>
/* 壳（底色/边框/图标/关闭）由 SoftBanner warning + dense 承担，这里只排正文 */
.recon-notice {
  display: flex;
  gap: 16px;
  align-items: center;
  width: 100%;
  min-width: 0;
}

.recon-notice__text {
  flex: 1 1 auto;
  min-width: 0;
}

.recon-notice__title {
  margin: 0;
  font-size: var(--text-body, 14px);
  font-weight: 600;
  line-height: 1.45;
  color: var(--text-primary);
}

.recon-notice__meta {
  margin: 2px 0 0;
  font-size: var(--text-label, 12px);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

.recon-notice__num {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-warning-ink);
}

.recon-notice__sep {
  margin: 0 8px;
  color: var(--text-disabled);
}

.recon-notice__action {
  display: inline-flex;
  flex: 0 0 auto;
  gap: 6px;
  align-items: center;
  padding: 5px 12px;
  font-size: var(--text-label, 12px);
  font-weight: 600;
  color: var(--color-warning-ink);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm);
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;
}

.recon-notice__action:hover {
  background: var(--color-warning-20);
  border-color: var(--color-warning-ink);
}
</style>
