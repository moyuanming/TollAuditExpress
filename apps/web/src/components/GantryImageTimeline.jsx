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
        <div className="detail-section-title">门架图片流水</div>
        <div className="text-sm text-tertiary">
          暂无抓拍图片记录
        </div>
      </div>
    )
  }

  return (
    <div className="detail-section">
      <div className="detail-section-title">
        门架图片流水（{items.length} 张）
      </div>
      <div className="gt-track gt-track-purple">
        {items.map((g, i) => (
          <div key={i} className="gt-item">
            <div className="gt-dot gt-dot-purple" />
            <div className="text-xs text-tertiary mb-1">
              {formatTime(g.occur_time)}
            </div>
            <div className="text-0p8 fw-500 mb-1">
              {g.station_name || '未知门架'}
            </div>
            <div className="text-xs text-secondary mb-1p5">
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
              <div className="text-xs text-tertiary">无抓拍图</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
