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
      token: { colorPrimary: '#0b7a58', colorInfo: '#0b7a58', borderRadius: 10, fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif' },
      components: { Layout: { siderBg: '#10231d', headerBg: '#f5f7f2' }, Menu: { darkItemBg: '#10231d', darkItemSelectedBg: '#1b604b' } }
    }}>
      <BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)

