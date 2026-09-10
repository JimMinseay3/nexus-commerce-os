import { useEffect, useMemo, useState } from 'react'
import { Button, Progress, Skeleton, Tag, Tooltip, message } from 'antd'
import {
  ApiOutlined, AuditOutlined, CheckCircleFilled, CloudSyncOutlined, DollarOutlined,
  InboxOutlined, PartitionOutlined, PlayCircleOutlined, RocketOutlined, ShoppingCartOutlined,
} from '@ant-design/icons'
import api from '../api'
import PageHeader from '../components/PageHeader'

interface WorkflowStep {
  key: string
  title: string
  description: string
  count: number
}

interface WorkflowData {
  mode: string
  steps: WorkflowStep[]
  summary: {
    orders: number
    pending_orders: number
    shipments: number
    returns: number
    purchase_orders: number
    settlements: number
    revenue_cny: string
    profit_cny: string
  }
}

const stepIcons: Record<string, React.ReactNode> = {
  bootstrap: <InboxOutlined />,
  sync_orders: <CloudSyncOutlined />,
  allocate: <PartitionOutlined />,
  ship: <RocketOutlined />,
  return_refund: <ShoppingCartOutlined />,
  replenish: <ApiOutlined />,
  approve_purchase: <AuditOutlined />,
  receive: <InboxOutlined />,
  settle: <DollarOutlined />,
}

const actionLabels: Record<string, string> = {
  bootstrap: '准备账套',
  sync_orders: '拉取新订单',
  allocate: '执行分仓',
  ship: '完成出库',
  return_refund: '模拟售后',
  replenish: '计算建议',
  approve_purchase: '审批转单',
  receive: '确认入库',
  settle: '执行对账',
}

const money = (value: string | number) => `¥${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`

export default function WorkflowPage() {
  const [data, setData] = useState<WorkflowData | null>(null)
  const [busy, setBusy] = useState('')

  const load = () => api.get('/workflow-simulator/').then((response) => setData(response.data))
  useEffect(() => { load() }, [])

  const run = async (action: string, quiet = false) => {
    setBusy(action)
    try {
      const response = await api.post('/workflow-simulator/', { action })
      setData(response.data.workflow)
      if (!quiet) message.success(`${actionLabels[action]}完成，业务数据已落账`)
      return true
    } catch (error: any) {
      message.error(error.userMessage)
      return false
    } finally {
      setBusy('')
    }
  }

  const runAll = async () => {
    if (!data) return
    setBusy('all')
    let latest = data
    try {
      for (const step of data.steps) {
        const response = await api.post('/workflow-simulator/', { action: step.key })
        latest = response.data.workflow
        setData(latest)
      }
      message.success('一轮跨境业务闭环已完成：从订单同步到结算利润')
    } catch (error: any) {
      message.error(error.userMessage)
    } finally {
      setBusy('')
    }
  }

  const completed = useMemo(() => data?.steps.filter((step) => step.count > 0).length || 0, [data])
  const progress = data ? Math.round(completed / data.steps.length * 100) : 0

  if (!data) return <><PageHeader title="全链路沙盘" subtitle="使用模拟平台数据验证完整业务闭环" /><Skeleton active /></>

  return <>
    <PageHeader
      title="全链路业务沙盘"
      subtitle="模拟外部平台，运行真实订单、库存、采购与财务核心"
      actions={<Button className="nexus-run-button" type="primary" icon={<PlayCircleOutlined />} loading={busy === 'all'} onClick={runAll}>一键跑通全流程</Button>}
    />

    <section className="workflow-hero">
      <div className="workflow-orbit workflow-orbit-one" />
      <div className="workflow-orbit workflow-orbit-two" />
      <div className="workflow-hero-copy">
        <Tag className="glow-tag" variant="filled">NEXUS SIMULATION CORE</Tag>
        <h2>从一笔订单，到一份可解释的利润。</h2>
        <p>九个业务节点共享同一本库存与财务账。平台 API 是模拟的，订单状态机、库存事务、成本分摊、审计记录都是真实的。</p>
        <div className="workflow-trust-row">
          <span><CheckCircleFilled /> 事务锁库存</span>
          <span><CheckCircleFilled /> 幂等写入</span>
          <span><CheckCircleFilled /> 审计留痕</span>
          <span><CheckCircleFilled /> 三平台适配</span>
        </div>
      </div>
      <div className="workflow-score">
        <div className="score-ring"><Progress type="circle" percent={progress} size={124} strokeColor={{ '0%': '#7c6cff', '100%': '#3ce6c4' }} railColor="rgba(255,255,255,.1)" format={() => <><b>{completed}</b><small>/ {data.steps.length} 节点</small></>} /></div>
        <span>当前账套闭环进度</span>
      </div>
    </section>

    <div className="workflow-summary">
      <div><span>统一订单</span><b>{data.summary.orders}</b><em>{data.summary.pending_orders} 待履约</em></div>
      <div><span>已发货</span><b>{data.summary.shipments}</b><em>追踪已回传</em></div>
      <div><span>售后单</span><b>{data.summary.returns}</b><em>质检与退款</em></div>
      <div><span>采购单</span><b>{data.summary.purchase_orders}</b><em>建议转采购</em></div>
      <div><span>收入归集</span><b>{money(data.summary.revenue_cny)}</b><em>本位币 CNY</em></div>
      <div><span>贡献利润</span><b className={Number(data.summary.profit_cny) >= 0 ? 'positive' : 'negative'}>{money(data.summary.profit_cny)}</b><em>实时重算</em></div>
    </div>

    <section className="workflow-section">
      <div className="section-heading"><div><span className="eyebrow">LIVE BUSINESS GRAPH</span><h3>全业务链路</h3></div><Tag color="purple">模拟边界 · 真实核心</Tag></div>
      <div className="workflow-grid">
        {data.steps.map((step, index) => <article className={`workflow-step ${step.count > 0 ? 'is-complete' : ''}`} key={step.key}>
          <div className="step-number">{String(index + 1).padStart(2, '0')}</div>
          <div className="step-icon">{step.count > 0 ? <CheckCircleFilled /> : stepIcons[step.key]}</div>
          <div className="step-body"><h4>{step.title}</h4><p>{step.description}</p></div>
          <div className="step-footer"><span>{step.count > 0 ? `${step.count} 条记录` : '等待执行'}</span><Tooltip title="此操作会写入当前演示账套"><Button size="small" loading={busy === step.key} disabled={busy === 'all'} onClick={() => run(step.key)}>{actionLabels[step.key]}</Button></Tooltip></div>
        </article>)}
      </div>
    </section>

    <section className="simulator-note">
      <div className="simulator-note-icon"><ApiOutlined /></div>
      <div><b>连接器边界已经隔离</b><p>当前由本地模拟器生成平台事件。接入正式凭证后，Amazon、Wayfair、Walmart 连接器会向同一套统一模型写入，页面和核心流程无需修改。</p></div>
      <Tag color="cyan">API READY</Tag>
    </section>
  </>
}
