<template>
  <div class="asset-detail p-6">
    <div class="mb-8">
      <h2 class="text-2xl font-bold">资产明细</h2>
      <p class="text-gray-500 mt-1">您的每一笔资产详情</p>
    </div>

    <div class="bg-white rounded-xl shadow-md overflow-hidden">
      <div class="p-6">
        <div class="flex flex-wrap gap-3 mb-6">
          <select
            class="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-orange-500 text-sm shadow-sm"
          >
            <option>全部资产类型</option>
            <option>股票</option>
            <option>基金</option>
            <option>房产</option>
            <option>贵金属</option>
          </select>
          <select
            class="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-orange-500 text-sm shadow-sm"
          >
            <option>全部账户</option>
            <option>股票账户</option>
            <option>基金账户</option>
          </select>
          <input
            type="text"
            placeholder="搜索资产名称..."
            class="flex-1 max-w-xs px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-orange-500 text-sm shadow-sm"
          />
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <div
            class="border border-gray-200 rounded-lg p-4 hover:shadow-lg transition-shadow"
          >
            <div class="flex justify-between items-start mb-3">
              <div>
                <h4 class="font-bold text-sm">腾讯控股</h4>
                <p class="text-xs text-gray-500">00700.HK | 股票</p>
              </div>
              <span
                class="px-2 py-0.5 bg-red-100 text-red-600 text-[10px] rounded-full font-medium"
                >高风险</span
              >
            </div>
            <div class="grid grid-cols-2 gap-3 mb-3 text-xs">
              <div>
                <p class="text-gray-500">持有数量</p>
                <p class="font-medium">500 股</p>
              </div>
              <div>
                <p class="text-gray-500">当前价格</p>
                <p class="font-medium text-orange-500">¥345.60</p>
              </div>
              <div>
                <p class="text-gray-500">持仓成本</p>
                <p class="font-medium">¥320.00</p>
              </div>
              <div>
                <p class="text-gray-500">市值</p>
                <p class="font-medium">¥172,800</p>
              </div>
            </div>
            <div
              class="pt-3 border-t border-gray-100 flex justify-between items-center"
            >
              <p class="text-green-600 font-bold text-sm">
                <IconifyIconOffline
                  icon="ep:arrow-up-bold"
                  class="mr-0.5 text-xs"
                />+¥12,800 (+8.00%)
              </p>
              <div class="flex gap-1.5">
                <button
                  class="px-2.5 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 transition-colors"
                >
                  买入
                </button>
                <button
                  class="px-2.5 py-1 bg-red-500 text-white text-xs rounded-lg hover:bg-red-600 transition-colors"
                >
                  卖出
                </button>
              </div>
            </div>
          </div>

          <div
            class="border border-gray-200 rounded-lg p-4 hover:shadow-lg transition-shadow"
          >
            <div class="flex justify-between items-start mb-3">
              <div>
                <h4 class="font-bold text-sm">易方达消费精选</h4>
                <p class="text-xs text-gray-500">009265 | 基金</p>
              </div>
              <span
                class="px-2 py-0.5 bg-amber-100 text-amber-600 text-[10px] rounded-full font-medium"
                >中风险</span
              >
            </div>
            <div class="grid grid-cols-2 gap-3 mb-3 text-xs">
              <div>
                <p class="text-gray-500">持有份额</p>
                <p class="font-medium">50,000 份</p>
              </div>
              <div>
                <p class="text-gray-500">单位净值</p>
                <p class="font-medium text-red-600">¥1.2450</p>
              </div>
              <div>
                <p class="text-gray-500">持仓成本</p>
                <p class="font-medium">¥1.2800</p>
              </div>
              <div>
                <p class="text-gray-500">市值</p>
                <p class="font-medium">¥62,250</p>
              </div>
            </div>
            <div
              class="pt-3 border-t border-gray-100 flex justify-between items-center"
            >
              <p class="text-red-600 font-bold text-sm">
                <IconifyIconOffline
                  icon="ep:arrow-down-bold"
                  class="mr-0.5 text-xs"
                />-¥1,750 (-2.73%)
              </p>
              <div class="flex gap-1.5">
                <button
                  class="px-2.5 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 transition-colors"
                >
                  申购
                </button>
                <button
                  class="px-2.5 py-1 bg-red-500 text-white text-xs rounded-lg hover:bg-red-600 transition-colors"
                >
                  赎回
                </button>
              </div>
            </div>
          </div>

          <div
            class="border border-gray-200 rounded-lg p-4 hover:shadow-lg transition-shadow"
          >
            <div class="flex justify-between items-start mb-3">
              <div>
                <h4 class="font-bold text-sm">阳光花园小区</h4>
                <p class="text-xs text-gray-500">房产 | 自住</p>
              </div>
              <span
                class="px-2 py-0.5 bg-green-100 text-green-600 text-[10px] rounded-full font-medium"
                >低风险</span
              >
            </div>
            <div class="grid grid-cols-2 gap-3 mb-3 text-xs">
              <div>
                <p class="text-gray-500">面积</p>
                <p class="font-medium">120 ㎡</p>
              </div>
              <div>
                <p class="text-gray-500">当前估值</p>
                <p class="font-medium text-green-600">¥810,488</p>
              </div>
              <div>
                <p class="text-gray-500">购入价格</p>
                <p class="font-medium">¥680,000</p>
              </div>
              <div>
                <p class="text-gray-500">购入日期</p>
                <p class="font-medium">2020-05-20</p>
              </div>
            </div>
            <div
              class="pt-3 border-t border-gray-100 flex justify-between items-center"
            >
              <p class="text-green-600 font-bold text-sm">
                <IconifyIconOffline
                  icon="ep:arrow-up-bold"
                  class="mr-0.5 text-xs"
                />+¥130,488 (+19.19%)
              </p>
              <button
                class="px-2.5 py-1 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200 transition-colors"
              >
                查看详情
              </button>
            </div>
          </div>

          <div
            class="border border-gray-200 rounded-lg p-4 hover:shadow-lg transition-shadow"
          >
            <div class="flex justify-between items-start mb-3">
              <div>
                <h4 class="font-bold text-sm">贵州茅台</h4>
                <p class="text-xs text-gray-500">600519.SH | 股票</p>
              </div>
              <span
                class="px-2 py-0.5 bg-red-100 text-red-600 text-[10px] rounded-full font-medium"
                >高风险</span
              >
            </div>
            <div class="grid grid-cols-2 gap-3 mb-3 text-xs">
              <div>
                <p class="text-gray-500">持有数量</p>
                <p class="font-medium">100 股</p>
              </div>
              <div>
                <p class="text-gray-500">当前价格</p>
                <p class="font-medium text-orange-500">¥1,520.00</p>
              </div>
              <div>
                <p class="text-gray-500">持仓成本</p>
                <p class="font-medium">¥1,450.00</p>
              </div>
              <div>
                <p class="text-gray-500">市值</p>
                <p class="font-medium">¥152,000</p>
              </div>
            </div>
            <div
              class="pt-3 border-t border-gray-100 flex justify-between items-center"
            >
              <p class="text-green-600 font-bold text-sm">
                <IconifyIconOffline
                  icon="ep:arrow-up-bold"
                  class="mr-0.5 text-xs"
                />+¥7,000 (+4.83%)
              </p>
              <div class="flex gap-1.5">
                <button
                  class="px-2.5 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 transition-colors"
                >
                  买入
                </button>
                <button
                  class="px-2.5 py-1 bg-red-500 text-white text-xs rounded-lg hover:bg-red-600 transition-colors"
                >
                  卖出
                </button>
              </div>
            </div>
          </div>

          <div
            class="border border-gray-200 rounded-lg p-4 hover:shadow-lg transition-shadow"
          >
            <div class="flex justify-between items-start mb-3">
              <div>
                <h4 class="font-bold text-sm">纳斯达克100ETF</h4>
                <p class="text-xs text-gray-500">513100 | 基金</p>
              </div>
              <span
                class="px-2 py-0.5 bg-amber-100 text-amber-600 text-[10px] rounded-full font-medium"
                >中风险</span
              >
            </div>
            <div class="grid grid-cols-2 gap-3 mb-3 text-xs">
              <div>
                <p class="text-gray-500">持有份额</p>
                <p class="font-medium">10,000 份</p>
              </div>
              <div>
                <p class="text-gray-500">单位净值</p>
                <p class="font-medium text-green-600">¥1.978</p>
              </div>
              <div>
                <p class="text-gray-500">持仓成本</p>
                <p class="font-medium">¥1.850</p>
              </div>
              <div>
                <p class="text-gray-500">市值</p>
                <p class="font-medium">¥19,780</p>
              </div>
            </div>
            <div
              class="pt-3 border-t border-gray-100 flex justify-between items-center"
            >
              <p class="text-green-600 font-bold text-sm">
                <IconifyIconOffline
                  icon="ep:arrow-up-bold"
                  class="mr-0.5 text-xs"
                />+¥1,280 (+6.92%)
              </p>
              <div class="flex gap-1.5">
                <button
                  class="px-2.5 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 transition-colors"
                >
                  申购
                </button>
                <button
                  class="px-2.5 py-1 bg-red-500 text-white text-xs rounded-lg hover:bg-red-600 transition-colors"
                >
                  赎回
                </button>
              </div>
            </div>
          </div>

          <div
            class="border border-gray-200 rounded-lg p-4 hover:shadow-lg transition-shadow"
          >
            <div class="flex justify-between items-start mb-3">
              <div>
                <h4 class="font-bold text-sm">实物黄金</h4>
                <p class="text-xs text-gray-500">贵金属 | 投资</p>
              </div>
              <span
                class="px-2 py-0.5 bg-amber-100 text-amber-600 text-[10px] rounded-full font-medium"
                >中风险</span
              >
            </div>
            <div class="grid grid-cols-2 gap-3 mb-3 text-xs">
              <div>
                <p class="text-gray-500">持有重量</p>
                <p class="font-medium">100 克</p>
              </div>
              <div>
                <p class="text-gray-500">当前价格</p>
                <p class="font-medium text-yellow-600">¥580/克</p>
              </div>
              <div>
                <p class="text-gray-500">购入价格</p>
                <p class="font-medium">¥520/克</p>
              </div>
              <div>
                <p class="text-gray-500">市值</p>
                <p class="font-medium">¥58,000</p>
              </div>
            </div>
            <div
              class="pt-3 border-t border-gray-100 flex justify-between items-center"
            >
              <p class="text-green-600 font-bold text-sm">
                <IconifyIconOffline
                  icon="ep:arrow-up-bold"
                  class="mr-0.5 text-xs"
                />+¥6,000 (+11.54%)
              </p>
              <button
                class="px-2.5 py-1 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200 transition-colors"
              >
                查看详情
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";

const filterType = ref("all");
const filterAccount = ref("all");
const searchQuery = ref("");
</script>

<style scoped>
.asset-detail {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
