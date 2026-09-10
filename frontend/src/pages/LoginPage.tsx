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
      <div className="brand" style={{ padding:0 }}><div className="brand-mark">N</div><div><div className="brand-title">NEXUS</div><div className="brand-sub">COMMERCE OS</div></div></div>
      <div style={{ position:'relative' }}><div className="login-kicker">THE OPERATING SYSTEM FOR GLOBAL COMMERCE</div><h1>让每一笔生意，<br/>连接成完整闭环。</h1><p>NEXUS 把商品、订单、采购、仓储与利润放在同一张业务网络中。连接 Amazon、Wayfair、Walmart，也连接每一个关键决策。</p></div>
      <div className="login-features"><div><span>01</span>多平台订单<br/><b>统一履约</b></div><div><span>02</span>库存与补货<br/><b>实时可解释</b></div><div><span>03</span>订单级利润<br/><b>自动归集</b></div></div>
    </section>
    <section className="login-panel"><div className="login-box"><div className="login-panel-badge">NEXUS WORKSPACE</div><h2>欢迎回来</h2><p>登录全球业务控制台</p>
      <Form form={form} layout="vertical" onFinish={submit} initialValues={{ username:'admin', password:'Admin123!' }}>
        <Form.Item name="username" label="账号" rules={[{ required:true }]}><Input size="large" prefix={<UserOutlined/>} placeholder="请输入用户名"/></Form.Item>
        <Form.Item name="password" label="密码" rules={[{ required:true }]}><Input.Password size="large" prefix={<LockOutlined/>} placeholder="请输入密码" onPressEnter={submit}/></Form.Item>
        <Button type="primary" htmlType="submit" size="large" block style={{ height:48,marginTop:8 }}>进入系统</Button>
      </Form>
      <div style={{ marginTop:22,color:'#929c97',fontSize:12,textAlign:'center' }}>默认演示账号仅用于首次体验，请上线前修改密码</div>
    </div></section>
  </div>
}
