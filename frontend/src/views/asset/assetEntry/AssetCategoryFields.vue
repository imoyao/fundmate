<script setup lang="ts">
/**
 * 资产大类 + 两个子类选择器（#980 拆分）。
 *
 * 这三个下拉是**联动**的：大类决定「哪个子类选择器可见」以及「已有的细分是否还适用」。
 * 把它们收在一起，是因为这份联动关系散到页面里就没人看得见——切大类时忘清细分，
 * 结果是把投资细分写到别的大类、或把固定资产子类写到投资理财。
 *
 * 两个值用 `defineModel` 双向绑回页面：页面持有整个 form，这里只改这两个字段，
 * 不接触 form 本体（也就不存在「子组件改 prop」的问题）。
 */
import { watch } from "vue";
import {
  INVESTMENT_MINOR_CATEGORIES,
  MAJOR_CATEGORY_OPTIONS
} from "@/constants";

import {
  FIXED_SUBTYPE_OPTIONS,
  minorCategoryAppliesTo
} from "./assetEntryModel";

const majorCategory = defineModel<string>("majorCategory", { required: true });
const minorCategory = defineModel<string | null>("minorCategory", {
  required: true
});

/**
 * 大类切换时清掉不适用的细分。
 * 判据是「新大类 + 旧细分」的组合，不是单独看任一边——同一个值在 investment 下
 * 合法、在 fixed 下就是脏数据。
 */
watch(majorCategory, next => {
  if (!minorCategoryAppliesTo(next, minorCategory.value)) {
    minorCategory.value = null;
  }
});
</script>

<template>
  <el-form-item label="资产大类" prop="major_category">
    <el-select v-model="majorCategory" class="w-full">
      <el-option
        v-for="opt in MAJOR_CATEGORY_OPTIONS"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
    </el-select>
  </el-form-item>

  <!-- 固定资产子类（#1798）：写入 minor_category。
       此前盘点页快捷录入的 ?type=house/car/gold 在此被静默丢弃，
       导致房产 / 汽车 / 黄金在数据上无法区分（详情页无法按子类过滤） -->
  <el-form-item v-if="majorCategory === 'fixed'" label="资产子类">
    <el-select
      v-model="minorCategory"
      class="w-full"
      clearable
      placeholder="可不选，如房产、汽车、黄金"
      @clear="minorCategory = null"
    >
      <el-option
        v-for="opt in FIXED_SUBTYPE_OPTIONS"
        :key="opt.key"
        :label="opt.label"
        :value="opt.key"
      />
    </el-select>
  </el-form-item>

  <!-- #1354：银行理财/投顾/信托/私募/理财型保险 不再是平级大类，
       作为「投资理财」的细分子类记录在 minor_category -->
  <el-form-item v-if="majorCategory === 'investment'" label="投资类型">
    <el-select
      v-model="minorCategory"
      class="w-full"
      clearable
      placeholder="可不选，如银行理财、信托、私募等"
      @clear="minorCategory = null"
    >
      <el-option
        v-for="opt in INVESTMENT_MINOR_CATEGORIES"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
    </el-select>
  </el-form-item>
</template>
