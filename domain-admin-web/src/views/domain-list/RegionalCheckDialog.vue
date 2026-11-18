<template>
  <el-dialog
    :model-value="true"
    title="区域复测"
    width="min(960px, calc(100vw - 32px))"
    @update:model-value="emit('close')"
  >
    <p class="target">{{ domain.domain }}（端口 {{ domain.port }}）</p>
    <el-form label-position="top" @submit.prevent="startCheck">
      <fieldset class="agent-picker">
        <legend>复测节点</legend>
        <template v-if="selectableAgents.length">
          <p>选择 1–10 个已登记节点。离线节点可在任务到期前重连并执行。</p>
          <el-checkbox-group
            v-model="selectedIds"
            class="agent-options"
            aria-label="已登记节点"
            :max="10"
            :disabled="starting || agentError"
          >
            <el-checkbox
              v-for="agent in selectableAgents"
              :key="agent.id"
              :label="agent.id"
            >
              {{ agent.region }} / {{ agent.name }} #{{ agent.id }}（{{ AGENT_STATUS[agent.status].label }}）
            </el-checkbox>
          </el-checkbox-group>
        </template>
        <p v-if="agentError" role="status">加载节点失败，请刷新后重试。</p>
        <p v-else-if="!selectableAgents.length" role="status">
          {{ loadingAgents ? '正在加载节点' : '暂无已登记节点，请先在系统管理中安装 Agent。' }}
        </p>
        <el-button native-type="submit" type="primary" :loading="starting" :disabled="!canStart">
          发起复测
        </el-button>
      </fieldset>
    </el-form>

    <div class="results-toolbar">
      <h2>{{ batchId ? '本次复测' : '近期复测结果' }}</h2>
      <div>
        <el-button v-if="batchId" :disabled="loadingResults || starting" @click="showRecent">
          查看近期结果
        </el-button>
        <el-button :loading="loadingResults" :disabled="starting" @click="refresh">刷新</el-button>
      </div>
    </div>
    <el-alert
      v-if="resultError"
      title="加载复测结果失败，请刷新后重试。"
      type="error"
      :closable="false"
      show-icon
    />
    <el-table v-loading="loadingResults && !results.length" :data="results" row-key="id" empty-text="暂无复测结果">
      <el-table-column label="地区 / 节点" min-width="170">
        <template #default="{ row }">
          <div>{{ row.region }}</div>
          <div class="secondary">{{ row.agent_name }} #{{ row.agent_id }}</div>
          <div v-if="row.domain !== domain.domain || row.port !== domain.port" class="secondary">
            {{ row.domain }}（端口 {{ row.port }}）
          </div>
        </template>
      </el-table-column>
      <el-table-column label="复测状态" min-width="160">
        <template #default="{ row }">
          <el-tag :type="CHECK_STATUS[row.status]?.type" effect="plain">
            {{ CHECK_STATUS[row.status]?.label || row.status }}
          </el-tag>
          <div v-if="row.error">{{ CHECK_ERROR[row.error] || row.error }}</div>
        </template>
      </el-table-column>
      <el-table-column label="证书有效期" min-width="210">
        <template #default="{ row }">
          <template v-if="row.cert_starts_at || row.cert_expires_at">
            <div>起始 {{ formatTime(row.cert_starts_at) }}</div>
            <div>到期 {{ formatTime(row.cert_expires_at) }}</div>
          </template>
          <template v-else>—</template>
        </template>
      </el-table-column>
      <el-table-column label="复测时间" min-width="210">
        <template #default="{ row }">
          <div>发起 {{ formatTime(row.created_at) }}</div>
          <div v-if="row.finished_at">完成 {{ formatTime(row.finished_at) }}</div>
          <div v-else>期限 {{ formatTime(row.deadline_at) }}</div>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Http } from '@/api/index.js'
import { AGENT_STATUS, CHECK_ERROR, CHECK_STATUS, formatTime } from '../agent-list/display.js'

const props = defineProps({
  domain: { type: Object, required: true },
})

const emit = defineEmits(['close'])
const agents = ref([])
const selectedIds = ref([])
const batchId = ref(null)
const results = ref([])
const loadingAgents = ref(false)
const loadingResults = ref(false)
const starting = ref(false)
const agentError = ref(false)
const resultError = ref(false)

const selectableAgents = computed(() => agents.value.filter(
  ({ status }) => status === 'online' || status === 'offline',
))
const canStart = computed(() => !agentError.value && !resultError.value && !loadingResults.value &&
  selectedIds.value.length > 0 && selectedIds.value.length <= 10)
const hasActiveChecks = computed(() => results.value.some(
  ({ status }) => status === 'queued' || status === 'running',
))

async function loadAgents() {
  if (loadingAgents.value) return
  loadingAgents.value = true
  try {
    const res = await Http.getAgentList()
    agentError.value = !res.ok
    if (res.ok) {
      agents.value = res.data
      const available = new Set(selectableAgents.value.map(({ id }) => id))
      selectedIds.value = selectedIds.value.filter((id) => available.has(id))
    }
  } finally {
    loadingAgents.value = false
  }
}

async function loadResults() {
  if (loadingResults.value || starting.value) return
  loadingResults.value = true
  try {
    const params = { domain_id: props.domain.id }
    if (batchId.value) params.batch_id = batchId.value
    const res = await Http.getAgentCheckResults(params)
    resultError.value = !res.ok
    if (res.ok) results.value = res.data
  } finally {
    loadingResults.value = false
  }
}

function refresh() {
  return Promise.all([loadAgents(), loadResults()])
}

function showRecent() {
  batchId.value = null
  results.value = []
  return loadResults()
}

async function startCheck() {
  if (!canStart.value || starting.value) return
  starting.value = true
  try {
    const res = await Http.startAgentDomainCheck({
      domain_id: props.domain.id,
      agent_ids: selectedIds.value,
    })
    if (res.ok) {
      batchId.value = res.data.batch_id
      results.value = res.data.results
      resultError.value = false
    }
  } finally {
    starting.value = false
  }
}

let pollTimer
onMounted(() => {
  refresh()
  pollTimer = setInterval(() => {
    if (!agentError.value) loadAgents()
    if (!resultError.value && hasActiveChecks.value) loadResults()
  }, 5000)
})
onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.target {
  margin-bottom: 16px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.agent-picker {
  min-width: 0;
}

.agent-picker legend {
  margin-bottom: 6px;
  font-weight: 600;
}

.agent-options {
  display: grid;
  max-height: 160px;
  overflow: auto;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  padding: 6px 12px;
  margin: 8px 0;
}

.agent-options :deep(.el-checkbox) {
  white-space: normal;
  height: auto;
  min-height: 32px;
  margin-right: 0;
}

.agent-options :deep(.el-checkbox__label) {
  overflow-wrap: anywhere;
}

.agent-picker > .el-button {
  margin-top: 8px;
}

.results-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  width: 100%;
  justify-content: space-between;
  margin: 20px 0 8px;
}

.results-toolbar h2 {
  font-size: 16px;
  font-weight: 600;
}

.secondary {
  color: var(--el-text-color-regular);
}
</style>
