// src/composables/echarts/useEchartsLifecycle.ts
import { onMounted, onBeforeUnmount, onActivated, type Ref } from "vue";
import echarts from "@/plugins/echarts";

/** ECharts 实例类型（取 echarts.init 的返回类型，避免版本差异导致的类型名不匹配） */
export type EChartsInstance = ReturnType<typeof echarts.init>;

/** 单个图表的规格：模板 ref + 构建函数 */
export interface ChartSpec {
  /** 图表容器的模板 ref */
  ref: Ref<HTMLElement | null>;
  /**
   * 构建函数：接收容器 DOM，返回 ECharts 实例（内部应调用 echarts.init + setOption）。
   * 例：(el) => { const c = echarts.init(el); c.setOption(option); return c; }
   */
  build: (el: HTMLElement) => EChartsInstance;
}

export interface EchartLifecycleOptions {
  /** 是否为 keepAlive 页。true 时会在 onActivated 触发 resize，解决缓存页图表空白/尺寸错乱。默认 false。 */
  keepAlive?: boolean;
  /**
   * 挂载后是否自动渲染。默认 true。
   * 异步数据页（初始无数据）设 false，等数据就绪后手动调用返回的 render()。
   */
  autoRenderOnMount?: boolean;
}

/**
 * 统一的 ECharts 生命周期管理，取代各页面手写的 echarts.init / getCSSColor /
 * window resize 监听 / onBeforeUnmount dispose，集中收口避免内存泄漏与
 * keepAlive 缓存页图表空白。
 *
 * 职责：
 * - 自动 render（支持挂载时自动或手动触发）
 * - window resize 自动 resize
 * - 卸载时 dispose，杜绝内存泄漏
 * - keepAlive 页在 onActivated 自动 resize，修复缓存回来图表空白/尺寸错乱
 *
 * @example
 * const pieRef = ref<HTMLElement | null>(null);
 * const { render } = useEchartsLifecycle([{
 *   ref: pieRef,
 *   build: (el) => {
 *     const c = echarts.init(el);
 *     c.setOption({ ... });
 *     return c;
 *   }
 * }], { keepAlive: true, autoRenderOnMount: false });
 * // 异步数据就绪后：render();
 */
export function useEchartsLifecycle(
  specs: ChartSpec[],
  options: EchartLifecycleOptions = {}
) {
  const charts: EChartsInstance[] = [];

  const render = () => {
    // 先释放旧实例，避免同一 DOM 上重复 init 触发 ECharts 警告
    charts.forEach((c) => c?.dispose());
    charts.length = 0;
    specs.forEach((spec, i) => {
      const el = spec.ref.value;
      if (!el) return;
      charts[i] = spec.build(el);
    });
  };

  const resize = () => {
    charts.forEach((c) => c?.resize());
  };

  const handleResize = () => resize();

  onMounted(() => {
    if (options.autoRenderOnMount !== false) render();
    window.addEventListener("resize", handleResize);
  });

  if (options.keepAlive) {
    onActivated(() => resize());
  }

  onBeforeUnmount(() => {
    window.removeEventListener("resize", handleResize);
    charts.forEach((c) => c?.dispose());
    charts.length = 0;
  });

  return { render, resize, charts };
}
