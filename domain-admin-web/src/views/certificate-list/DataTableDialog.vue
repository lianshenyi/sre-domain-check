<template>
  <!-- 编辑框 -->
  <el-dialog
    :title="dialogTitle"
    v-model="dialogVisible"
    width="340px"
    center
    append-to-body
    @close="handleClose"
  >
    <DataTableIndex
      v-if="dialogVisible"
      :row="row"
      @on-cancel="handleCancel"
      @on-success="handleSuccess"
    ></DataTableIndex>
  </el-dialog>
</template>

<script>
/**
 * created 2022-10-11
 */
import DataTableIndex from './index.vue'

export default {
  name: '',

  props: {
    // 数据行
    row: {
      type: Object,
      default: null,
    },

    // 显示
    visible: {
      type: Boolean,
      default: false,
    },
  },

  components: {
    DataTableIndex,
  },

  data() {
    return {
      // currentRow: null,
      // dialogVisible: false,
    }
  },

  computed: {
    dialogTitle() {
      if (this.row) {
        return '编辑'
      } else {
        return '添加'
      }
    },

    dialogVisible: {
      get() {
        return this.visible
      },
      set(val) {
        this.$emit('update:visible', val)
      },
    },
  },

  methods: {
    handleClose() {
      console.log('handleClose');
      
      this.$emit('on-close')
    },

    handleOpen() {
      this.dialogVisible = true
    },

    handleCancel(){
      this.dialogVisible = false
    },

    handleSuccess() {
      this.dialogVisible = false
      this.$emit('on-success')
    },
  },

  created() {},
}
</script>

<style lang="less"></style>

<style lang="less" scoped></style>
