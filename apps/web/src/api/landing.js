/**
 * 营销落地页 API client — 表单提交。
 * 错误对象带 status 字段,方便 UI 判断 422 / 429 / 5xx。
 */
export async function submitLead(payload) {
  const res = await fetch('/api/landing/leads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (res.status === 429) {
    const err = new Error('提交过于频繁,请稍后再试')
    err.status = 429
    throw err
  }
  if (res.status === 422) {
    const data = await res.json().catch(() => ({}))
    const err = new Error('表单校验失败')
    err.status = 422
    err.fieldErrors = parseFieldErrors(data)
    throw err
  }
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

/**
 * Pydantic 422 响应通常是:
 *   { "detail": [ { "loc": ["body","phone"], "msg": "...", "type": "..." } ] }
 * 转换为 { phone: "手机号格式不正确" }。
 */
function parseFieldErrors(data) {
  const out = {}
  const detail = data && data.detail
  if (Array.isArray(detail)) {
    for (const item of detail) {
      const loc = item.loc || []
      const field = loc[loc.length - 1]
      if (field) out[field] = item.msg
    }
  }
  return out
}