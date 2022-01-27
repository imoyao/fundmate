---
title: 导出支付宝理财记录
---
1. 查询支付宝账号注销时间：[帮助文档](https://help.alipay.com/lab/help_detail.htm?help_id=247394)
2. 点击[此链接](https://consumeprod.alipay.com/record/standard.htm) 登录支付宝；
   ```https://consumeprod.alipay.com/record/standard.htm```
3. 查询账单信息
   [![](https://pic.imgdb.cn/item/61e7ce262ab3f51d911a4b25.png)](https://pic.imgdb.cn/item/61e7ce262ab3f51d911a4b25.png)
4. 下载压缩包
   [![](https://pic.imgdb.cn/item/61e7cec82ab3f51d911ae260.png)](https://pic.imgdb.cn/item/61e7cec82ab3f51d911ae260.png)
5. 解压文件
6. 处理csv裸文件
   :::warning
   1. `IS_RECORD_TRANSACTIONAL_NUMBER`配置设置为`True`表明自愿将流水号作为记录的一部分上传到网站数据库，记录流水号涉及部分个人敏感数据上传，请确保使用时是自主配置该项。
   记录流水号有助于后期根据流水号去源网站回溯记录，操作示意如下：
   ![](https://pic.imgdb.cn/item/61f2603e2ab3f51d91af98a2.png)
   2. 关于隐私泄露，根据流水号查询账单详情在支付宝网站属于敏感操作，网站会通过二次扫码进行用户鉴权，所以不用担心资产安全及隐私泄露问题。
   :::
7. 导入网站
8. 查看导入记录