<!-- 导航模式：左侧 / 顶部 / 混合 -->
<script setup lang="ts">
import { NAV_MODE_OPTIONS, SECTION_TITLE_CLASS } from "./settingModel";

const props = defineProps<{
  /** 当前导航模式（vertical / horizontal / mix） */
  layout: string;
  /** mobile 时不提供顶部与混合两种形态 */
  device: string;
}>();

const emit = defineEmits<{ select: [layout: string] }>();
</script>

<template>
  <div>
    <p :class="['mt-5!', ...SECTION_TITLE_CLASS]">导航模式</p>
    <ul class="pure-theme">
      <!-- 用 v-if 而不是 v-show：移动端下这两个 `<li>` 本来就不该进 DOM，
           （`v-show` 会留下 `display:none` 的隐藏节点，被读屏与 e2e 计数误当成可见项） -->
      <template v-for="mode in NAV_MODE_OPTIONS" :key="mode.layout">
        <li
          v-if="!(mode.mobileHidden && props.device === 'mobile')"
          v-tippy="{ content: mode.tip, zIndex: 41000 }"
          :class="props.layout === mode.layout ? 'is-select' : ''"
          role="button"
          tabindex="0"
          :aria-label="mode.ariaLabel"
          @keydown.enter="emit('select', mode.layout)"
          @click="emit('select', mode.layout)"
        >
          <div />
          <div />
        </li>
      </template>
    </ul>
  </div>
</template>

<style lang="scss" scoped>
/* scoped 说明：三个 `li` 是本组件内部元素，`.pure-theme` / `.is-select` 必须自带一份。
   选中态由 `:class` 绑定表达——原来父层还有一段 `watch($storage)` + `toggleClass`
   的命令式 DOM 操作，作用在同一批元素、同一个类名、同一个条件上，是同义重复
   （详见 PR 风险节）；拆到子组件后父层拿不到这些 `li` 的 ref，故删去。 */
.pure-theme {
  display: flex;
  gap: 12px;

  li {
    position: relative;
    width: 46px;
    height: 36px;
    overflow: hidden;
    cursor: pointer;
    background: #f0f2f5;
    border-radius: 4px;
    box-shadow: 0 1px 2.5px 0 rgb(0 0 0 / 18%);

    &:nth-child(1) {
      div {
        &:nth-child(1) {
          width: 30%;
          height: 100%;
          background: #1b2a47;
        }

        &:nth-child(2) {
          position: absolute;
          top: 0;
          right: 0;
          width: 70%;
          height: 30%;
          background: var(--bg-card);
          box-shadow: 0 0 1px #888;
        }
      }
    }

    &:nth-child(2) {
      div {
        &:nth-child(1) {
          width: 100%;
          height: 30%;
          background: #1b2a47;
          box-shadow: 0 0 1px #888;
        }
      }
    }

    &:nth-child(3) {
      div {
        &:nth-child(1) {
          width: 100%;
          height: 30%;
          background: #1b2a47;
          box-shadow: 0 0 1px #888;
        }

        &:nth-child(2) {
          position: absolute;
          bottom: 0;
          left: 0;
          width: 30%;
          height: 70%;
          background: var(--bg-card);
          box-shadow: 0 0 1px #888;
        }
      }
    }
  }
}

.is-select {
  border: 2px solid var(--el-color-primary);
}
</style>
