// 行程详情面板：被 SuspectList / VehicleQuery 共用
// props:
//   trip: TripDetailResponse —— 含 gantry_records, gantry_image_records, audit_results[], passid, ...
//   actions: ReactNode —— 可选操作区（SuspectList 注入"稽核判定"按钮；VehicleQuery 注入"在可疑记录中处理"链接）
//   deepLink: ReactNode —— 可选跳转链接（VehicleQuery 注入"→ 查看可疑记录"链接）
import React, { useState } from 'react'
import GantryTimeline from './GantryTimeline'
import GantryImageTimeline from './GantryImageTimeline'
import { DecisionTable, ImageBox, JsonView, formatTime } from './tripDetailUtils'
import { auditApi } from '../api/audit'
import Icon from './Icon'

const LLM_ERROR_MAP = {
  maas_unavailable: {
    message: 'MaaS 多模态服务暂不可用',
    hint: '可能网络抖动或 MaaS 配额/鉴权异常，稍后重试或联系管理员',
  },
  parse_error: {
    message: 'MaaS 响应解析失败',
    hint: '模型输出格式异常，请重试或换一条行程',
  },
  image_url_missing: {
    message: '缺少出入口车牌图片',
    hint: 'Doris 中该行程未关联到车牌特写图，跳过 LLM 判定',
  },
  image_download_failed: {
    message: '图片下载失败',
    hint: '车道服务器返回 4xx/5xx，请检查图片 URL 是否仍有效',
  },
  trip_not_found: {
    message: '未找到该行程',
    hint: 'Doris 中无此 passid 的聚合记录',
  },
}

const VEHICLE_TYPE_LABEL = { 1: '客车', 2: '货车', 14: '货车', 15: '货车', 16: '货车' }
function vehicleTypeLabel(t) {
  return VEHICLE_TYPE_LABEL[t] || (t == null ? '—' : String(t))
}

function mapLlmError(e) {
  if (!e) return { message: '调用失败', hint: '' }
  if (e.status === 401) {
    return { message: 'API Key 无效或缺失', hint: '检查 localStorage.api_key 或后端 API_KEY 配置' }
  }
  if (e.status === 422) {
    return { message: '请求参数不合法', hint: 'passid 不能为空' }
  }
  if (e.status === 502) {
    return { message: 'MaaS 多模态服务暂不可用', hint: '可能网络抖动或 MaaS 配额/鉴权异常，稍后重试或联系管理员' }
  }
  const raw = (e.message || '').trim()
  const m = raw.match(/^([a-z_]+):\s*(.*)$/i)
  if (m) {
    const code = m[1]
    const sub = m[2]
    const mapped = LLM_ERROR_MAP[code]
    if (mapped) return { message: mapped.message, hint: mapped.hint }
    return { message: `${code}${sub ? '：' + sub : ''}`, hint: '后端返回未映射错误码' }
  }
  return { message: raw || '调用失败', hint: '' }
}

