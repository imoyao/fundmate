<template>
  <div class="dashboard-editor-container">
<!--     参考github相关页面设计（https://github.com/explore）-->
    <div class="app-container">
<!--       筛选条件-->
      <div class="page-header">
        <el-form class="el-form--inline"
                 ref="form"
                 :model="queryForm"
                 :inline="true"
                 @submit.native.prevent>
          <el-form-item label="所属平台" prop="platName" class="el-form-item__label">
            <el-col>
              <el-select v-model="value1" multiple placeholder="请选择">
                <el-option
                  v-for="item in options"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value">
                </el-option>
              </el-select>
            </el-col>
          </el-form-item>
          <el-form-item label="风险等级" prop="riskLevel" class="el-form-item__label">
            <el-col>
              <el-select v-model="value1" multiple placeholder="请选择">
                <el-option
                  v-for="item in options"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value">
                </el-option>
              </el-select>
            </el-col>
          </el-form-item>
          <el-form-item label="主理人类型" prop="fpoMgrType" class="el-form-item__label">
            <el-col>
              <el-select v-model="value1" multiple placeholder="请选择">
                <el-option
                  v-for="item in options"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value">
                </el-option>
              </el-select>
            </el-col>
          </el-form-item>
          <el-button type="primary" icon="el-icon-search" v-waves @click="handleQuery">查询</el-button>
        </el-form>
      </div>
<!--      卡片列表-->
      <el-row class="panel-group card-panel-col" :gutter="45">
        <el-col :xs="24" :md="12" :lg="8">
          <el-card shadow="hover" style="margin-bottom: 20px;">
            <div slot="header" class="clearfix">
              <span>成长五剑</span>
              <el-tag size="mini" style="margin-left: 6px;">一石二鸟</el-tag>
              <el-button style="float: right; padding: 3px 0" type="text" icon="el-icon-star-off">加自选</el-button>
            </div>

            <el-main style="overflow: hidden">
              <el-col :span="20">
                <el-row :gutter="4" >
                  <!--                    指标信息-->
                  <el-col :span="24" style="text-align: center">
                    <var class="per-num" style="color:#F56C6C;font-size:24px">12.88%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">年化收益率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">12.88%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">最大回撤率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">2.88</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">夏普率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">27.00%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">波动率</span>
                  </el-col>
                </el-row>
              </el-col>

              <el-col :xs="24" :lg="4">
                <el-card shadow="never" class="el-card__body box-card" style="margin-top: 35px;width:200px">
                  <el-button type="text" icon="el-icon-arrow-right"></el-button>
                </el-card>
              </el-col>

            </el-main>
            <el-footer>
              <p>这里是组合长长长长长长长长1111描述</p>
            </el-footer>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12" :lg="8">
          <el-card shadow="hover" style="margin-bottom: 20px;">
            <div slot="header" class="clearfix">
              <span>成长五剑</span>
              <el-tag size="mini" style="margin-left: 6px;">一石二鸟</el-tag>
              <el-button style="float: right; padding: 3px 0" type="text" icon="el-icon-star-off">加自选</el-button>
            </div>

            <el-main style="overflow: hidden">
              <el-col :span="20">
                <el-row :gutter="4" >
                  <!--                    指标信息-->
                  <el-col :span="24" style="text-align: center">
                    <var class="per-num" style="color:#F56C6C;font-size:24px">12.88%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">年化收益率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">12.88%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">最大回撤率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">2.88</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">夏普率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">27.00%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">波动率</span>
                  </el-col>
                </el-row>
              </el-col>

              <el-col :xs="24" :lg="4">
                <el-card shadow="never" class="el-card__body box-card" style="margin-top: 35px;width:200px">
                  <el-button type="text" icon="el-icon-arrow-right"></el-button>
                </el-card>
              </el-col>

            </el-main>
            <el-footer>
              <p>这里是组合长长长长长长长长1111描述</p>
            </el-footer>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12" :lg="8">
          <el-card shadow="hover" style="margin-bottom: 20px;">
            <div slot="header" class="clearfix">
              <span>成长五剑</span>
              <el-tag size="mini" style="margin-left: 6px;">一石二鸟</el-tag>
              <el-button style="float: right; padding: 3px 0" type="text" icon="el-icon-star-off">加自选</el-button>
            </div>

            <el-main style="overflow: hidden">
              <el-col :span="20">
                <el-row :gutter="4" >
                  <!--                    指标信息-->
                  <el-col :span="24" style="text-align: center">
                    <var class="per-num" style="color:#F56C6C;font-size:24px">12.88%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">年化收益率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">12.88%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">最大回撤率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">2.88</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">夏普率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">27.00%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">波动率</span>
                  </el-col>
                </el-row>
              </el-col>

              <el-col :xs="24" :lg="4">
                <el-card shadow="never" class="el-card__body box-card" style="margin-top: 35px;width:200px">
                  <el-button type="text" icon="el-icon-arrow-right"></el-button>
                </el-card>
              </el-col>

            </el-main>
            <el-footer>
              <p>这里是组合长长长长长长长长1111描述</p>
            </el-footer>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12" :lg="8">
          <el-card shadow="hover" style="margin-bottom: 20px;">
            <div slot="header" class="clearfix">
              <span>成长五剑</span>
              <el-tag size="mini" style="margin-left: 6px;">一石二鸟</el-tag>
              <el-button style="float: right; padding: 3px 0" type="text" icon="el-icon-star-off">加自选</el-button>
            </div>

            <el-main style="overflow: hidden">
              <el-col :span="20">
                <el-row :gutter="4" >
                  <!--                    指标信息-->
                  <el-col :span="24" style="text-align: center">
                    <var class="per-num" style="color:#F56C6C;font-size:24px">12.88%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">年化收益率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">12.88%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">最大回撤率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">2.88</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">夏普率</span>
                  </el-col>
                  <el-col :xs="24" :lg="8" style="text-align: center">
                    <var class="per-num">27.00%</var>
                    <br>
                    <span style="line-height: 65px;font-size:12px">波动率</span>
                  </el-col>
                </el-row>
              </el-col>

              <el-col :xs="24" :lg="4">
                <el-card shadow="never" class="el-card__body box-card" style="margin-top: 35px;width:200px">
                  <el-button type="text" icon="el-icon-arrow-right"></el-button>
                </el-card>
              </el-col>

            </el-main>
            <el-footer>
              <p>这里是组合长长长长长长长长1111描述</p>
            </el-footer>
          </el-card>
        </el-col>
      </el-row>
