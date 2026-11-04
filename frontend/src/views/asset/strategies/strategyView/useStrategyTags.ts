import { ref } from "vue";
import { ElMessage } from "element-plus";
import {
  bindPositionTag,
  createStrategyTag,
  deleteStrategyTag,
  unbindPositionTag,
  type StrategyTag
} from "@/api/strategy";
import {
  diffTags,
  withTag,
  withoutTag,
  withoutTagEverywhere
} from "./strategyViewModel";

/**
 * 策略标签的状态与增删改（#980 拆分自 views/asset/strategies/index.vue）。
 *
 * 所有操作都是「先落库、再更新本地映射」，且**逐项收集失败**而不是空 catch
 * （#1833）：过去绑定失败也被吞掉，最后无条件弹「标签已更新」——用户看到成功、
 * 刷新后标签消失。乐观更新 + 静默失败比直接报错更伤信任。
 *
 * 映射更新一律走 model 里的纯函数（返回新对象），不就地 `splice`：就地改会让
 * 依赖该映射引用的 computed 拿不到变更，也让单元测试无法断言「改了什么」。
 */
export function useStrategyTags() {
  const allTags = ref<StrategyTag[]>([]);
  /** 持仓 id → 标签名数组 */
  const positionTagMap = ref<Record<number, string[]>>({});

  /** 概览接口返回后初始化（tags 与 relations 一起进来） */
  function setOverview(
    tags: StrategyTag[],
    relations: Record<number, string[]>
  ) {
    allTags.value = tags;
    positionTagMap.value = relations;
  }

  /** 摘掉某持仓上的一个标签 */
  async function unbindTag(positionId: number, tagName: string) {
    const tag = allTags.value.find(t => t.name === tagName);
    if (!tag) return;
    try {
      await unbindPositionTag(tag.id, positionId);
      positionTagMap.value = withoutTag(
        positionTagMap.value,
        positionId,
        tagName
      );
      ElMessage.success("已移除标签");
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "操作失败");
    }
  }

  /** 把某持仓的标签改成勾选后的全集（双向 diff：补绑定 + 解绑） */
  async function updateTags(positionId: number, selected: string[]) {
    const current = positionTagMap.value[positionId] || [];
    const { toAdd, toRemove } = diffTags(current, selected);

    const failed: string[] = [];

    for (const tagName of toAdd) {
      const tag = allTags.value.find(t => t.name === tagName);
      if (tag) {
        try {
          await bindPositionTag(tag.id, positionId);
        } catch {
          failed.push(tagName);
        }
      }
    }
    for (const tagName of toRemove) {
      const tag = allTags.value.find(t => t.name === tagName);
      if (tag) {
        try {
          await unbindPositionTag(tag.id, positionId);
        } catch {
          failed.push(tagName);
        }
      }
    }

    // 本地映射只提交真正生效的部分，别把失败的写进去
    positionTagMap.value = {
      ...positionTagMap.value,
      [positionId]: selected.filter(t => !failed.includes(t))
    };
    if (failed.length) {
      ElMessage.warning(`部分标签未生效：${failed.join("、")}`);
    } else {
      ElMessage.success("标签已更新");
    }
  }

  /**
   * 为某持仓新建并绑定标签。
   *
   * @returns 是否成功——调用方（单元格组件）据此决定要不要清空输入框：
   *          失败时保留用户输入，别让他重打一遍。
   */
  async function createTagForRow(
    positionId: number,
    rawName: string
  ): Promise<boolean> {
    const name = rawName.trim();
    if (!name) return false;
    try {
      const res: any = await createStrategyTag({ name });
      const newTag: StrategyTag = res?.data;
      if (!newTag?.id) throw new Error("创建标签失败");

      allTags.value.push(newTag);
      await bindPositionTag(newTag.id, positionId);
      positionTagMap.value = withTag(positionTagMap.value, positionId, name);
      ElMessage.success("标签已添加并绑定");
      return true;
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "创建失败");
      return false;
    }
  }

  /** 新建全局标签（不绑定任何持仓） */
  async function createGlobalTag(rawName: string): Promise<boolean> {
    const name = rawName.trim();
    if (!name) return false;
    try {
      const res: any = await createStrategyTag({ name });
      const newTag: StrategyTag = res?.data;
      if (!newTag?.id) throw new Error("创建失败");

      allTags.value.push(newTag);
      ElMessage.success("标签已创建");
      return true;
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "创建失败");
      return false;
    }
  }

  /** 删除全局标签，并把它的名字从所有持仓上摘掉 */
  async function deleteGlobalTag(id: number) {
    try {
      await deleteStrategyTag(id);
      const deletedTag = allTags.value.find(t => t.id === id);
      allTags.value = allTags.value.filter(t => t.id !== id);

      if (deletedTag) {
        positionTagMap.value = withoutTagEverywhere(
          positionTagMap.value,
          deletedTag.name
        );
      }
      ElMessage.success("标签已删除");
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "删除失败");
    }
  }

  return {
    allTags,
    positionTagMap,
    setOverview,
    unbindTag,
    updateTags,
    createTagForRow,
    createGlobalTag,
    deleteGlobalTag
  };
}
