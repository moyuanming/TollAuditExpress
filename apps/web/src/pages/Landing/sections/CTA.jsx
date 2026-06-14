import React, { useState } from 'react'
import { submitLead } from '../../../api/landing'
import './CTA.css'

const PHONE_RE = /^1[3-9]\d{9}$/
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

function validate(values) {
  const errors = {}
  if (!values.name.trim()) errors.name = '请填写姓名'
  if (!PHONE_RE.test(values.phone)) errors.phone = '请填写正确的手机号'
  if (!values.org.trim()) errors.org = '请填写单位名称'
  if (values.email && !EMAIL_RE.test(values.email)) errors.email = '邮箱格式不正确'
  if (values.message && values.message.length > 500) errors.message = '备注不超过 500 字'
  return errors
}

const EMPTY = { name: '', phone: '', org: '', email: '', message: '' }

export default function CTA() {
  const [values, setValues] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState('idle') // idle | submitting | success
  const [toast, setToast] = useState(null)

  const onChange = (e) => {
    const { name, value } = e.target
    setValues((v) => ({ ...v, [name]: value }))
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    const errs = validate(values)
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    setStatus('submitting')
    try {
      await submitLead(values)
      setStatus('success')
    } catch (err) {
      setStatus('idle')
      if (err.status === 422 && err.fieldErrors) {
        setErrors(err.fieldErrors)
      } else {
        setToast(err.message || '提交失败,请稍后重试')
        setTimeout(() => setToast(null), 4000)
      }
    }
  }

  return (
    <section className="cta" id="contact">
      <div className="cta-inner">
        <h2 className="cta-title">申请免费试用</h2>
        <p className="cta-sub">填写后我们 1 个工作日内联系您</p>

        {status === 'success' ? (
          <div className="cta-success">
            <div className="cta-success-icon">✓</div>
            <div className="cta-success-text">提交成功,我们会尽快联系您</div>
            <button
              type="button"
              className="cta-link"
              onClick={() => { setValues(EMPTY); setStatus('idle'); setErrors({}) }}
            >
              再次提交
            </button>
          </div>
        ) : (
          <form className="cta-form" onSubmit={onSubmit} noValidate>
            <label className="cta-field">
              <span>姓名 *</span>
              <input
                name="name" value={values.name} onChange={onChange}
                disabled={status === 'submitting'}
              />
              {errors.name && <em className="cta-err">{errors.name}</em>}
            </label>
            <label className="cta-field">
              <span>联系电话 *</span>
              <input
                name="phone" value={values.phone} onChange={onChange}
                inputMode="numeric" disabled={status === 'submitting'}
              />
              {errors.phone && <em className="cta-err">{errors.phone}</em>}
            </label>
            <label className="cta-field">
              <span>单位名称 *</span>
              <input
                name="org" value={values.org} onChange={onChange}
                disabled={status === 'submitting'}
              />
              {errors.org && <em className="cta-err">{errors.org}</em>}
            </label>
            <label className="cta-field">
              <span>邮箱</span>
              <input
                name="email" type="email" value={values.email} onChange={onChange}
                disabled={status === 'submitting'}
              />
              {errors.email && <em className="cta-err">{errors.email}</em>}
            </label>
            <label className="cta-field cta-field-full">
              <span>备注</span>
              <textarea
                name="message" value={values.message} onChange={onChange}
                rows={3} maxLength={500}
                disabled={status === 'submitting'}
              />
              {errors.message && <em className="cta-err">{errors.message}</em>}
            </label>
            <div className="cta-actions">
              <button
                type="submit"
                className="cta-submit"
                disabled={status === 'submitting'}
              >
                {status === 'submitting' ? '提交中...' : '提交申请'}
              </button>
            </div>
          </form>
        )}

        {toast && <div className="cta-toast">{toast}</div>}
      </div>
    </section>
  )
}
