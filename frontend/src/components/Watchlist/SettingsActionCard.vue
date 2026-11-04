<script setup lang="ts">
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";

/**
 * 设置抽屉里的一张「入口卡」（#980 拆分自 `SettingsDrawer.vue`）。
 *
 * 原实现把同一段模板抄了 5 份（管理分组 / 管理标签 / 批量管理 / 导入探市数据 /
 * 表格列显示 / 排序设置），只差图标、文案与是否可点。抽成组件后：
 * 卡片外观（白底 + 1px 描边 + 抬升阴影）、`role="button"` + 键盘 Enter 语义、
 * 右侧箭头都只有一份，改一次全抽屉同步。
 *
 * 视觉严格沿用原类名组合（`settings-card rounded-xl p-4 …`），未新增任何类名与色值。
 */
defineOptions({ name: "SettingsActionCard" });

const props = withDefaults(
  defineProps<{
    icon: string;
    /** 图标色（走语义 token，如 --brand-700 / --color-warning-ink） */
    iconColor: string;
    title: string;
    description: string;
    /** 卡片描边色，默认 --border-light；「导入探市数据」用 --brand-400 强调待办 */
    borderColor?: string;
    /** 是否可点（false = 「即将推出」占位卡：半透明 + 禁用光标 + 无键盘语义） */
    clickable?: boolean;
    /** 标题右侧的「!」徽标（有待迁移数据时提示） */
    badge?: boolean;
    /** clickable=false 时右侧替代箭头的文案 */
    trailingText?: string;
  }>(),
  {
    borderColor: "var(--border-light)",
    clickable: true,
    badge: false,
    trailingText: ""
  }
);

const emit = defineEmits<{ activate: [] }>();

/** 可点 / 占位两种类名组合与原实现逐字一致（含 Tailwind 工具类） */
const cardClass = computed(() =>
  props.clickable
    ? [
        "settings-card",
        "rounded-xl",
        "p-4",
        "cursor-pointer",
        "transition-shadow"
      ]
    : ["settings-card", "rounded-xl", "p-4", "opacity-50", "cursor-not-allowed"]
);

const cardStyle = computed(() => ({
  backgroundColor: "var(--bg-card)",
  border: `1px solid ${props.borderColor}`,
  boxShadow: "var(--shadow-raised)"
}));

function activate(): void {
  if (props.clickable) emit("activate");
}
</script>

<template>
  <div
    :class="cardClass"
    :style="cardStyle"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    @keydown.enter="activate"
    @click="activate"
  >
    <div class="flex items-center gap-3">
      <div
        class="w-10 h-10 rounded-lg flex items-center justify-center"
        :style="{ backgroundColor: 'var(--bg-soft)' }"
      >
        <IconifyIconOffline
          :icon="icon"
          class="text-lg"
          :style="{ color: iconColor }"
        />
      </div>
      <div class="flex-1">
        <h4
          class="text-sm font-medium mb-1"
          :style="{
            color: clickable
              ? 'var(--text-primary)'
              : 'var(--text-tertiary-ink)'
          }"
        >
          {{ title }}
          <el-badge v-if="badge" :value="'!'" type="danger" class="ml-1" />
        </h4>
        <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
          {{ description }}
        </p>
      </div>
      <IconifyIconOffline
        v-if="clickable"
        icon="ep:arrow-right"
        class="text-sm"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      />
      <span
        v-else
        class="px-2 py-0.5 text-[10px] rounded-full"
        :style="{
          backgroundColor: 'var(--bg-soft)',
          color: 'var(--text-tertiary-ink)'
        }"
      >
        {{ trailingText }}
      </span>
    </div>
  </div>
</template>
