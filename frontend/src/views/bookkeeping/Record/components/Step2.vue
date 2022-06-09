<template>
  <div>
    <el-form ref="form" :model="form" :rules="rules" label-width="120px">
      <el-form-item label-width="0">
        <el-alert show-icon>
          请检查并确认交易信息是否正确。
        </el-alert>
      </el-form-item>
      <el-form-item label="账户名称：">
        {{ infoData.payAccount }}
      </el-form-item>
      <el-form-item label="交易基金：">
        {{ infoData.gatheringAccount }}
      </el-form-item>
      <el-form-item label="购买金额：">
        {{ infoData.purchaseAmount }}
      </el-form-item>
      <el-form-item label="交易手续费：">
        <strong>
          {{ infoData.tradeFee }}
        </strong>
      </el-form-item>
    </el-form>
    <div class="pay-button-group">
      <el-button type="primary" :loading="loading" @click="handleSubmit">
        提交
      </el-button>
      <el-button @click="handlePrev">上一步</el-button>
    </div>
  </div>
</template>
<script>
export default {
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
      loading: false
    }
  },
  methods: {
    handleSubmit() {
      this.$refs.form.validate((valid) => {
        if (valid) {
          this.loading = true
          setTimeout(() => {
            this.$emit('change-step', 3)
            this.loading = false
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
.pay-button-group {
  display: block;
  margin: 20px auto;
  text-align: center;
}
</style>