function LlmCompareSection({ passid, hasEntry, hasExit, initialVerdict, onVerified }) {
  const [state, setState] = useState({ loading: false, result: null, error: null })

  const disabled = !passid || !hasEntry || !hasExit
  const hasVerdict = initialVerdict && initialVerdict.llm_checked_at != null

  async function handleClick() {
    if (disabled) return
    setState({ loading: true, result: null, error: null })
    try {
      // 有 suspect id（如可疑记录）走持久化路由；否则（如原始车辆详情）按 passid 临时调
      let raw
      if (initialVerdict?.id) {
        raw = await auditApi.llmVerifySuspect(initialVerdict.id)
      } else {
        raw = await auditApi.compareVehiclesMaaS(passid)
        if (raw && raw.error) throw new Error(JSON.stringify(raw))
        if (raw) {
          raw = {
            llm_is_same_vehicle: raw.is_same_vehicle ? 1 : 0,
            llm_confidence: raw.confidence,
            llm_reason: raw.reason,
            llm_model: raw.model,
          }
        }
      }
      setState({ loading: false, result: raw, error: null })
      if (onVerified) onVerified(raw)
    } catch (e) {
      setState({ loading: false, result: null, error: mapLlmError(e) })
    }
  }

  let hint = null
  if (!hasEntry || !hasExit) {
    hint = '缺少出入口车牌图片，无法比对'
  } else if (!passid) {
    hint = '缺少 passid'
  }

  // 用最新结果优先，其次是传入的 initialVerdict
  const verdict = state.result
    ? {
        is_same_vehicle: state.result.llm_is_same_vehicle === 1,
        confidence: state.result.llm_confidence,
        reason: state.result.llm_reason,
        model: state.result.llm_model,
        elapsed_ms: null,
      }
    : hasVerdict
      ? {
          is_same_vehicle: initialVerdict.llm_is_same_vehicle === 1,
          confidence: initialVerdict.llm_confidence,
          reason: initialVerdict.llm_reason,
          model: initialVerdict.llm_model,
          elapsed_ms: null,
        }
      : null

  return (
    <div className="detail-section">
      <div className="detail-section-title"><Icon name="sparkles" />LLM 判定同一车辆</div>
      <button
        className="btn btn-primary"
        onClick={handleClick}
        disabled={disabled || state.loading}
      >
        {state.loading ? <><Icon name="loader" />分析中…</> : hasVerdict ? <><Icon name="refresh" />重新检测</> : <><Icon name="sparkles" />调用 MaaS 比对出入口车牌</>}
      </button>
      {hint && !verdict && !state.error && (
        <div className="alert alert-warning mt-2">
          <span>{hint}</span>
        </div>
      )}
      {state.error && (
        <div className="alert alert-warning col items-stretch mt-2">
          <span><Icon name="x-circle" />{state.error.message}</span>
          {state.error.hint && (
            <span className="mt-1 text-0p8 opacity-85">
              {state.error.hint}
            </span>
          )}
          {!disabled && (
            <button
              className="btn btn-secondary mt-2 align-self-start"
              onClick={handleClick}
              disabled={state.loading}
            >
              {state.loading ? '重试中…' : '重试'}
            </button>
          )}
        </div>
      )}
      {verdict && (
        <div
          className={`alert col items-stretch mt-2 ${verdict.is_same_vehicle ? 'alert-success' : 'alert-warning'}`}
        >
          <div className="text-0p95 fw-700">
            {verdict.is_same_vehicle ? <><Icon name="check" />判定为同一车辆</> : <><Icon name="x-circle" />判定为不同车辆</>}
            <span className="ml-2 text-secondary text-0p8">
              置信度 {((verdict.confidence || 0) * 100).toFixed(0)}%
            </span>
          </div>
          {verdict.reason && (
            <div className="mt-1 text-0p85">
              依据：{verdict.reason}
            </div>
          )}
          <div className="mt-1 text-xs text-tertiary">
            模型 {verdict.model || '—'}
            {verdict.elapsed_ms != null && ` · 用时 ${verdict.elapsed_ms}ms`}
          </div>
        </div>
      )}
    </div>
  )
}

