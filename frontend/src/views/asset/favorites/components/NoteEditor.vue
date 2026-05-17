<template>
  <el-dialog v-model="show" title="编辑笔记" width="500px">
    <el-input type="textarea" v-model="noteContent" :rows="6" placeholder="写下你的思考..." />
    <template #footer>
      <el-button @click="show = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { updateWatchlistItem } from '@/api/watchlist';
import { ElMessage } from 'element-plus';

const props = defineProps<{ visible: boolean; item: any }>();
const emit = defineEmits(['update:visible', 'saved']);

const show = ref(false);
const noteContent = ref('');

watch(() => props.visible, (val) => {
  show.value = val;
  if (val && props.item) {
    noteContent.value = props.item.notes || '';
  }
});
watch(show, (val) => emit('update:visible', val));

const save = async () => {
  try {
    await updateWatchlistItem(props.item.id, { notes: noteContent.value });
    emit('saved');
    show.value = false;
    ElMessage.success('笔记已保存');
  } catch (e) {
    ElMessage.error('保存失败');
  }
};
</script>
