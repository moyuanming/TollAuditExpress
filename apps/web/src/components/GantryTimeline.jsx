// 门架交易流水（gantry_records）：从 trip.gantry_records JSON 字符串解析并按时间顺序展示
import React from 'react'
import { formatTime } from './tripDetailUtils'
import Icon from './Icon'

export default function GantryTimeline({ records, count }) {
  let items = []
  if (records) {
    try {
      items = typeof records === 'string' ? JSON.parse(records) : records
    } catch (e) { items = [] }
  }

  if (items.length === 0) {
    return (
      <div className="detail-section">
        <div className="detail-section-title"><Icon name="git-branch" />门架交易流水</div>
        <div className="text-xs text-tertiary">
          暂无门架记录（{count || 0} 个门架未抓拍或未聚合）
        </div>
      </div>
    )
  }

  return (
    <div className="detail-section">
      <div className="detail-section-title">
        <Icon name="git-branch" />门架交易流水（{items.length} 个）
      </div>
      <div className="gt-track">
        {items.map((g, i) => (
          <div key={i} className="gt-item">
            <span className="gt-dot" />
            <div className="text-xs text-tertiary mb-1">
              {formatTime(g.occur_time)}
            </div>
            <div className="text-sm font-medium mb-1">
              {g.station_name || '未知门架'}
            </div>
            <div className="text-xs text-secondary">
              {g.vehicle_id || '?'} (色:{g.vehicle_color ?? '?'}) {g.vehicle_type != null ? `· 车型${g.vehicle_type}` : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