<!--分页器-->
      <el-pagination
        background
        style="text-align: center;"
        :current-page="queryForm.pageNo"
        :layout="layout"
        :page-sizes="queryForm.pageSizes"
        :page-size="queryForm.pageSize"
        :total="total"
        @current-change="handleCurrentChange"
        @size-change="handleSizeChange"></el-pagination>

    </div>
    </div>

</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { getPortfolios } from '@/api/portfolios'

@Component({
  name: 'FundPortfolio'
})
export default class extends Vue {
  private queryForm = Object.assign({
    pageNo: 1,
    pageSize: 15,
    pageSizes: [10, 15, 20, 30],
    title: ''
  })

  private layout='total, sizes, prev, pager, next, jumper'
  private total= 0
  private options= [{
    value: '选项1',
    label: '黄金糕'
  }, {
    value: '选项2',
    label: '双皮奶'
  }, {
    value: '选项3',
    label: '蚵仔煎'
  }, {
    value: '选项4',
    label: '龙须面'
  }, {
    value: '选项5',
    label: '北京烤鸭'
  }]

  private value1= '1'

  created() {
    this.fetchData()
  }

  public handleSizeChange(val:number) {
    this.queryForm.pageSize = val
    this.fetchData()
  }

  public handleCurrentChange(val:number) {
    this.queryForm.pageNo = val
    this.fetchData()
  }

  public handleQuery() {
    this.queryForm.pageNo = 1
    this.fetchData()
  }

  private async fetchData() {
    try {
      const { data } = await getPortfolios({})
      this.queryForm = data.article
    } catch (err) {
      console.error(err)
    }
  }
}
</script>
<style scoped>
.dashboard-editor-container {
  padding: 32px;
  background-color: rgb(240, 242, 245);
  position: relative;
}
.box-card{
  border: 0;
}

.page-header {
  display: flex;
  align-items: center;
  padding: 20px 20px 0 20px;
  margin-bottom: 20px;
  background: #fff;
  border: 1px solid #ebeef5;
}
.panel-group {
  margin-top: 18px;
}
.card-panel-col {
  margin-bottom: 32px;
}
.text {
  font-size: 14px;
}

.item {
  margin-bottom: 18px;
}

.clearfix:before,
.clearfix:after {
  display: table;
  content: "";
}

.clearfix:after {
  clear: both
}

.box-card {
  width: 480px;
}
</style>
