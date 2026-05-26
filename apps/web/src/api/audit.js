const API_BASE = '/api/audit'

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
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

  // 可疑记录列表
  async getSuspects(params = {}) {
    const qs = new URLSearchParams(params).toString()
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
