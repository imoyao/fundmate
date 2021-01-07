<template>
  <div>
    <el-tabs v-model="activeName" @tab-click="handleClick">
    <el-tab-pane label="申购" name="first">
      <el-form ref="form" :model="form" :rules="rules" label-width="120px">
      <el-form-item label-width="0">
        <el-alert show-icon>试玉要烧三日满，辨材须待七年期。待到财富自由时，君在丛中笑!</el-alert>
      </el-form-item>
      <!--  TODO:    优先用户已有账户，其次预设券商名称，最后用户可输入自定义-->

      <el-form-item label="账户名称" prop="payAccount">
        <el-select
          v-model="form.payAccount"
          filterable
          allow-create
          default-first-option
          prop="payAccount"
          placeholder="请选择/输入账户名称">
          <el-option
            v-for="item in userAccounts"
            :key="item.value"
            :label="item.label"
            :value="item.value">
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="收款账户" prop="gatheringAccount">
        <el-input v-model="form.gatheringAccount"></el-input>
      </el-form-item>
      <el-form-item label="收款人姓名" prop="gatheringName">
        <el-input v-model="form.gatheringName"></el-input>
      </el-form-item>
      <el-form-item label="转账金额" prop="price">
        <el-input v-model="form.price"></el-input>
      </el-form-item>
    </el-form>
    <div class="pay-button-group">
      <el-button type="primary" @click="handleSubmit">下一步</el-button>
    </div>
    </el-tab-pane>
    <el-tab-pane label="赎回" name="second">
      <el-form ref="form" :model="form" :rules="rules" label-width="120px">
      <el-form-item label-width="0">
        <el-alert show-icon>剑术已成</el-alert>
      </el-form-item>
      <!--  TODO:    优先用户已有账户，其次预设券商名称，最后用户可输入自定义-->

      <el-form-item label="账户名称" prop="payAccount">
        <el-select
          v-model="form.payAccount"
          filterable
          allow-create
          default-first-option
          prop="payAccount"
          class="select-box"
          placeholder="请选择/输入账户名称">
          <el-option
            v-for="item in userAccounts"
            :key="item.value"
            :label="item.label"
            :value="item.value">
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="收款账户" prop="gatheringAccount">
        <el-input v-model="form.gatheringAccount"></el-input>
      </el-form-item>
      <el-form-item label="收款人姓名" prop="gatheringName">
        <el-input v-model="form.gatheringName"></el-input>
      </el-form-item>
      <el-form-item label="转账金额" prop="price">
        <el-input v-model="form.price"></el-input>
      </el-form-item>
    </el-form>
    <div class="pay-button-group">
      <el-button type="primary" @click="handleSubmit">下一步</el-button>
    </div>
    </el-tab-pane>
    <el-tab-pane label="转换" name="third">
      <el-form ref="form" :model="form" :rules="rules" label-width="120px">
      <el-form-item label-width="0">
        <el-alert show-icon>安能辨我是雄雌</el-alert>
      </el-form-item>
      <!--  TODO:    优先用户已有账户，其次预设券商名称，最后用户可输入自定义-->

      <el-form-item label="账户名称" prop="payAccount">
        <el-select
          v-model="form.payAccount"
          filterable
          allow-create
          default-first-option
          prop="payAccount"
          placeholder="请选择/输入账户名称">
          <el-option
            v-for="item in userAccounts"
            :key="item.value"
            :label="item.label"
            :value="item.value">
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="收款账户" prop="gatheringAccount">
        <el-input v-model="form.gatheringAccount"></el-input>
      </el-form-item>
      <el-form-item label="收款人姓名" prop="gatheringName">
        <el-input v-model="form.gatheringName"></el-input>
      </el-form-item>
      <el-form-item label="转账金额" prop="price">
        <el-input v-model="form.price"></el-input>
      </el-form-item>
    </el-form>
    <div class="pay-button-group">
      <el-button type="primary" @click="handleSubmit">下一步</el-button>
    </div>
    </el-tab-pane>
  </el-tabs>
  </div>
</template>
<script>
export default {
  data() {
    return {
      activeName: 'first',
      // 用户已有账户
      userAccounts: [{
        value: '支付宝',
        label: '支付宝'
      }, {
        value: '理财通',
        label: '理财通'
      }, {
        value: '天天基金',
        label: '天天基金'
      }],
      form: {
        payAccount: '理财通',
        gatheringAccount: 'fundmate@163.com',
        gatheringName: 'imoyao',
        price: '10000'
      },
      rules: {
        payAccount: [
          { required: true, message: '请选择/输入账户信息', trigger: 'blur' }
        ],
        gatheringAccount: [
          { required: true, message: '请输入收款账户', trigger: 'blur' },
          { type: 'email', message: '账户名应为邮箱格式', trigger: 'blur' }
        ],
        gatheringName: [
          { required: true, message: '请输入收款人姓名', trigger: 'blur' }
        ],
        price: [
          { required: true, message: '请输入转账金额', trigger: 'blur' },
          { pattern: /^(\d+)((?:\.\d+)?)$/, message: '请输入合法金额数字' }
        ]
      }
    }
  },
  methods: {
    handleClick(tab, event) {
      console.log(tab, event)
    },
    handleSubmit() {
      this.$refs.form.validate((valid) => {
        if (valid) {
          this.$emit('change-step', 2, this.form)
        }
      })
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
.select-box{
  width: 100%;
}
</style>
