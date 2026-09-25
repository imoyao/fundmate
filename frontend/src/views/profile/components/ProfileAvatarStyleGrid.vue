<template>
  <!-- 第二排：下方头像网格 -->
  <div class="style-card-group" role="radiogroup" aria-label="头像画风">
    <button
      v-for="style in AVATAR_STYLES"
      :key="style"
      type="button"
      role="radio"
      :aria-checked="avatarStyle === style"
      class="style-card"
      :class="{
        'style-card--active': avatarStyle === style,
        'style-card--animated': ANIMATED_AVATAR_STYLES.has(style)
      }"
      :style="styleCardStyle(style)"
      @click="$emit('select', style)"
    >
      <span class="style-card__thumb">
        <img
          :src="
            buildAvatarUrl(style, avatarThumbSeed, {
              animated: false
            })
          "
          :alt="AVATAR_STYLE_LABEL[style]"
          class="style-card__img"
          loading="lazy"
        />
        <IconifyIconOffline
          v-if="avatarStyle === style"
          icon="lucide:check"
          class="style-card__check"
          aria-hidden="true"
        />
      </span>
      <span class="style-card__name">
        {{ AVATAR_STYLE_LABEL[style] }}
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
import {
  AVATAR_STYLES,
  AVATAR_STYLE_LABEL,
  ANIMATED_AVATAR_STYLES,
  type AvatarStyle,
  buildAvatarUrl
} from "@/utils/avatar";

defineOptions({ name: "ProfileAvatarStyleGrid" });

defineProps<{
  avatarStyle: AvatarStyle;
  avatarThumbSeed: string;
  styleCardStyle: (style: AvatarStyle) => Record<string, string>;
}>();

defineEmits<{ select: [style: AvatarStyle] }>();
</script>

<style scoped>
/* ===== 果冻回弹关键帧 ===== */
@keyframes style-pop {
  0% {
    transform: var(--tilt, none) scale(1);
  }

  30% {
    transform: var(--tilt, none) scale(0.92);
  }

  60% {
    transform: var(--tilt, none) scale(1.05);
  }

  80% {
    transform: var(--tilt, none) scale(0.97);
  }

  100% {
    transform: var(--tilt, none) scale(1);
  }
}

@keyframes card-dot-breathe {
  0%,
  100% {
    opacity: 0.35;
  }

  50% {
    opacity: 1;
  }
}

/* ===== 第二排：头像卡片网格 ===== */

/* 头像卡片网格：7 列，缩略图约 68px，与 100px 预览呈黄金比例 ~0.68 */
.style-card-group {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: var(--space-3);
  width: 100%;
}

.style-card {
  display: inline-flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  padding: 6px 6px 4px;
  color: var(--text-tertiary-ink);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  transform: var(--tilt, none);
  transition:
    transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1),
    border-color 0.2s,
    color 0.2s,
    box-shadow 0.2s;
  will-change: transform;
}

.style-card:hover {
  color: var(--text-primary);
  border-color: var(--brand-400);
  box-shadow: var(--shadow-raised);
  transform: var(--tilt, none) translateY(-2px) scale(1.04);
}

.style-card:active {
  transform: var(--tilt, none) scale(0.94);
}

.style-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.style-card--active {
  color: var(--brand-ink);
  border-color: var(--brand-400);
  box-shadow: 0 1px 3px rgb(0 0 0 / 6%);
  animation: style-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.style-card--active:hover {
  color: var(--brand-ink);
}

.style-card--animated .style-card__name::after {
  display: inline-block;
  margin-left: 3px;
  font-size: 8px;
  vertical-align: super;
  color: var(--brand-ink);
  content: "●";
  animation: card-dot-breathe 2.4s ease-in-out infinite;
}

.style-card__thumb {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  background-color: var(--bg-soft);
  border-radius: var(--radius-sm);
}

.style-card__img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.style-card__check {
  position: absolute;
  right: 2px;
  bottom: 2px;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  font-size: 10px;
  color: var(--text-inverse);
  background: var(--brand-500);
  border-radius: 50%;
}

.style-card__name {
  font-size: var(--text-small);
  line-height: 1.2;
}

/* ===== 响应式 ===== */

/* 窄屏（<640px）：设置页的行式布局改竖排。
   ⚠️ 本块原先排在各自的基础声明**之前**——媒体查询不改变特异性，覆盖被后面同选择器的声明压掉、**从未生效**（2026-09-18 修复，见 #1576 同类台账）。 */
@media (width <= 640px) {
  /* breakpoint-allow: 本文件 style 块是纯 CSS（无 lang="scss"），无法用 bp mixin */
  .style-card-group {
    justify-content: flex-start;
  }
}
</style>
