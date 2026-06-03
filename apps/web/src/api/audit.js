const API_BASE = '/api/audit'
const TASK_BASE = '/api'

const errorListeners = []
export function onApiError(listener) { errorListeners.push(listener) }

async function fetchJSON(url, options = {}) {
  const headers = {
    ...options.headers,
    'X-API-Key': localStorage.getItem('api_key') || ''
  }
  const res = await fetch(url, { ...options, headers })
  if (!res.ok) {
    const error = new Error(`HTTP ${res.status}`)
    errorListeners.forEach(l => l(error))
    throw error
  }
  return res.json()
}

export const auditApi = {
  // 统计概览
  async getStats() {
    return fetchJSON(`${API_BASE}/stats/overview`)
  },

  // 行程列表
  async getTrips(params = {}) {
    const qs = new URLSearchParams(params).toString()
    return fetchJSON(`${API_BASE}/trips?${qs}`)
  },

  // 行程详情
  async getTrip(passid) {
    return fetchJSON(`${API_BASE}/trip/${passid}`)
  },

  // 启动聚合任务
  async aggregateTrips(data = {}) {
    return fetchJSON(`${API_BASE}/trips/aggregate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
  },

  // 获取聚合任务状态
  async getAggregationStatus(taskId) {
    return fetchJSON(`${API_BASE}/trips/aggregate/${taskId}`)
  },

  // 可疑记录列表
  async getSuspects(params = {}) {
    const filtered = {}
    if (params.fraud_type) filtered.fraud_type = params.fraud_type
    if (params.process_status) filtered.process_status = params.process_status
    if (params.limit) filtered.limit = params.limit
    if (params.offset) filtered.offset = params.offset
    const qs = new URLSearchParams(filtered).toString()
    return fetchJSON(`${API_BASE}/suspects?${qs}`)
  },

  // 可疑记录详情
  async getSuspect(id) {
    return fetchJSON(`${API_BASE}/suspect/${id}`)
  },

  // 处理可疑记录
  async processSuspect(id, data) {
    return fetchJSON(`${API_BASE}/suspect/${id}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
  },

  // 检测货车套用OBU
  async detectTruckOBU(passid) {
    return fetchJSON(`${API_BASE}/detect/truck-obu`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passid })
    })
  },

  // 检测出入口不一致
  async detectEntryExit(passid) {
    return fetchJSON(`${API_BASE}/detect/entry-exit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passid })
    })
  }
}

export const taskApi = {
  async getTasks() {
    return fetchJSON(`${TASK_BASE}/tasks`)
  },

  async createTask(data) {
    return fetchJSON(`${TASK_BASE}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
  },

  async getTask(id) {
    return fetchJSON(`${TASK_BASE}/tasks/${id}`)
  },

  async updateTask(id, data) {
    return fetchJSON(`${TASK_BASE}/tasks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
  },

  async deleteTask(id) {
    return fetchJSON(`${TASK_BASE}/tasks/${id}`, {
      method: 'DELETE'
    })
  },

  async executeTask(id) {
    return fetchJSON(`${TASK_BASE}/tasks/${id}/execute`, {
      method: 'POST'
    })
  },

  async getTaskExecutions(id, limit = 50) {
    return fetchJSON(`${TASK_BASE}/tasks/${id}/executions?limit=${limit}`)
  }
}
