<!--
  数据连接页（MCP 连接管理）：两种连接方式共用一个入口。

  路由 `/settings/mcp-connections` 是 OAuth 回调成功后的固定回跳地址（后端
  `_success_redirect` 默认值），所以这个路径不能改；页面从 query 读一次性成功提示。

  与 /profile 同族：hidden 路由不进侧边栏，从导航栏头像菜单进入；页签由组件自登记。
-->
<template>
  <div class="mcp-page">
    <PageHeaderBar
      title="数据连接"
      subtitle="连接第三方投资服务后，账本精灵就能直接查询这些账户的数据。"
    />

    <div class="mcp-shell">
      <el-alert
        v-if="notice"
        class="mcp-notice"
        :type="notice.type"
        :title="notice.text"
        show-icon
        closable
        @close="clearNotice"
      />

      <section class="mcp-section">
        <SectionHeader
          title="可连接的服务"
          info="只展示系统已登记的服务。为保证账户安全，这里不接受自行填写服务地址。"
        />
        <div v-loading="loading" class="mcp-grid">
          <ServiceCard
            v-for="item in services"
            :key="item.provider"
            :service="item"
            :connection="item.connection"
            :pending="pending.includes(item.provider)"
            @connect-oauth="connectOAuth"
            @connect-static="onConnectStatic"
            @disconnect="disconnect"
          />
        </div>
      </section>

      <p class="mcp-footnote">
        凭据按用户隔离、加密保存；可以在任何时候断开。断开不会删除你在第三方服务里的账户。
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onActivated, onMounted } from "vue";
import { useRoute } from "vue-router";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import ServiceCard from "./components/ServiceCard.vue";
import { useMcpConnections } from "./useMcpConnections";

defineOptions({ name: "McpConnections" });

// hidden 路由不进侧边栏，页签只能靠组件自登记（同 /profile 的处理）
const route = useRoute();
const registerTag = () => {
  useMultiTagsStoreHook().handleTags("push", {
    path: route.path,
    name: route.name as string,
    meta: {
      title: route.meta.title || "数据连接",
      ...(route.meta as Record<string, unknown>)
    }
  });
};

const {
  services,
  loading,
  pending,
  notice,
  load,
  consumeRedirectNotice,
  connectOAuth,
  connectStatic,
  disconnect,
  clearNotice
} = useMcpConnections();

function onConnectStatic(payload: { provider: string; apiKey: string }): void {
  void connectStatic(payload.provider, payload.apiKey);
}

onMounted(() => {
  registerTag();
  consumeRedirectNotice();
  void load();
});
onActivated(registerTag);
</script>

<style scoped>
.mcp-page {
  min-height: 100%;
  padding: var(--space-5);
  background-color: var(--bg-page);
}

.mcp-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-width: 900px;
  margin: var(--space-5) auto 0;
}

.mcp-notice {
  border-radius: 12px;
}

.mcp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--space-4);
}

.mcp-footnote {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
