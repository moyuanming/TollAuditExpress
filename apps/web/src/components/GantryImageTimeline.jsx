// 门架抓拍图片流水（gantry_image_records）：从 JSON 字符串解析并按时间顺序展示图片
import React from 'react'
import SmartImage from './SmartImage'
import { formatTime } from './tripDetailUtils'

export default function GantryImageTimeline({ records }) {
  let items = []
  if (records) {
    try {
      items = typeof records === 'string' ? JSON.parse(records) : records
    } catch (e) { items = [] }
  }

  if (items.length === 0) {
    return (
      <div className="detail-section">
        <div className="detail-section-title">📸 门架图片流水</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>
          暂无抓拍图片记录
        </div>
      </div>
    )
  }

  return (
    <div className="detail-section">
      <div className="detail-section-title">
        📸 门架图片流水（{items.length} 张）
      </div>
      <div style={{
        position: 'relative',
        paddingLeft: 16,
        borderLeft: '2px solid var(--accent-purple)',
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
              background: 'var(--accent-purple)',
              border: '2px solid var(--bg-primary)'
            }} />
            <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginBottom: 4 }}>
              {formatTime(g.occur_time)}
            </div>
            <div style={{ fontSize: '0.8rem', fontWeight: 500, marginBottom: 4 }}>
              {g.station_name || '未知门架'}
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: 6 }}>
              {g.vehicle_id || '?'} (色:{g.vehicle_color ?? '?'})
            </div>
            {g.image_url ? (
              <SmartImage
                imageUrl={g.image_url}
                alt={g.station_name || `gantry image ${i}`}
                style={{
                  width: '100%',
                  maxWidth: 240,
                  aspectRatio: '4/3',
                  border: '1px solid var(--border-primary)',
                  background: 'var(--bg-tertiary)'
                }}
              />
            ) : (
              <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>无抓拍图</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