export default function VehicleTripDetail({ trip, actions, deepLink }) {
  // 缺入口数据时(如新疆昭苏主线站等内网不可达的车道图片),不渲染入口 ImageBox
  // 避免 SmartImage 通过 image-proxy 请求不可达上游导致详情页"卡住"
  const hasEntry = !!trip.entry_vehicle_id
  return (
    <>
      {/* 决策依据：仅当存在 audit_results 时展示（按 fraud_type 逐个） */}
      {trip.audit_results && trip.audit_results.length > 0 && (
        <div className="detail-section">
          <div className="detail-section-title"><Icon name="target" />决策依据</div>
          {trip.audit_results.map((r, i) => (
            <div key={i} className="mb-3">
              <div className="text-xs text-tertiary mb-1">
                {r.fraud_type === 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A' ? <><Icon name="route" size="sm" /> 客车套用货车OBU</> : r.fraud_type === 'TRUCK_USES_PASSENGER_OBU' ? <><Icon name="bus" size="sm" /> 货车套用OBU</> : <><Icon name="route" size="sm" /> 出入口不一致</>}
                {' · 风险 '}
                {r.risk_score != null ? r.risk_score.toFixed(2) : '—'}
              </div>
              <DecisionTable suspect={r} />
            </div>
          ))}
          {deepLink}
        </div>
      )}

      {/* 图像对比 */}
      {(trip.entry_image_license || trip.exit_image_license) && (
        <div className="detail-section">
          <div className="detail-section-title"><Icon name="camera" />图像对比</div>

          <div className="detail-subsection-title">车牌图像</div>
          <div className="image-compare">
            {hasEntry && (
              <ImageBox
                label="入口"
                imageUrl={trip.entry_image_license}
                status={trip.entry_image_license ? 'success' : 'pending'}
                badge={trip.entry_image_license ? null : '无图像'}
              />
            )}
            <ImageBox
              label="出口"
              imageUrl={trip.exit_image_license}
              status={trip.exit_image_license ? 'success' : 'pending'}
              badge={trip.exit_image_license ? null : '无图像'}
            />
          </div>

          {(trip.entry_image_trans || trip.exit_image_trans) && (
            <>
              <div className="detail-subsection-title mt-3">车体/侧面图像</div>
              <div className="image-compare">
                {hasEntry && (
                  <ImageBox
                    label="入口"
                    imageUrl={trip.entry_image_trans}
                    status={trip.entry_image_trans ? 'success' : 'pending'}
                  />
                )}
                <ImageBox
                  label="出口"
                  imageUrl={trip.exit_image_trans}
                  status={trip.exit_image_trans ? 'success' : 'pending'}
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* 门架交易流水 */}
      <GantryTimeline records={trip.gantry_records} count={trip.gantry_count} />
      {/* 门架图片流水 */}
      <GantryImageTimeline records={trip.gantry_image_records} />

      {/* 基础信息 */}
      <div className="detail-section">
        <div className="detail-section-title"><Icon name="info" />基础信息</div>
        <div className="detail-grid">
          <div className="detail-item">
            <span className="detail-label">入口站</span>
            <span className="detail-value">{trip.entry_station_name || '—'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">出口站</span>
            <span className="detail-value">{trip.exit_station_name || '—'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">入口车型</span>
            <span className="detail-value">{vehicleTypeLabel(trip.entry_vehicle_type)}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">出口车型</span>
            <span className="detail-value">{vehicleTypeLabel(trip.exit_vehicle_type)}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">入口时间</span>
            <span className="detail-value mono">{formatTime(trip.entry_time)}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">出口时间</span>
            <span className="detail-value mono">{formatTime(trip.exit_time)}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">入口 OBU</span>
            <span className="detail-value mono">{trip.entry_obu_id || '—'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">出口 OBU</span>
            <span className="detail-value mono">{trip.exit_obu_id || '—'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">入口车道</span>
            <span className="detail-value mono">{trip.entry_lane_id || '—'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">出口车道</span>
            <span className="detail-value mono">{trip.exit_lane_id || '—'}</span>
          </div>
        </div>
      </div>

      {/* AI 检测原始数据：每个 audit_result 一个 JsonView */}
      {trip.audit_results && trip.audit_results.length > 0 && (
        <div className="detail-section">
          <div className="detail-section-title"><Icon name="sparkles" />AI 检测原始数据</div>
          {trip.audit_results.map((r, i) => (
            <div key={i} className="mb-3">
              <div className="text-xs text-tertiary mb-1">
                {r.fraud_type}
              </div>
              <JsonView data={r.details} />
            </div>
          ))}
        </div>
      )}

      {/* LLM 双图比对：手动调用 MaaS 比对出入口车牌特写 */}
      <LlmCompareSection
        passid={trip.passid}
        hasEntry={!!trip.entry_image_license}
        hasExit={!!trip.exit_image_license}
        initialVerdict={trip}
      />

      {/* 操作区：SuspectList 传"稽核判定"；VehicleQuery 不传 */}
      {actions}
    </>
  )
}
