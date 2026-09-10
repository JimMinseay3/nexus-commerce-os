import { useEffect } from 'react'
import { Button, Form, Input, message } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [form] = Form.useForm()
  useEffect(() => { if (user) navigate('/') }, [user])
  const submit = async () => {
    try { const values = await form.validateFields(); await login(values.username, values.password); navigate('/') }
    catch (error: any) { if (error.userMessage) message.error(error.userMessage) }
  }
  return <div className="login-page">
    <section className="login-hero">
      <div className="brand" style={{ padding:0 }}><div className="brand-mark">Y</div><div><div className="brand-title">远帆 ERP</div><div className="brand-sub">CROSS-BORDER OS</div></div></div>
      <div style={{ position:'relative' }}><h1>把跨境业务，<br/>收进一张清晰的图里。</h1><p>商品、订单、采购、仓储与利润在同一套数据上运转。连接 Amazon、Wayfair、Walmart，不再依赖零散表格。</p></div>
      <div className="login-features"><div>多平台订单<br/><b>统一履约</b></div><div>库存与补货<br/><b>实时可解释</b></div><div>订单级利润<br/><b>自动归集</b></div></div>
    </section>
    <section className="login-panel"><div className="login-box"><h2>欢迎回来</h2><p>登录你的业务工作台</p>
      <Form form={form} layout="vertical" onFinish={submit} initialValues={{ username:'admin', password:'Admin123!' }}>
        <Form.Item name="username" label="账号" rules={[{ required:true }]}><Input size="large" prefix={<UserOutlined/>} placeholder="请输入用户名"/></Form.Item>
        <Form.Item name="password" label="密码" rules={[{ required:true }]}><Input.Password size="large" prefix={<LockOutlined/>} placeholder="请输入密码" onPressEnter={submit}/></Form.Item>
        <Button type="primary" htmlType="submit" size="large" block style={{ height:48,marginTop:8 }}>进入系统</Button>
      </Form>
      <div style={{ marginTop:22,color:'#929c97',fontSize:12,textAlign:'center' }}>默认演示账号仅用于首次体验，请上线前修改密码</div>
    </div></section>
  </div>
}

