import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import api from './api'
import type { User } from './types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('erp_token')
    if (!token) return setLoading(false)
    api.get('/auth/me/').then(({ data }) => setUser(data)).finally(() => setLoading(false))
  }, [])

  const login = async (username: string, password: string) => {
    const { data } = await api.post('/auth/login/', { username, password })
    localStorage.setItem('erp_token', data.token)
    setUser(data.user)
  }

  const logout = async () => {
    try { await api.post('/auth/logout/') } finally {
      localStorage.removeItem('erp_token')
      setUser(null)
    }
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

