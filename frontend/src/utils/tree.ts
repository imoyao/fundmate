/**
 * 菜单 / 路由树的通用工具（#2879 类型化）。
 *
 * 这些函数处理的节点既有 vue-router 的 RouteRecordRaw，也有后端返回的普通对象；
 * 统一用泛型保持「进什么类型、出什么类型」，只在读写层级字段的那一处把节点
 * 断言成 HierarchyNode（字段全部可选）。动态键名来自调用参数，也只在辅助函数里
 * 做一次边界断言 —— 不再用 any 放开整个数据形状。
 */

/** 层级构造会写入的节点字段（全部可选：调用前的原始节点尚未补齐）。 */
interface HierarchyNode {
  id?: number;
  parentId?: number | string | null;
  pathList?: Array<number | string>;
  uniqueId?: number | string;
  children?: HierarchyNode[];
}

type Indexable = Record<string, unknown>;
const readKey = (o: object, key: string): unknown => (o as Indexable)[key];
const writeKey = (o: object, key: string, value: unknown): void => {
  (o as Indexable)[key] = value;
};
const asNode = (o: object): HierarchyNode => o as HierarchyNode;

/**
 * @description 提取菜单树中的每一项uniqueId
 * @param tree 树
 * @returns 每一项uniqueId组成的数组
 */
export const extractPathList = (
  tree: object[]
): Array<number | string | undefined> => {
  if (!Array.isArray(tree)) {
    console.warn("tree must be an array");
    return [];
  }
  if (!tree || tree.length === 0) return [];
  const expandedPaths: Array<number | string | undefined> = [];
  for (const raw of tree) {
    const node = asNode(raw);
    const hasChildren = node.children && node.children.length > 0;
    if (hasChildren) extractPathList(node.children);
    expandedPaths.push(node.uniqueId);
  }
  return expandedPaths;
};

/**
 * @description 如果父级下children的length为1，删除children并自动组建唯一uniqueId
 * @param tree 树
 * @param pathList 每一项的id组成的数组
 * @returns 组件唯一uniqueId后的树
 */
export const deleteChildren = <T extends object>(
  tree: T[],
  pathList: Array<number | string> = []
): T[] => {
  if (!Array.isArray(tree)) {
    console.warn("menuTree must be an array");
    return [];
  }
  if (!tree || tree.length === 0) return [];
  for (const [key, raw] of tree.entries()) {
    const node = asNode(raw);
    if (node.children && node.children.length === 1) delete node.children;
    node.id = key;
    node.parentId = pathList.length ? pathList[pathList.length - 1] : null;
    node.pathList = [...pathList, node.id];
    node.uniqueId =
      node.pathList.length > 1 ? node.pathList.join("-") : node.pathList[0];
    const hasChildren = node.children && node.children.length > 0;
    if (hasChildren) deleteChildren(node.children, node.pathList);
  }
  return tree;
};

/**
 * @description 创建层级关系
 * @param tree 树
 * @param pathList 每一项的id组成的数组
 * @returns 创建层级关系后的树
 */
export const buildHierarchyTree = <T extends object>(
  tree: T[],
  pathList: Array<number | string> = []
): T[] => {
  if (!Array.isArray(tree)) {
    console.warn("tree must be an array");
    return [];
  }
  if (!tree || tree.length === 0) return [];
  for (const [key, raw] of tree.entries()) {
    const node = asNode(raw);
    node.id = key;
    node.parentId = pathList.length ? pathList[pathList.length - 1] : null;
    node.pathList = [...pathList, node.id];
    const hasChildren = node.children && node.children.length > 0;
    if (hasChildren) buildHierarchyTree(node.children, node.pathList);
  }
  return tree;
};

/**
 * @description 广度优先遍历，根据唯一uniqueId找当前节点信息
 * @param tree 树
 * @param uniqueId 唯一uniqueId
 * @returns 当前节点信息
 */
export const getNodeByUniqueId = (
  tree: HierarchyNode[],
  uniqueId: number | string
): HierarchyNode | HierarchyNode[] => {
  if (!Array.isArray(tree)) {
    console.warn("menuTree must be an array");
    return [];
  }
  if (!tree || tree.length === 0) return [];
  const item = tree.find(node => node.uniqueId === uniqueId);
  if (item) return item;
  const childrenList = tree
    .filter(node => node.children)
    .map(i => i.children)
    .flat(1) as HierarchyNode[];
  return getNodeByUniqueId(childrenList, uniqueId);
};

/**
 * @description 向当前唯一uniqueId节点中追加字段
 * @param tree 树
 * @param uniqueId 唯一uniqueId
 * @param fields 需要追加的字段
 * @returns 追加字段后的树
 */
export const appendFieldByUniqueId = (
  tree: HierarchyNode[],
  uniqueId: number | string,
  fields: object
): HierarchyNode[] => {
  if (!Array.isArray(tree)) {
    console.warn("menuTree must be an array");
    return [];
  }
  if (!tree || tree.length === 0) return [];
  for (const raw of tree) {
    const node = asNode(raw);
    const hasChildren = node.children && node.children.length > 0;
    if (
      node.uniqueId === uniqueId &&
      Object.prototype.toString.call(fields) === "[object Object]"
    )
      Object.assign(node, fields);
    if (hasChildren) {
      appendFieldByUniqueId(node.children, uniqueId, fields);
    }
  }
  return tree;
};

/**
 * @description 构造树型结构数据
 * @param data 数据源
 * @param id id字段 默认id
 * @param parentId 父节点字段，默认parentId
 * @param children 子节点字段，默认children
 * @returns 追加字段后的树
 */
export const handleTree = <T extends object>(
  data: T[],
  id?: string,
  parentId?: string,
  children?: string
): T[] => {
  if (!Array.isArray(data)) {
    console.warn("data must be an array");
    return [];
  }
  const config = {
    id: id || "id",
    parentId: parentId || "parentId",
    childrenList: children || "children"
  };

  const childrenListMap: Record<string, T[]> = {};
  const nodeIds: Record<string, T> = {};
  const tree: T[] = [];

  for (const d of data) {
    const parentKey = String(readKey(d, config.parentId));
    if (childrenListMap[parentKey] == null) {
      childrenListMap[parentKey] = [];
    }
    nodeIds[String(readKey(d, config.id))] = d;
    childrenListMap[parentKey].push(d);
  }

  for (const d of data) {
    const parentKey = String(readKey(d, config.parentId));
    if (nodeIds[parentKey] == null) {
      tree.push(d);
    }
  }

  for (const t of tree) {
    adaptToChildrenList(t);
  }

  function adaptToChildrenList(o: T) {
    const key = String(readKey(o, config.id));
    if (childrenListMap[key] !== null) {
      writeKey(o, config.childrenList, childrenListMap[key]);
    }
    const childList = readKey(o, config.childrenList);
    if (childList) {
      for (const c of childList as T[]) {
        adaptToChildrenList(c);
      }
    }
  }
  return tree;
};
