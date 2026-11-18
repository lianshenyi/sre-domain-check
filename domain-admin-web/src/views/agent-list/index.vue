<template>
  <section class="app-container">
    <div class="agent-toolbar">
      <h1>Agent 节点</h1>
      <div>
        <el-button :loading="refreshing" @click="refresh">刷新状态</el-button>
        <el-button type="primary" :disabled="!isHttps || saving" @click="showCreate">
          登记节点
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="!isHttps"
      title="请通过 HTTPS 访问控制台后登记节点或签发安装码"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert v-if="listError" :title="listError" type="error" :closable="false" show-icon />

    <el-table v-loading="refreshing && !loaded" :data="agents" row-key="id" empty-text="暂无 Agent 节点">
      <el-table-column label="节点" min-width="150">
        <template #default="{ row }">
          <div class="node-name">{{ row.name }}</div>
          <div class="agent-hint">#{{ row.id }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="region" label="地区" min-width="120" show-overflow-tooltip />
      <el-table-column label="连通状态" width="110">
        <template #default="{ row }">
          <el-tag :type="AGENT_STATUS[row.status]?.type" effect="plain">
            {{ AGENT_STATUS[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近心跳" width="200">
        <template #default="{ row }">{{ formatTime(row.last_seen_at) }}</template>
      </el-table-column>
      <el-table-column label="安装码有效期" width="200">
        <template #default="{ row }">
          <span v-if="isExpired(row)">已过期</span>
          <span v-else>{{ formatTime(row.enrollment_expires_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button link type="primary" :disabled="!isHttps || saving" @click="renew(row)">
            重签安装码
          </el-button>
          <el-button
            v-if="row.status !== 'revoked'"
            link
            type="danger"
            :disabled="saving"
            @click="revoke(row)"
          >
            撤销
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="creating"
      title="登记节点"
      width="min(460px, calc(100vw - 32px))"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
    >
      <el-form label-position="top" @submit.prevent="create">
        <el-form-item label="节点名称" for="agent-name">
          <el-input id="agent-name" v-model="name" :disabled="saving" />
        </el-form-item>
        <el-form-item label="地区" for="agent-region">
          <el-input id="agent-region" v-model="region" :disabled="saving" />
        </el-form-item>
        <p class="agent-hint">名称和地区各限 1–64 个字符。</p>
        <div class="agent-actions">
          <el-button :disabled="saving" @click="creating = false">取消</el-button>
          <el-button native-type="submit" type="primary" :disabled="!validLabels" :loading="saving">
            登记并签发
          </el-button>
        </div>
      </el-form>
    </el-dialog>

    <el-dialog
      :model-value="!!enrollment"
      title="安装 Agent"
      width="min(680px, calc(100vw - 32px))"
      @update:model-value="enrollment = null"
    >
      <template v-if="enrollment">
        <p>{{ enrollment.agent.name }}（{{ enrollment.agent.region }}）</p>
        <h2>安装命令</h2>
        <pre class="agent-value">{{ enrollment.install_command }}</pre>
        <el-button @click="copyValue(enrollment.install_command, '安装命令')">复制安装命令</el-button>

        <h2>一次性安装码</h2>
        <template v-if="!enrollmentUnavailable">
          <p>在目标节点运行命令后，按提示输入安装码。关闭后可重签。</p>
          <p>有效期至 {{ formatTime(enrollment.agent.enrollment_expires_at) }}</p>
          <pre class="agent-value">{{ enrollment.enrollment_code }}</pre>
          <el-button @click="copyEnrollmentCode">复制安装码</el-button>
        </template>
        <p v-else role="status">{{ enrollmentUnavailable }}</p>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import copy from 'copy-to-clipboard'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Http } from '@/api/index.js'
import { AGENT_STATUS, formatTime } from './display.js'

const origin = window.location.origin
const isHttps = window.location.protocol === 'https:'
const agents = ref([])
const loaded = ref(false)
const refreshing = ref(false)
const listError = ref('')
const creating = ref(false)
const saving = ref(false)
const name = ref('')
const region = ref('')
const enrollment = ref(null)
const now = ref(Date.now())

let generation = 0
let clockTimer
let refreshTimer

function isExpired(agent, time = now.value) {
  return agent.enrollment_expires_at && Date.parse(agent.enrollment_expires_at) <= time
}

const validLabels = computed(() => [name.value, region.value].every((value) => {
  const length = [...value.trim()].length
  return length >= 1 && length <= 64
}))

const enrollmentUnavailable = computed(() => {
  const issued = enrollment.value?.agent
  if (!issued) return ''

  const current = agents.value.find((agent) => agent.id === issued.id)
  if (current && (current.status !== 'pending' ||
      current.enrollment_expires_at !== issued.enrollment_expires_at)) {
    return '此安装码已使用或失效。需要重新登记时请重签。'
  }
  return isExpired(issued) ? '安装码已过期，请关闭后重签。' : ''
})

async function refresh() {
  if (refreshing.value || saving.value) return

  refreshing.value = true
  const requestGeneration = generation
  try {
    const res = await Http.getAgentList()
    if (requestGeneration !== generation) return

    if (res.ok) {
      agents.value = res.data
      loaded.value = true
      listError.value = ''
    } else {
      listError.value = '加载节点状态失败，请刷新状态后重试。'
    }
  } finally {
    refreshing.value = false
  }
}

function showCreate() {
  name.value = ''
  region.value = ''
  creating.value = true
}

function updateAgent(agent) {
  agents.value = [...agents.value.filter(({ id }) => id !== agent.id), agent]
    .sort((left, right) => left.id - right.id)
}

async function mutate(request, handler) {
  if (saving.value) return
  saving.value = true
  generation += 1
  try {
    const res = await request()
    if (res.ok) handler(res.data)
  } finally {
    saving.value = false
  }
}

function showEnrollment(data) {
  updateAgent(data.agent)
  now.value = Date.now()
  enrollment.value = data
}

function create() {
  if (!isHttps || !validLabels.value) return

  return mutate(
    () => Http.createAgent({ name: name.value.trim(), region: region.value.trim(), origin }),
    (data) => {
      creating.value = false
      showEnrollment(data)
    },
  )
}

async function confirmAction(message, title, action) {
  try {
    await ElMessageBox.confirm(message, title, {
      type: 'warning',
      confirmButtonText: action,
      cancelButtonText: '取消',
    })
  } catch {
    return false
  }
  return true
}

async function renew(agent) {
  if (!isHttps || !await confirmAction(
    `重签后，${agent.name} 的原安装码、运行凭据及进行中的复测将失效。`,
    '重签安装码',
    '重签',
  )) return

  return mutate(
    () => Http.renewAgentEnrollment({ agent_id: agent.id, origin }),
    showEnrollment,
  )
}

async function revoke(agent) {
  if (!await confirmAction(
    `撤销后，${agent.name} 将停止领取任务，进行中的复测将取消。`,
    '撤销节点',
    '撤销',
  )) return

  return mutate(
    () => Http.revokeAgent({ agent_id: agent.id }),
    updateAgent,
  )
}

function copyValue(value, label) {
  if (copy(value)) {
    ElMessage.success(`已复制${label}`)
  } else {
    ElMessage.error('复制失败，请手动选中文本复制。')
  }
}

function copyEnrollmentCode() {
  now.value = Date.now()
  if (!enrollmentUnavailable.value && enrollment.value) {
    copyValue(enrollment.value.enrollment_code, '安装码')
  }
}

onMounted(() => {
  refresh()
  clockTimer = setInterval(() => { now.value = Date.now() }, 1000)
  refreshTimer = setInterval(() => {
    if (!listError.value) refresh()
  }, 5000)
})

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(refreshTimer)
  enrollment.value = null
})
</script>

<style scoped>
.agent-toolbar,
.agent-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.agent-toolbar h1 {
  font-size: 20px;
  font-weight: 600;
}

.agent-actions {
  justify-content: flex-end;
  margin: 16px 0 0;
}

.agent-hint {
  color: var(--el-text-color-regular);
}

.node-name {
  overflow-wrap: anywhere;
}

.el-alert {
  margin-bottom: 12px;
}

.el-dialog h2 {
  font-weight: 600;
  margin: 16px 0 6px;
}

.agent-value {
  padding: 10px 12px;
  margin: 8px 0;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
