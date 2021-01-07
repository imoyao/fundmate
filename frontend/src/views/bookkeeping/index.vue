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
  </div>
</template>

<script>
import Step1 from './Record/components/Step1'
import Step2 from './Record/components/Step2'
import Step3 from './Record/components/Step3'

export default {
  name: 'BookKeeping',
  components: { Step1, Step2, Step3 },
  data() {
    return {
      active: 1,
      form: {}
    }
  },
  methods: {
    handleSetStep(active, form) {
      this.active = active
      if (form) this.form = Object.assign(this.form, form)
    }
  }
}
</script>
<style lang="scss" scoped>
.pay-container {
  .steps {
    justify-content: center;
    margin-bottom: 20px;
  }
}
</style>
