// 门架交易流水（gantry_records）：从 trip.gantry_records JSON 字符串解析并按时间顺序展示
import React from 'react'
import { formatTime } from './tripDetailUtils'

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
        <div className="detail-section-title">🛣️ 门架交易流水</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>
          暂无门架记录（{count || 0} 个门架未抓拍或未聚合）
        </div>
      </div>
    )
  }

  return (
    <div className="detail-section">
      <div className="detail-section-title">
        🛣️ 门架交易流水（{items.length} 个）
      </div>
      <div style={{
        position: 'relative',
        paddingLeft: 16,
        borderLeft: '2px solid var(--border-primary)',
        marginLeft: 8
      }}>
        {items.map((g, i) => (
          <div key={i} style={{
            position: 'relative',
            paddingLeft: 12,
            marginBottom: 12,
            paddingBottom: 12,
            borderBottom: i < items.length - 1 ? '1px dashed var(--border-primary)' : 'none'
          }}>
            <div style={{
              position: 'absolute',
              left: -22,
              top: 4,
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: 'var(--accent-blue)',
              border: '2px solid var(--bg-primary)'
            }} />
            <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginBottom: 4 }}>
              {formatTime(g.occur_time)}
            </div>
            <div style={{ fontSize: '0.8rem', fontWeight: 500, marginBottom: 4 }}>
              {g.station_name || '未知门架'}
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: 6 }}>
              {g.vehicle_id || '?'} (色:{g.vehicle_color ?? '?'}) {g.vehicle_type != null ? `· 车型${g.vehicle_type}` : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
