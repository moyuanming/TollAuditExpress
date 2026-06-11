import { fetchJSON } from './audit'

function parseRuleExpr(rule) {
  if (!rule || typeof rule.rule_expr !== 'string') return rule
  try {
    return { ...rule, rule_expr: JSON.parse(rule.rule_expr) }
  } catch {
    return rule
  }
}

export const rulesApi = {
  async listRules(params = {}) {
    const filtered = {}
    if (params.fraud_type) filtered.fraud_type = params.fraud_type
    if (params.enabled !== undefined && params.enabled !== null && params.enabled !== '') {
      filtered.enabled = params.enabled
    }
    const qs = new URLSearchParams(filtered).toString()
    const data = await fetchJSON(`/api/audit/rules${qs ? `?${qs}` : ''}`)
    return { ...data, rules: (data.rules || []).map(parseRuleExpr) }
  },

  async getRule(id) {
    return parseRuleExpr(await fetchJSON(`/api/audit/rules/${id}`))
  },

  async createRule(data) {
    return parseRuleExpr(await fetchJSON('/api/audit/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }))
  },

  async updateRule(id, data) {
    return parseRuleExpr(await fetchJSON(`/api/audit/rules/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }))
  },

  async deleteRule(id) {
    return fetchJSON(`/api/audit/rules/${id}`, { method: 'DELETE' })
  },

  async toggleRule(id, enabled) {
    return fetchJSON(`/api/audit/rules/${id}/toggle?enabled=${enabled ? 1 : 0}`, {
      method: 'PATCH'
    })
  },

  async setDryRun(id, dryRun) {
    return fetchJSON(`/api/audit/rules/${id}/dry-run?dry_run=${dryRun ? 1 : 0}`, {
      method: 'PATCH'
    })
  }
}
