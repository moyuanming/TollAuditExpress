import { createContext, useContext, useState, useCallback, useEffect } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('auth_token'))

  const isAuthenticated = !!token

  const login = useCallback((newToken) => {
    localStorage.setItem('auth_token', newToken)
    setToken(newToken)
  }, [])

  const logout = useCallback(async () => {
    if (token) {
      try {
        await fetch('/api/oauth/logout', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        })
      } catch { /* ignore */ }
    }
    localStorage.removeItem('auth_token')
    setToken(null)
  }, [token])

  useEffect(() => {
    const handler = () => setToken(null)
    window.addEventListener('auth:invalid', handler)
    return () => window.removeEventListener('auth:invalid', handler)
  }, [])

  return (
    <AuthContext.Provider value={{ token, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
