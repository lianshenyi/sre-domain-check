export const AGENT_STATUS = {
  pending: { label: '待登记', type: 'warning' },
  online: { label: '在线', type: 'success' },
  offline: { label: '离线', type: 'danger' },
  revoked: { label: '已撤销', type: 'info' },
}

export const CHECK_STATUS = {
  queued: { label: '排队中', type: 'info' },
  running: { label: '执行中', type: 'warning' },
  succeeded: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  expired: { label: '已超时', type: 'warning' },
  canceled: { label: '已取消', type: 'info' },
}

export const CHECK_ERROR = {
  deadline_exceeded: '超过任务期限',
  credential_revoked: '节点凭据已失效',
  domain_changed: '域名记录已变更',
  invalid_certificate: '证书无法解析',
  name_mismatch: '证书名称不匹配',
  probe_failed: '节点证书采集失败',
}

const dateFormat = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

export function formatTime(value) {
  return value ? dateFormat.format(new Date(value)) : '—'
}
