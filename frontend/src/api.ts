import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('erp_token')
  if (token) config.headers.Authorization = `Token ${token}`
  config.headers['X-Request-ID'] = crypto.randomUUID()
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('erp_token')
      if (!location.pathname.includes('/login')) location.assign('/login')
    }
    const payload = error.response?.data
    error.userMessage = payload?.error?.message?.detail || payload?.detail || '请求失败，请稍后重试'
    return Promise.reject(error)
  },
)

export default api

