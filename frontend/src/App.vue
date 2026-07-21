<template>
  <el-config-provider :locale="currentLocale">
    <router-view />
    <ReDialog />
  </el-config-provider>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed } from "vue";
import { ElConfigProvider } from "element-plus";
import { ReDialog } from "@/components/ReDialog";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { useSupabaseAuth } from "@/composables/useSupabaseAuth";

export default defineComponent({
  name: "app",
  components: {
    [ElConfigProvider.name]: ElConfigProvider,
    ReDialog
  },
  setup() {
    const { initAuthListener } = useSupabaseAuth();

    onMounted(() => {
      initAuthListener();
    });

    const currentLocale = computed(() => zhCn);

    return {
      currentLocale
    };
  }
});
</script>
