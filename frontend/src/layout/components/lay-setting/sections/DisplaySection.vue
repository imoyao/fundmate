<!-- 界面显示：六个开关（灰色 / 色弱 / 隐藏标签页 / 隐藏页脚 / Logo / 页签持久化） -->
<script setup lang="ts">
import { SECTION_TITLE_CLASS } from "./settingModel";

/**
 * 六个开关用 `defineModel` 双向绑定：父层持有状态，这里只负责「点了什么」。
 * `*-change` 事件在开关值已回写父层之后才发（el-switch 先 `update:modelValue`
 * 再 `change`），所以父层的 `xxxChange()` 仍能从 state 里读到新值。
 */
const grey = defineModel<boolean>("grey", { required: true });
const weak = defineModel<boolean>("weak", { required: true });
const hideTabs = defineModel<boolean>("hideTabs", { required: true });
const hideFooter = defineModel<boolean>("hideFooter", { required: true });
const logo = defineModel<boolean>("logo", { required: true });
const multiTagsCache = defineModel<boolean>("multiTagsCache", {
  required: true
});

const emit = defineEmits<{
  "grey-change": [];
  "weak-change": [];
  "tabs-change": [];
  "hide-footer-change": [];
  "logo-change": [];
  "multi-tags-cache-change": [];
}>();
</script>

<template>
  <div>
    <p :class="['mt-5!', ...SECTION_TITLE_CLASS]">界面显示</p>
    <ul class="setting">
      <li>
        <span class="text-[var(--text-primary)]">灰色模式</span>
        <el-switch
          v-model="grey"
          inline-prompt
          active-text="开"
          inactive-text="关"
          @change="emit('grey-change')"
        />
      </li>
      <li>
        <span class="text-[var(--text-primary)]">色弱模式</span>
        <el-switch
          v-model="weak"
          inline-prompt
          active-text="开"
          inactive-text="关"
          @change="emit('weak-change')"
        />
      </li>
      <li>
        <span class="text-[var(--text-primary)]">隐藏标签页</span>
        <el-switch
          v-model="hideTabs"
          inline-prompt
          active-text="开"
          inactive-text="关"
          @change="emit('tabs-change')"
        />
      </li>
      <li>
        <span class="text-[var(--text-primary)]">隐藏页脚</span>
        <el-switch
          v-model="hideFooter"
          inline-prompt
          active-text="开"
          inactive-text="关"
          @change="emit('hide-footer-change')"
        />
      </li>
      <li>
        <span class="text-[var(--text-primary)]">Logo</span>
        <el-switch
          v-model="logo"
          inline-prompt
          :active-value="true"
          :inactive-value="false"
          active-text="开"
          inactive-text="关"
          @change="emit('logo-change')"
        />
      </li>
      <li>
        <span class="text-[var(--text-primary)]">页签持久化</span>
        <el-switch
          v-model="multiTagsCache"
          inline-prompt
          active-text="开"
          inactive-text="关"
          @change="emit('multi-tags-cache-change')"
        />
      </li>
    </ul>
  </div>
</template>

<style lang="scss" scoped>
/* scoped 说明：`li` 是本组件内部元素，`.setting` 必须自带一份 */
.setting {
  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 3px 0;
    font-size: var(--text-small);
  }
}
</style>
