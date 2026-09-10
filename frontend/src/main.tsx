import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './auth'
import App from './App'
import './styles.css'

dayjs.locale('zh-cn')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{
      token: { colorPrimary: '#6758e8', colorInfo: '#18a999', colorSuccess: '#18a999', borderRadius: 12, fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif' },
      components: { Layout: { siderBg: '#0b1020', headerBg: '#f6f7fb' }, Menu: { darkItemBg: '#0b1020', darkItemSelectedBg: '#302968', darkItemHoverBg: '#171d34' }, Button: { primaryShadow: '0 8px 24px rgba(103,88,232,.24)' } }
    }}>
      <BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)
