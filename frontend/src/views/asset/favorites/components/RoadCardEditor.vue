<!--
  RoadCardEditor · 未竟之蹊单卡「编辑态」

  只做三件可写的事：标签增删、投资笔记、下次复盘日期。
  名称不可改（display_name 来自标的库），避免给用户假的可编辑暗示。
-->
<template>
  <div class="road-form" @click.stop>
    <p class="road-form__name">{{ item.display_name }}</p>
    <p class="road-form__hint">名称来自标的库，暂不支持改名</p>

    <div class="road-form__field">
      <span class="road-form__label">标签</span>
      <RoadTagChips :tags="draftTags" removable @remove="removeDraftTag" />
      <el-select
        v-model="pendingTagIds"
        multiple
        filterable
        size="small"
        placeholder="添加标签"
        class="road-form__select"
      >
        <el-option
          v-for="tag in addableTags"
          :key="tag.id"
          :label="tag.name"
          :value="tag.id"
        />
      </el-select>
    </div>

    <div class="road-form__field">
      <span class="road-form__label">投资笔记</span>
      <el-input
        v-model="draftNotes"
        type="textarea"
        :rows="4"
        maxlength="2000"
        show-word-limit
        resize="none"
        placeholder="写下你为什么在意它，以及下一次想验证什么。"
      />
    </div>

    <div class="road-form__field">
      <span class="road-form__label">下次复盘日期</span>
      <el-date-picker
        v-model="draftReviewDate"
        type="date"
        size="small"
        value-format="YYYY-MM-DD"
        placeholder="选个日子，慢下来看看"
        class="road-form__date"
      />
    </div>

    <div class="road-form__actions">
      <el-button size="small" @click="$emit('cancel')">取消</el-button>
      <el-button size="small" type="primary" :loading="saving" @click="onSave"
        >保存</el-button
      >
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type { WatchlistTag } from "@/api/watchlist";
import type { RoadItem } from "@/types/favorites";
import { findTagColor, findTagName } from "@/utils/tagHelpers";
import RoadTagChips from "./RoadTagChips.vue";

const props = defineProps<{ item: RoadItem; tags: WatchlistTag[] }>();

const emit = defineEmits<{
  (e: "cancel"): void;
  (
    e: "save",
    draft: { notes: string; next_review_date: string | null; tagIds: number[] }
  ): void;
}>();

const draftNotes = ref("");
const draftReviewDate = ref<string | null>(null);
const draftTagIds = ref<number[]>([]);
const pendingTagIds = ref<number[]>([]);
const saving = ref(false);

/**
 * 切换编辑对象时用当前卡片值重置草稿，避免残留上一张卡的内容。
 * 监听 item 引用而非 id：示例卡 id 恒为 null，按 id 监听会漏重置。
 */
watch(
  () => props.item,
  () => {
    draftNotes.value = props.item.notes ?? "";
    draftReviewDate.value = props.item.next_review_date ?? null;
    draftTagIds.value = [...props.item.tag_ids];
    pendingTagIds.value = [];
  },
  { immediate: true }
);

// 下拉选中后立刻沉淀为 chips（可删），下拉本身保持空态以便继续添加
watch(pendingTagIds, ids => {
  for (const id of ids) {
    if (!draftTagIds.value.includes(id)) draftTagIds.value.push(id);
  }
  pendingTagIds.value = [];
});

const draftTags = computed<WatchlistTag[]>(() =>
  draftTagIds.value.map(id => ({
    id,
    name: findTagName(props.tags, id),
    color: findTagColor(props.tags, id)
  }))
);

const addableTags = computed(() =>
  props.tags.filter(t => !draftTagIds.value.includes(t.id))
);

function removeDraftTag(tagId: number) {
  draftTagIds.value = draftTagIds.value.filter(id => id !== tagId);
}

function onSave() {
  if (props.item.isDemo) {
    ElMessage.info("示例卡片不支持保存，关闭「设计预览」即可回到真实数据");
    return;
  }
  saving.value = true;
  try {
    emit("save", {
      notes: draftNotes.value,
      next_review_date: draftReviewDate.value,
      tagIds: [...draftTagIds.value]
    });
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.road-form {
  margin-top: 10px;
}

.road-form__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.road-form__hint {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.road-form__field {
  margin-top: 12px;
}

.road-form__label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.road-form__select,
.road-form__date {
  width: 100%;
}

.road-form__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
