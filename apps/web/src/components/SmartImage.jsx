import { useState } from 'react'

function SmartImage({ imageUrl, alt = '', style, onLoaded }) {
  const [phase, setPhase] = useState('direct') // direct | proxy | error
  const [attempt, setAttempt] = useState(0)

  if (!imageUrl) {
    return (
      <div className="image-fallback-box" style={style}>
        <span style={{ fontSize: '1.5rem' }}>🖼️</span>
        <span>无图像</span>
      </div>
    )
  }

  const proxyUrl = `/api/audit/image-proxy?url=${encodeURIComponent(imageUrl)}${attempt ? `&_t=${Date.now()}` : ''}`
  const src = phase === 'direct' ? imageUrl : phase === 'proxy' ? proxyUrl : null

  const handleDirectError = () => {
    if (phase === 'direct') {
      setPhase('proxy')
    } else if (phase === 'proxy') {
      setPhase('error')
    }
  }

  const handleRetry = (e) => {
    e.stopPropagation()
    setAttempt(a => a + 1)
    setPhase('direct')
  }

  if (phase === 'error') {
    return (
      <div className="smart-image-wrap" style={style}>
        <div className="image-error-box">
          <span style={{ fontSize: '1.5rem' }}>⚠️</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>加载失败</span>
          <button
            type="button"
            className="btn btn-link btn-sm"
            style={{ fontSize: '0.7rem', padding: 0, marginTop: 4 }}
            onClick={handleRetry}
          >
            🔄 重试
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="smart-image-wrap" style={style}>
      <img
        src={src}
        alt={alt}
        className="smart-image"
        onLoad={() => onLoaded && onLoaded()}
        onError={handleDirectError}
      />
    </div>
  )
}

export default SmartImage
