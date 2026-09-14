<template>
  <section id="assetManagement" class="page">
    <div class="page-header">
      <h1>资产管理</h1>
      <div class="header-actions">
        <button class="action-button" @click="showAddAssetModal = true">
          + 新增资产
        </button>
        <button class="action-button">导出资产</button>
      </div>
    </div>

    <!-- 新增：资产总览区域 -->
    <div class="asset-summary-cards">
      <div class="summary-card net-asset">
        <div class="card-title">净资产</div>
        <div class="card-value">
          <MoneyDisplay :value="netAsset" :show-sign="false" />
        </div>
      </div>
      <div class="summary-card total-asset">
        <div class="card-title">资产总额</div>
        <div class="card-value">
          <MoneyDisplay :value="totalAsset" :show-sign="false" />
        </div>
      </div>
      <div class="summary-card total-liability">
        <div class="card-title">负债总额</div>
        <div class="card-value">
          <MoneyDisplay :value="totalLiability" :show-sign="false" />
        </div>
      </div>
    </div>

    <div class="filter-bar">
      <input v-model="searchQuery" type="text" placeholder="搜索资产..." />
      <select v-model="filterType">
        <option value="all">所有类型</option>
        <option value="stock">股票</option>
        <option value="fund">基金</option>
        <option value="bond">债券</option>
        <option value="realEstate">房地产</option>
        <option value="other">其他</option>
      </select>
      <select v-model="sortBy">
        <option value="name">按名称</option>
        <option value="value">按市值</option>
        <option value="profit">按盈亏</option>
      </select>
    </div>

    <div class="asset-list">
      <table>
        <thead>
          <tr>
            <th>名称</th>
            <th>类型</th>
            <th>市值</th>
            <th>成本</th>
            <th>盈亏</th>
            <th>盈亏率</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="asset in filteredAssets" :key="asset.id">
            <td>{{ asset.name }}</td>
            <td>{{ asset.type }}</td>
            <td>
              <MoneyDisplay :value="asset.value" :show-sign="false" />
            </td>
            <td>
              <MoneyDisplay :value="asset.cost" :show-sign="false" />
            </td>
            <td :class="{ profit: asset.profit > 0, loss: asset.profit < 0 }">
              <MoneyDisplay :value="asset.profit" />
            </td>
            <td
              :class="{
                profit: asset.profitRate > 0,
                loss: asset.profitRate < 0
              }"
            >
              <RiseFallText :value="asset.profitRate" />
            </td>
            <td>
              <button class="action-link">编辑</button>
              <button class="action-link">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Add Asset Modal -->
    <div v-if="showAddAssetModal" class="modal-overlay">
      <div class="modal-content">
        <h2>新增资产</h2>
        <form @submit.prevent="handleAssetFormSubmit">
          <div class="form-group">
            <label for="assetName">资产名称:</label>
            <input
              id="assetName"
              v-model="newAsset.name"
              type="text"
              required
            />
          </div>
          <div class="form-group">
            <label for="assetType">资产类型:</label>
            <select id="assetType" v-model="newAsset.type" required>
              <option value="stock">股票</option>
              <option value="fund">基金</option>
              <option value="bond">债券</option>
              <option value="realEstate">房地产</option>
              <option value="other">其他</option>
            </select>
          </div>
          <div class="form-group">
            <label for="assetValue">市值:</label>
            <input
              id="assetValue"
              v-model.number="newAsset.value"
              type="number"
              required
            />
          </div>
          <div class="form-group">
            <label for="assetCost">成本:</label>
            <input
              id="assetCost"
              v-model.number="newAsset.cost"
              type="number"
              required
            />
          </div>
          <div class="form-actions">
            <button type="submit" class="btn-primary">添加</button>
            <button
              type="button"
              class="btn-secondary"
              @click="showAddAssetModal = false"
            >
              取消
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";

const showAddAssetModal = ref(false);

const searchQuery = ref("");
const filterType = ref("all");
const sortBy = ref("name");

const assets = ref([
  {
    id: 1,
    name: "沪深300ETF",
    type: "stock",
    value: 125678.9,
    cost: 122222.12,
    profit: 3456.78,
    profitRate: 2.83
  },
  {
    id: 2,
    name: "理财产品A",
    type: "fund",
    value: 200000.0,
    cost: 201200.0,
    profit: -1200.0,
    profitRate: -0.6
  },
  {
    id: 3,
    name: "定期存款",
    type: "other",
    value: 300000.0,
    cost: 297750.0,
    profit: 2250.0,
    profitRate: 0.76
  },
  {
    id: 4,
    name: "房产投资",
    type: "realEstate",
    value: 1500000.0,
    cost: 1485000.0,
    profit: 15000.0,
    profitRate: 1.01
  },
  {
    id: 5,
    name: "贵金属",
    type: "other",
    value: 50000.0,
    cost: 48500.0,
    profit: 1500.0,
    profitRate: 3.09
  }
]);

// 新增：计算总资产、总负债和净资产
const totalAsset = computed(() => {
  // 假设所有 assets 都是资产，如果需要区分资产和负债，需要修改数据结构
  return assets.value.reduce((sum, asset) => sum + asset.value, 0);
});

