---
title: 导入交易单
permalink: /dev/import-trade-records
---
## 导入交易单主要的流程
1. 从网站导出、整理账单信息处理成模板需要的格式（目前支持支付宝+理财通账单）
   1. 账单处理，基本流程如下
   ![](https://cdn.jsdelivr.net/gh/masantu/statics/master/images/%E5%AF%BC%E5%85%A5%E4%BA%A4%E6%98%93%E8%B4%A6%E5%8D%95%E6%B5%81%E7%A8%8B.drawio.png)
   费率计算参考：[leytou/FundsDateViewer: 基金赎回费率计算工具](https://github.com/leytou/FundsDateViewer)
2. 理财产品转编码
  支付宝购买的产品是以名称导出的，其中除了基金还有理财产品和组合，我们采用以下的处理策略：
   1. 如果是基金产品，则可以直接匹配编码；
   2. 如果是理财产品，则需要去平台根据名称查询，如果没有查询到，则提交添加申请；
   3. 如果是投资组合，同上；
   ::: 如何判断我们购买的产品是组合？基金还是理财产品？
      1. 在“基金”页面选择相应的产品风险类型，点击进入
       ![选择相应的产品风险类型](https://cdn.jsdelivr.net/gh/masantu/statics/images/Snipaste_2022-03-09_11-12-54.png)
      2. 在风险类型分类页选择收益明细区域
       ![选择收益明细](https://cdn.jsdelivr.net/gh/masantu/statics/images/Snipaste_2022-03-09_11-09-41.png)
      3. 在下级页面查看产品归类
       ![注意左侧文字](https://cdn.jsdelivr.net/gh/masantu/statics/images/Snipaste_2022-03-09_11-14-45.png)
   :::
3. 梳理结果返回并确认
