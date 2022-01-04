<template>
  <div>
    <div class="pay-top-content">
      <svg-icon class="pay-success" :icon="['fas', 'check-circle']"></svg-icon>
      <p>记账成功</p>
    </div>
    <el-form
      ref="form"
      :model="form"
      :rules="rules"
      label-width="120px"
      class="pay-bottom"
    >
      <el-form-item label="账户名称：">
        {{ infoData.payAccount }}
      </el-form-item>
      <el-form-item label="购买日期：">
        {{ infoData.gatheringAccount }}
      </el-form-item>
      <el-form-item label="购买基金：">
        {{ infoData.gatheringName }}
      </el-form-item>
      <el-form-item label="购买基金：">
        {{ infoData.gatheringName }}
      </el-form-item>
      <el-form-item label="购买金额：">
        <strong>
          {{ infoData.price }}
        </strong>
      </el-form-item>
    </el-form>
    <div class="pay-button-group">
      <el-button type="primary" @click="handlePrev">再记一笔</el-button>
      <!--  跳转到账本页面-->
      <el-button type="info" @click="handlePrev">下次再会</el-button>
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
