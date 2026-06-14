/**
 * CTA 表单测试 — 6 个用例覆盖:
 *   1. 空提交触发行内错误 (name / phone / org)
 *   2. 错误手机号格式阻止提交
 *   3. 合法提交 → 成功视图 + submitLead payload 校验
 *   4. 422 → 行内字段错误
 *   5. 5xx → toast 提示
 *   6. submitting 状态: 按钮文案切换 + disabled
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock the API client used by CTA.jsx.
// CTA.jsx imports:  import { submitLead } from '../../../api/landing'
// tests/web/ → apps/web/src/ → ../api/landing
vi.mock('../../apps/web/src/api/landing.js', () => ({
  submitLead: vi.fn(),
}))

import { submitLead } from '../../apps/web/src/api/landing.js'
import CTA from '../../apps/web/src/pages/Landing/sections/CTA.jsx'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CTA form', () => {
  it('空提交显示 name / phone / org 三个行内错误', async () => {
    const user = userEvent.setup()
    render(<CTA />)

    // 点击提交按钮,所有必填字段都为空
    await user.click(screen.getByRole('button', { name: '提交申请' }))

    // 三条行内错误都应出现
    expect(screen.getByText('请填写姓名')).toBeInTheDocument()
    expect(screen.getByText('请填写正确的手机号')).toBeInTheDocument()
    expect(screen.getByText('请填写单位名称')).toBeInTheDocument()

    // 不应调用 API
    expect(submitLead).not.toHaveBeenCalled()
  })

  it('非法手机号格式阻止提交', async () => {
    const user = userEvent.setup()
    render(<CTA />)

    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '1380013800') // 少一位
    await user.type(screen.getByLabelText('单位名称 *'), '测试公司')
    await user.click(screen.getByRole('button', { name: '提交申请' }))

    expect(screen.getByText('请填写正确的手机号')).toBeInTheDocument()
    expect(submitLead).not.toHaveBeenCalled()
  })

  it('合法提交: 显示成功视图 + submitLead payload 正确', async () => {
    const user = userEvent.setup()
    submitLead.mockResolvedValueOnce({ ok: true })

    render(<CTA />)

    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '13800138000')
    await user.type(screen.getByLabelText('单位名称 *'), '测试公司')
    // email / message 留空

    await user.click(screen.getByRole('button', { name: '提交申请' }))

    // 成功视图
    await waitFor(() => {
      expect(screen.getByText('提交成功,我们会尽快联系您')).toBeInTheDocument()
    })

    // payload 校验
    expect(submitLead).toHaveBeenCalledTimes(1)
    expect(submitLead).toHaveBeenCalledWith({
      name: '张三',
      phone: '13800138000',
      org: '测试公司',
      email: '',
      message: '',
    })
  })

  it('422 错误: 显示行内字段错误 (取自 err.fieldErrors)', async () => {
    const user = userEvent.setup()
    const apiErr = new Error('表单校验失败')
    apiErr.status = 422
    apiErr.fieldErrors = { phone: '手机号格式不正确' }
    submitLead.mockRejectedValueOnce(apiErr)

    render(<CTA />)

    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '13800138000')
    await user.type(screen.getByLabelText('单位名称 *'), '测试公司')
    await user.click(screen.getByRole('button', { name: '提交申请' }))

    // 行内错误:来自 API 的字段级 message
    await waitFor(() => {
      expect(screen.getByText('手机号格式不正确')).toBeInTheDocument()
    })

    // 不应显示 toast (因为 422 走的是行内错误分支)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    // 表单应回到 idle 状态 — 按钮恢复可点
    expect(screen.getByRole('button', { name: '提交申请' })).toBeEnabled()
  })

  it('5xx 错误: 显示 toast 错误信息', async () => {
    const user = userEvent.setup()
    const apiErr = new Error('HTTP 500')
    apiErr.status = 500
    submitLead.mockRejectedValueOnce(apiErr)

    render(<CTA />)

    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '13800138000')
    await user.type(screen.getByLabelText('单位名称 *'), '测试公司')
    await user.click(screen.getByRole('button', { name: '提交申请' }))

    // toast 出现,文案即 err.message
    await waitFor(() => {
      expect(screen.getByText('HTTP 500')).toBeInTheDocument()
    })

    // 不应进入成功视图
    expect(screen.queryByText('提交成功,我们会尽快联系您')).not.toBeInTheDocument()
  })

  it('submitting 状态: 按钮文案切换为"提交中..."且 disabled', async () => {
    const user = userEvent.setup()
    // 让 submitLead 挂起,这样我们能观察到中间态
    let resolveSubmit
    submitLead.mockImplementationOnce(
      () => new Promise((resolve) => { resolveSubmit = resolve })
    )

    render(<CTA />)

    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '13800138000')
    await user.type(screen.getByLabelText('单位名称 *'), '测试公司')
    await user.click(screen.getByRole('button', { name: '提交申请' }))

    // 中间态:按钮文案变化 + disabled
    const submitBtn = await screen.findByRole('button', { name: '提交中...' })
    expect(submitBtn).toBeDisabled()

    // 解析 promise,让组件进入 success
    resolveSubmit({ ok: true })
    await waitFor(() => {
      expect(screen.getByText('提交成功,我们会尽快联系您')).toBeInTheDocument()
    })
  })
})