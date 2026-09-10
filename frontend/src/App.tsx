import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Badge, Button, Dropdown, Layout, Menu, Spin, type MenuProps } from 'antd'
import {
  ApiOutlined, BarChartOutlined, DatabaseOutlined, DollarOutlined, HomeOutlined, ImportOutlined,
  LogoutOutlined, NodeIndexOutlined, ProductOutlined, SafetyCertificateOutlined, ShopOutlined, ShoppingCartOutlined,
  SwapOutlined, TeamOutlined, TruckOutlined, UserOutlined,
} from '@ant-design/icons'
import { useAuth } from './auth'
const LoginPage = lazy(() => import('./pages/LoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const ProductsPage = lazy(() => import('./pages/ProductsPage'))
const OrdersPage = lazy(() => import('./pages/OrdersPage'))
const InventoryPage = lazy(() => import('./pages/InventoryPage'))
const ProcurementPage = lazy(() => import('./pages/ProcurementPage'))
const ReturnsPage = lazy(() => import('./pages/ReturnsPage'))
const FinancePage = lazy(() => import('./pages/FinancePage'))
const IntegrationsPage = lazy(() => import('./pages/IntegrationsPage'))
const ImportsPage = lazy(() => import('./pages/ImportsPage'))
const AdministrationPage = lazy(() => import('./pages/AdministrationPage'))
const WorkflowPage = lazy(() => import('./pages/WorkflowPage'))

const { Header, Sider, Content } = Layout

const menu: MenuProps['items'] = [
  { key: '/', icon: <HomeOutlined />, label: '经营驾驶舱' },
  { key: '/workflow', icon: <NodeIndexOutlined />, label: '全链路沙盘' },
  { key: '/products', icon: <ProductOutlined />, label: '商品中心' },
  { key: '/orders', icon: <ShoppingCartOutlined />, label: '订单履约' },
  { key: '/returns', icon: <SwapOutlined />, label: '退货售后' },
  { key: '/procurement', icon: <ShopOutlined />, label: '采购管理' },
  { key: '/inventory', icon: <DatabaseOutlined />, label: '仓储库存' },
  { key: '/finance', icon: <DollarOutlined />, label: '经营财务' },
  { key: '/integrations', icon: <ApiOutlined />, label: '平台连接' },
  { key: '/imports', icon: <ImportOutlined />, label: '数据导入' },
  { key: '/administration', icon: <SafetyCertificateOutlined />, label: '系统管理' },
]

const titles: Record<string, string> = { '/':'经营驾驶舱', '/workflow':'全链路沙盘', '/products':'商品中心', '/orders':'订单履约', '/returns':'退货售后', '/procurement':'采购管理', '/inventory':'仓储库存', '/finance':'经营财务', '/integrations':'平台连接', '/imports':'数据导入', '/administration':'系统管理' }

function ProtectedApp() {
  const { user, loading, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  if (loading) return <div style={{ display:'grid',placeItems:'center',height:'100vh' }}><Spin size="large" /></div>
  if (!user) return <Navigate to="/login" replace />
  const userMenu: MenuProps['items'] = [
    { key:'user', icon:<UserOutlined/>, label:`${user.first_name || user.username} · ${user.role}`, disabled:true },
    { type:'divider' },
    { key:'logout', icon:<LogoutOutlined/>, label:'退出登录', onClick: async () => { await logout(); navigate('/login') } },
  ]
  return <Layout className="app-shell">
    <Sider width={238} theme="dark" style={{ position:'fixed',left:0,top:0,bottom:0 }}>
      <div className="brand"><div className="brand-mark">N</div><div><div className="brand-title">NEXUS</div><div className="brand-sub">COMMERCE OS</div></div></div>
      <Menu theme="dark" mode="inline" items={menu} selectedKeys={[location.pathname]} onClick={({ key }) => navigate(key)} style={{ border:0 }} />
      <div className="sidebar-foot"><strong><span className="live-dot"/>NEXUS ONLINE</strong>模拟器已就绪 · API v1</div>
    </Sider>
    <Layout style={{ marginLeft:238 }}>
      <Header className="topbar">
        <div className="topbar-title"><span className="topbar-kicker">NEXUS /</span> {titles[location.pathname] || 'Commerce OS'}</div>
        <div className="topbar-right"><Badge dot><Button type="text" icon={<BarChartOutlined />}/></Badge><Dropdown menu={{ items:userMenu }}><Avatar style={{ background:'linear-gradient(135deg,#6758e8,#22c7b8)',cursor:'pointer' }}>{(user.first_name || user.username)[0].toUpperCase()}</Avatar></Dropdown></div>
      </Header>
      <Content className="content">
        <Suspense fallback={<div style={{display:'grid',placeItems:'center',height:420}}><Spin size="large"/></div>}><Routes>
          <Route path="/" element={<DashboardPage/>}/>
          <Route path="/workflow" element={<WorkflowPage/>}/>
          <Route path="/products" element={<ProductsPage/>}/>
          <Route path="/orders" element={<OrdersPage/>}/>
          <Route path="/returns" element={<ReturnsPage/>}/>
          <Route path="/procurement" element={<ProcurementPage/>}/>
          <Route path="/inventory" element={<InventoryPage/>}/>
          <Route path="/finance" element={<FinancePage/>}/>
          <Route path="/integrations" element={<IntegrationsPage/>}/>
          <Route path="/imports" element={<ImportsPage/>}/>
          <Route path="/administration" element={<AdministrationPage/>}/>
          <Route path="*" element={<Navigate to="/" replace/>}/>
        </Routes></Suspense>
      </Content>
    </Layout>
  </Layout>
}

export default function App() {
  return <Suspense fallback={<div style={{display:'grid',placeItems:'center',height:'100vh'}}><Spin size="large"/></div>}><Routes><Route path="/login" element={<LoginPage/>}/><Route path="*" element={<ProtectedApp/>}/></Routes></Suspense>
}