const totalLiability = computed(() => {
  // 假设没有负债数据，这里暂时设置为0，实际应从数据中获取
  return 0;
});

const netAsset = computed(() => {
  return totalAsset.value - totalLiability.value;
});

const newAsset = ref({
  name: "",
  type: "stock",
  value: 0,
  cost: 0
});

const filteredAssets = computed(() => {
  let filtered = assets.value;

  if (filterType.value !== "all") {
    filtered = filtered.filter(asset => asset.type === filterType.value);
  }

  if (searchQuery.value) {
    filtered = filtered.filter(asset =>
      asset.name.toLowerCase().includes(searchQuery.value.toLowerCase())
    );
  }

  // Sorting
  filtered.sort((a, b) => {
    if (sortBy.value === "name") {
      return a.name.localeCompare(b.name);
    } else if (sortBy.value === "value") {
      return b.value - a.value; // Descending
    } else if (sortBy.value === "profit") {
      return b.profit - a.profit; // Descending
    }
    return 0;
  });

  return filtered;
});

const handleAssetFormSubmit = () => {
  const id =
    assets.value.length > 0 ? Math.max(...assets.value.map(a => a.id)) + 1 : 1;
  const profit = newAsset.value.value - newAsset.value.cost;
  const profitRate = (profit / newAsset.value.cost) * 100;
  assets.value.push({
    id,
    name: newAsset.value.name,
    type: newAsset.value.type,
    value: newAsset.value.value,
    cost: newAsset.value.cost,
    profit,
    profitRate
  });
  showAddAssetModal.value = false;
  newAsset.value = { name: "", type: "stock", value: 0, cost: 0 }; // Reset form
};
</script>

<style lang="scss" scoped>
@import url("../../style/index.scss");

/* 新增：资产总览区域样式 */
.asset-summary-cards {
  display: flex;
  justify-content: space-around;
  margin-bottom: 20px;

  .summary-card {
    flex: 1;
    padding: 20px;
    margin: 0 10px;
    text-align: center;
    background-color: var(--el-bg-color);
    border-radius: 8px;
    box-shadow: var(--el-box-shadow-lighter);

    .card-title {
      margin-bottom: 10px;
      font-size: 16px;
      color: var(--el-text-color-secondary);
    }

    .card-value {
      font-size: 24px;
      font-weight: bold;
      color: var(--el-text-color-primary);
    }
  }
}

/* 现有样式 */
.page {
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;

  h1 {
    font-size: 24px;
    color: var(--el-text-color-primary);
  }

  .header-actions {
    .action-button {
      padding: 8px 15px;
      margin-left: 10px;
      font-size: 14px;
      color: var(--text-inverse);
      cursor: pointer;
      background-color: var(--el-color-primary);
      border: none;
      border-radius: 4px;

      &:hover {
        background-color: var(--el-color-primary-light-1);
      }
    }
  }
}

.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;

  input,
  select {
    padding: 8px;
    font-size: 14px;
    color: var(--el-text-color-primary);
    background-color: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color);
    border-radius: 4px;
  }
}

.asset-list {
  overflow-x: auto;
  background-color: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: var(--el-box-shadow-lighter);

  table {
    width: 100%;
    border-collapse: collapse;

    th,
    td {
      padding: 12px 15px;
      color: var(--el-text-color-regular);
      text-align: left;
      border-bottom: 1px solid var(--el-border-color-light);
    }

    th {
      font-weight: bold;
      color: var(--el-text-color-secondary);
      background-color: var(--el-fill-color-light);
    }

    tbody tr:last-child td {
      border-bottom: none;
    }

    .profit {
      color: var(--el-color-success);
    }

    .loss {
      color: var(--el-color-error);
    }

    .action-link {
      margin-right: 10px;
      font-size: 14px;
      color: var(--el-color-primary);
      cursor: pointer;
      background: none;
      border: none;

      &:hover {
        text-decoration: underline;
      }
    }
  }
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background-color: rgb(0 0 0 / 50%);
}

.modal-content {
  width: 400px;
  padding: 30px;
  background-color: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: var(--el-box-shadow);

  h2 {
    margin-bottom: 20px;
    font-size: 22px;
    color: var(--el-text-color-primary);
  }

  .form-group {
    margin-bottom: 15px;

    label {
      display: block;
      margin-bottom: 5px;
      font-size: 14px;
      color: var(--el-text-color-regular);
    }

    input,
    select {
      width: 100%;
      padding: 10px;
      font-size: 14px;
      color: var(--el-text-color-primary);
      background-color: var(--el-fill-color-light);
      border: 1px solid var(--el-border-color);
      border-radius: 4px;
    }
  }

  .form-actions {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    margin-top: 20px;

    .btn-primary,
    .btn-secondary {
      padding: 10px 20px;
      font-size: 14px;
      cursor: pointer;
      border-radius: 4px;
    }

    .btn-primary {
      color: var(--text-inverse);
      background-color: var(--el-color-primary);
      border: none;

      &:hover {
        background-color: var(--el-color-primary-light-1);
      }
    }

    .btn-secondary {
      color: var(--el-text-color-regular);
      background-color: var(--el-button-bg-color);
      border: 1px solid var(--el-border-color);

      &:hover {
        background-color: var(--el-fill-color-light);
      }
    }
  }
}
</style>
