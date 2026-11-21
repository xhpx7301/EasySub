import axios from 'axios'

const api = axios.create({ baseURL: '/' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing = null
// 登录 / 注册 / 找回密码等接口的 401 属于业务响应（如密码错、需要 2FA 验证码），
// 不能当成登录过期去刷新令牌或跳转 /login，否则错误提示和 2FA 输入框会随刷新消失。
const AUTH_FLOW = /\/api\/auth\/(login|register|refresh|forgot|reset|verify)/
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry && !AUTH_FLOW.test(original.url || '')) {
      original._retry = true
      const rt = localStorage.getItem('refresh_token')
      if (rt) {
        try {
          if (!refreshing) {
            refreshing = axios.post('/api/auth/refresh', { refresh_token: rt })
          }
          const { data } = await refreshing
          refreshing = null
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch (e) {
          refreshing = null
          localStorage.clear()
          window.location.href = '/login'
        }
      } else {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
