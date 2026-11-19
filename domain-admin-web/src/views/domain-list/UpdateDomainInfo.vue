<template>
  <div class="batch-update">
    <el-button
      link
      type="primary"
      :disabled="controller !== null"
      @click="startBatch"
    ><el-icon><Refresh /></el-icon>{{ $t('全部更新') }}</el-button>

    <span role="status" class="batch-update__status">
      <span v-if="statusText">{{ $t(statusText) }}</span>
      <template v-if="progress">
        <span>{{ $t('已完成') }} {{ progress.completed }}/{{ progress.total ?? '—' }}</span>
        <span>{{ $t('成功') }} {{ progress.success }}</span>
        <span>{{ $t('失败') }} {{ progress.failed }}</span>
      </template>
    </span>
  </div>
</template>

<script>
const POLL_INTERVAL = 2000
const RETRY_INTERVAL = 5000
const STATUS_TEXT = {
  queued: '等待执行',
  running: '正在更新',
  succeeded: '批量更新完成',
  failed: '批量更新失败',
}

export default {
  name: 'UpdateDomainInfo',
  emits: ['batch-finished'],

  data() {
    return {
      controller: null,
      pollTimer: null,
      progress: null,
      statusText: null,
    }
  },

  beforeUnmount() {
    clearTimeout(this.pollTimer)
    this.controller?.abort()
  },

  methods: {
    async startBatch() {
      if (this.controller) return

      const controller = new AbortController()
      const { signal } = controller
      this.controller = controller
      this.progress = null
      this.statusText = '正在提交'

      let res
      try {
        res = await this.$http.updateAllDomainCertInfoOfUser({}, { signal, silentError: true })
      } catch {
        // 客户端错误与接口拒绝均按启动失败处理。
      }

      if (signal.aborted) return
      const taskId = res?.data?.task_id
      if (!res?.ok || !Number.isInteger(taskId) || taskId <= 0) {
        this.controller = null
        this.statusText = typeof res?.msg === 'string' && res.msg ? res.msg : '批量更新启动失败'
        return
      }

      this.progress = { total: null, completed: 0, success: 0, failed: 0 }
      this.statusText = STATUS_TEXT.queued
      this.pollProgress(taskId, signal)
    },

    async pollProgress(taskId, signal) {
      let res
      try {
        res = await this.$http.getDomainCertBatchProgress(
          { task_id: taskId },
          { signal, timeout: 10000, silentError: true }
        )
      } catch {
        // 查询异常时保留上次进度，继续追踪同一任务。
      }

      if (signal.aborted) return
      const progress = res?.data
      if (!res?.ok || progress?.task_id !== taskId || !Object.prototype.hasOwnProperty.call(STATUS_TEXT, progress.state)) {
        this.statusText = '查询进度失败，正在重试'
        this.schedulePoll(taskId, signal, RETRY_INTERVAL)
        return
      }

      this.progress = progress
      this.statusText = STATUS_TEXT[progress.state]

      if (progress.state === 'succeeded' || progress.state === 'failed') {
        if (progress.state === 'failed' && progress.success > 0) {
          this.statusText = '批量更新部分失败'
        }
        this.controller = null
        this.$emit('batch-finished')
        return
      }

      this.schedulePoll(taskId, signal, POLL_INTERVAL)
    },

    schedulePoll(taskId, signal, delay) {
      this.pollTimer = setTimeout(() => this.pollProgress(taskId, signal), delay)
    },
  },
}
</script>

<style scoped>
.batch-update,
.batch-update__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 8px;
}

.batch-update__status {
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
}
</style>
