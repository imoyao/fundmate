<template>
  <div class="p-4">
    <div class="flex justify-between items-center mb-6">
      <Tabs :tabs="assetTypes" />
      <div class="flex gap-2">
        <SearchBar />
        <Button icon="plus">添加资产</Button>
      </div>
    </div>

    <AssetDetailsTable :assets="filteredAssets" />
  </div>
</template>

<script setup>
// 导入组件和逻辑
</script>
