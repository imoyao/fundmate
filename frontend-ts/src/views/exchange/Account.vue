<template>
  <div class="app-container">
    <el-row :gutter="20">
      <!--      TODO:后端计算，缓存数据，每天更新 需要可以排序显示-->
      <el-col :span="12" :offset="6" class="account-item">
        <el-card class="box-card" shadow="hover">
          <div slot="header" class="clearfix item-header">
            <span>蚂蚁财富（支付宝）</span>
            <el-button style="float: right; padding: 3px 0" type="text">详情</el-button>
          </div>
          <el-row type="flex" class="row-bg c-box-bd clearfix" justify="space-around">
            <el-col :span="6">
              <div class="col-div col-divcol-c">
                <p class="bt">持有资产(元)</p>
                <p class="num"><b>5,613</b>.30</p>
                <el-tag type="danger" size="mini">32%</el-tag>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="col-div col-z">
                <p class="bt">昨日收益(元)</p>
                <p class="num"><b>0</b>.42 </p>
                <el-tag type="danger" size="mini">1.02%</el-tag>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="col-div col-l">
                <p class="bt">累计收益(元)</p>
                <p class="num "><b>784</b>.02</p>
                <el-tag type="danger" size="mini">158%</el-tag>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
      <!--      子项目-->
      <el-col :span="12" :offset="6" class="account-item">
        <el-card class="box-card" shadow="hover">
          <div slot="header" class="clearfix item-header">
            <span>理财通</span>
            <el-button style="float: right; padding: 3px 0" type="text">详情</el-button>
          </div>
          <el-row type="flex" class="row-bg c-box-bd clearfix" justify="space-around">
            <el-col :span="6">
              <div class="col-div col-divcol-c">
                <p class="bt">持有资产(元)</p>
                <p class="num"><b>5,613</b>.30</p>
                <el-tag type="danger" size="mini">32%</el-tag>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="col-div col-z">
                <p class="bt">昨日收益(元)</p>
                <p class="num"><b>0</b>.42 </p>
                <el-tag type="danger" size="mini">1.02%</el-tag>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="col-div col-l">
                <p class="bt">累计收益(元)</p>
                <p class="num "><b>784</b>.02</p>
                <el-tag type="danger" size="mini">158%</el-tag>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script lang="ts">

import {Component, Vue} from 'vue-property-decorator'

@Component({
  name: 'Account'
})

export default class extends Vue {

}

</script>

<style lang="scss" scoped>
.el-row {
  margin-bottom: 20px;
  .el-col,
  .account-item {
    margin-bottom: 10px;

    .col-div {
      p.num {
        display: inline;
      }
    }
  }

}
  .el-card__header {
    background-color: #fafbfc;
  }
.row-bg {
  padding: 10px 0;
  //background-color: #f9fafc;
}
</style>
