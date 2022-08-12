<template>
  <div>
    <div class="pay-top-content">
      <svg-icon class="pay-success" :icon="['fas', 'check-circle']"></svg-icon>
      <p>信息确认</p>
    </div>
    <el-form
      ref="form"
      :model="form"
      :rules="rules"
      label-width="120px"
      class="pay-bottom"
    >
      <el-form-item label="账本名称：">
        {{ infoData.payAccount || '示例账本名称'}}
      </el-form-item>
      <el-form-item label="购买基金：">
        {{ infoData.gatheringName || '一个示例基金名称测试测试（888888）' }}
      </el-form-item>
      <el-form-item label="确认日期：">
        <el-badge :value="`单位净值： ${infoData.gatheringName || '暂无'} `" class="item" type="warning">
        {{ infoData.gatheringAccount }} 2022-08-12
        </el-badge>
      </el-form-item>
      <el-form-item label="确认份额：">
        {{ infoData.gatheringName }}
      </el-form-item>
      <el-form-item label="交易费用：">
        {{ infoData.gatheringName }}
      </el-form-item>
      <el-form-item label="购买金额：">
        <strong>
          {{ infoData.price }}
        </strong>
      </el-form-item>
    </el-form>
    <div class="pay-button-group">
      <!-- 用户调整输入-->
      <el-button type="info" :plain="this.isSubmit===false" :disabled="this.isSubmit===false" @click="handlePrev">再记</el-button>
      <el-button type="warning" @click="handlePrev">修改</el-button>
      <!--     默认可以点击修改和提交，再记和查看不可点击 点击提交之后再记可以点击-->
      <!-- 用户提交记录-->
      <el-button type="primary" @click="handleSubmit">提交</el-button>
      <!--  默认点击提交后3秒跳转到账本记录页面-->
      <el-button type="info" :plain="this.isSubmit===false" :disabled="this.isSubmit===false" @click="handlePrev">查看</el-button>
    </div>
  </div>
</template>
<script>
// import VabIcon from 'vab-icon'

export default {
  // components: { VabIcon },
  props: {
    infoData: {
      type: Object,
      default: () => {
        return {}
      }
    }
  },
  data() {
    return {
      form: {
        password: '123456'
      },
      rules: {
        password: [
          { required: true, message: '请输入支付密码', trigger: 'blur' }
        ]
      },
      loading: false,
      isSubmit: false
    }
  },
  methods: {
    handleSubmit() {
      this.$refs.form.validate((valid) => {
        if (valid) {
          this.loading = true
          this.isSubmit = true
          setTimeout(() => {
            this.$emit('change-step', 3)
            this.loading = false
            this.isSubmit = false
          }, 2000)
        } else {
          this.loading = false
        }
      })
    },
    handlePrev() {
      this.$emit('change-step', 1)
    }
  }
}
</script>
<style lang="scss" scoped>
$color-green: #13CE66FF;
$color-gray: #9E9E9E;

.pay-top-content {
  text-align: center;

  .pay-success {
    display: block;
    margin: 20px auto 5px auto;
    font-size: 40px;
    color: $color-green;
  }
}

.pay-bottom {
  padding: 20px;
  margin-top: 20px;
  background: #f5f7f8;
  border: 1px dashed $color-gray;
}

.pay-button-group {
  display: block;
  margin: 20px auto;
  text-align: center;
}
</style>
