<template>
  <!--
    待入库草稿摘要（P1）：默认折叠成一行，展开后包两个 RecognizerCandidatesPanel。
    草稿是「要确认入库的事」，不是域 tab，首屏不再常驻两张大表。
  -->
  <section v-if="total > 0" class="recon-draft-summary">
    <button
      type="button"
      class="recon-draft-summary__toggle"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="recon-draft-summary__label">
        有 {{ total }} 条待入库草稿
      </span>
      <span class="recon-draft-summary__hint">{{
        open ? "收起" : "展开"
      }}</span>
    </button>

    <div v-if="open" class="recon-draft-summary__body">
      <RecognizerCandidatesPanel
        kind="holding"
        :candidates="candidates"
        :committing="committing"
        @discard="emit('discard')"
        @commit="emit('commit', $event)"
      />
      <RecognizerCandidatesPanel
        kind="txn"
        :candidates="candidates"
        :committing="committing"
        @discard="emit('discard')"
        @commit="emit('commit', $event)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { RecognizerCandidate } from "@/composables/useReconDraft";
import RecognizerCandidatesPanel from "./RecognizerCandidatesPanel.vue";

defineOptions({ name: "ReconDraftSummary" });

const props = defineProps<{
  candidates: RecognizerCandidate[];
  committing: boolean;
}>();

const emit = defineEmits<{
  discard: [];
  commit: [kind: "txn" | "holding"];
}>();

const open = ref(false);

const total = computed(() => props.candidates.length);
</script>

<style scoped>
.recon-draft-summary {
  margin-bottom: var(--space-standard);
  background: color-mix(in srgb, var(--brand-100) 35%, var(--bg-card));
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.recon-draft-summary__toggle {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 10px 16px;
  font-family: var(--font-ui);
  cursor: pointer;
  background: transparent;
  border: none;
}

.recon-draft-summary__label {
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.recon-draft-summary__hint {
  font-size: var(--text-label);
  color: var(--brand-ink);
}

.recon-draft-summary__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0 16px 16px;
}
</style>
