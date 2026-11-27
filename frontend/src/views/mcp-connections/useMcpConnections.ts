import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  beginMcpOAuth,
  connectMcpStaticToken,
  disconnectMcp,
  listMcpConnections,
  type McpConnection
} from "@/api/mcp";
import { MCP_SERVICES } from "./mcpServices";

export type McpNotice = { type: "success" | "error"; text: string };

/**
 * 连接管理页的状态层。
 *
 * 两条连接方式的唯一分叉只在「怎么拿到凭据」：OAuth 整页跳授权站、回调由后端接；
 * API Key 在本站填、后端加密入库。拿到之后共用同一张凭据表，所以本层不区分后续
 * 的列表 / 断开逻辑。
 *
 * 错误文案固定为人话：上游响应体可能含 token，绝不把 err.message 直接显示出来。
 */
export function useMcpConnections() {
  const route = useRoute();
  const router = useRouter();

  const connections = ref<McpConnection[]>([]);
  const loading = ref(false);
  const pending = ref<string[]>([]);
  const notice = ref<McpNotice | null>(null);

  const byProvider = computed(
    () => new Map(connections.value.map(item => [item.provider, item]))
  );

  /** 服务清单（UI 侧登记）+ 该用户的实时连接状态 */
  const services = computed(() =>
    MCP_SERVICES.map(service => ({
      ...service,
      connection: byProvider.value.get(service.provider) ?? null
    }))
  );

  function fail(text: string): void {
    notice.value = { type: "error", text };
  }

  async function load(): Promise<void> {
    loading.value = true;
    try {
      const response = await listMcpConnections();
      connections.value = response.data ?? [];
    } catch {
      fail("连接列表加载失败，请稍后重试");
    } finally {
      loading.value = false;
    }
  }

  /** OAuth 回调回跳后的一次性成功提示；读完即清 query，刷新不再重复弹 */
  function consumeRedirectNotice(): void {
    if (route.query.mcp_connected !== "1") return;
    const provider = String(route.query.provider ?? "");
    const name =
      MCP_SERVICES.find(service => service.provider === provider)?.name ??
      "该服务";
    notice.value = { type: "success", text: `${name}已授权连接` };

    const rest = { ...route.query };
    delete rest.mcp_connected;
    delete rest.provider;
    void router.replace({ path: route.path, query: rest });
  }

  function track(provider: string, on: boolean): void {
    pending.value = on
      ? [...pending.value, provider]
      : pending.value.filter(item => item !== provider);
  }

  /** 浏览器授权：整页跳到后端返回的授权 URL，回调后由后端跳回本页 */
  async function connectOAuth(provider: string): Promise<void> {
    track(provider, true);
    try {
      const response = await beginMcpOAuth(provider);
      const url = response.data?.authorization_url;
      if (!url) {
        fail("授权地址获取失败，请稍后重试");
        return;
      }
      window.location.assign(url);
    } catch {
      fail("发起授权失败，请稍后重试");
    } finally {
      track(provider, false);
    }
  }

  /** 静态 API Key：前端只负责递交给后端，不留存、不回显 */
  async function connectStatic(
    provider: string,
    apiKey: string
  ): Promise<void> {
    track(provider, true);
    try {
      await connectMcpStaticToken({ provider, api_key: apiKey });
      notice.value = { type: "success", text: "API Key 已保存" };
      await load();
    } catch {
      fail("保存失败，请检查 API Key 后重试");
    } finally {
      track(provider, false);
    }
  }

  async function disconnect(provider: string): Promise<void> {
    track(provider, true);
    try {
      await disconnectMcp(provider);
      notice.value = { type: "success", text: "已断开连接" };
      await load();
    } catch {
      fail("断开失败，请稍后重试");
    } finally {
      track(provider, false);
    }
  }

  return {
    services,
    loading,
    pending,
    notice,
    load,
    consumeRedirectNotice,
    connectOAuth,
    connectStatic,
    disconnect,
    clearNotice: () => {
      notice.value = null;
    }
  };
}
