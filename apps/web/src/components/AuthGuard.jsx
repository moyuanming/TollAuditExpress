import { useState, useEffect } from 'react'
import { useAuth } from './AuthContext'

export function AuthGuard({ children }) {
  const { isAuthenticated } = useAuth()
  const [authConfig, setAuthConfig] = useState({ authEnabled: true, loginUrl: '' })

  useEffect(() => {
    fetch('/api/oauth/config')
      .then(r => r.json())
      .then(d => setAuthConfig({ authEnabled: d.data?.authEnabled ?? true, loginUrl: d.data?.loginUrl || '' }))
      .catch(() => setAuthConfig({ authEnabled: true, loginUrl: '' }))
  }, [])

  if (!authConfig.authEnabled) {
    return children
  }

  if (!isAuthenticated) {
    if (authConfig.loginUrl) {
      window.location.replace(authConfig.loginUrl)
    }
    return null
  }

  return children
}
