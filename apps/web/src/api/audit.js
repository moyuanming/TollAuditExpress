const API_BASE = '/api/audit'
const TASK_BASE = '/api'

const errorListeners = []
export function onApiError(listener) { errorListeners.push(listener) }

export async function fetchJSON(url, options = {}) {
  const token = localStorage.getItem('auth_token')
  const headers = { ...options.headers }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const apiKey = localStorage.getItem('api_key')
  if (apiKey && !token) {
    headers['X-API-Key'] = apiKey
  }
  const res = await fetch(url, { ...options, headers })
  const newToken = res.headers.get('X-New-Access-Token')
  if (newToken) {
    localStorage.setItem('auth_token', newToken)
  }
  if (!res.ok) {
    if (res.status === 401 && localStorage.getItem('auth_token')) {
      localStorage.removeItem('auth_token')
      window.dispatchEvent(new CustomEvent('auth:invalid'))
    }
    let errorMessage = `HTTP ${res.status}`
    try {
      const errorData = await res.json()
      const detail = errorData && errorData.detail
      if (typeof detail === 'string') {
        errorMessage = detail
      } else if (detail && typeof detail === 'object') {
        const code = detail.error || 'unknown_error'
        const sub = detail.field || detail.detail
        errorMessage = sub ? `${code}: ${sub}` : code
      }
    } catch {
      // 响应体不是 JSON，忽略
    }
    const error = new Error(errorMessage)
    error.status = res.status
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

  // 行程完整详情（含门架图片流水 + 关联稽核结果）
  async getTripFull(passid) {
    return fetchJSON(`${API_BASE}/trip/${passid}/full`)
  },

  // Doris 原始数据：任意车辆通行列表（无检测后字段）
  async getRawVehicles(params = {}) {
    const qs = new URLSearchParams(params).toString()
    return fetchJSON(`${API_BASE}/doris/vehicles?${qs}`)
  },

  // Doris 原始数据：单个行程详情（无 audit_results）
  async getRawVehicleFull(passid) {
    return fetchJSON(`${API_BASE}/doris/vehicle/${passid}/full`)
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
    const qs = new URLSearchParams()
    if (params.fraud_types && params.fraud_types.length > 0) {
      params.fraud_types.forEach(t => qs.append('fraud_types', t))
    } else if (params.fraud_type) {
      qs.set('fraud_types', params.fraud_type)
    }
    if (params.process_status) qs.set('process_status', params.process_status)
    if (params.llm_result) qs.set('llm_result', params.llm_result)
    if (params.limit) qs.set('limit', params.limit)
    if (params.offset) qs.set('offset', params.offset)
    const query = qs.toString()
    return fetchJSON(`${API_BASE}/suspects${query ? `?${query}` : ''}`)
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

  // 手动对单条可疑记录触发 LLM 二次判定（覆盖已有 verdict）
  async llmVerifySuspect(id) {
    return fetchJSON(`${API_BASE}/suspect/${id}/llm-verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    })
  },

  // 检测客车套用货车 OBU（图片识别为货车 + LLM 复核）
  async detectPassengerOBU(passid) {
    return fetchJSON(`${API_BASE}/detect/passenger-obu`, {
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
  },

  // 手动调用 MaaS 双图比对出入口车牌特写
  async compareVehiclesMaaS(passid) {
    return fetchJSON(`${API_BASE}/detect/entry-exit/llm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passid })
    })
  },

  // 客车 OBU 监测 — 顶部概览 (累计/异常/待处理/已确认 + 最近 30 天趋势)
  async getPassengerObuOverview() {
    return fetchJSON(`${API_BASE}/passenger-obu/overview`)
  },

  // 客车 OBU 监测 — 按日统计列表
  async getPassengerObuDailyStats(params = {}) {
    const qs = new URLSearchParams(params).toString()
    return fetchJSON(`${API_BASE}/passenger-obu/stats/daily${qs ? `?${qs}` : ''}`)
  },

  // 客车 OBU 监测 — 异常记录列表
  async getPassengerObuAnomalies(params = {}) {
    const qs = new URLSearchParams(params).toString()
    return fetchJSON(`${API_BASE}/passenger-obu/anomalies${qs ? `?${qs}` : ''}`)
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
  },

  async getTaskExecutionDetail(taskId, executionId) {
    return fetchJSON(`${TASK_BASE}/tasks/${taskId}/executions/${executionId}`)
  }
}
