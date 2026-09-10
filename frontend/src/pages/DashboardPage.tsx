import { useEffect, useState } from 'react'
import { Card, Segmented, Skeleton, Tag } from 'antd'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api from '../api'
import type { DashboardData } from '../types'
import PageHeader from '../components/PageHeader'

const money = (value: string | number) => `¥${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits:0 })}`

export default function DashboardPage() {
  const [days, setDays] = useState(30)
  const [data, setData] = useState<DashboardData | null>(null)
  useEffect(() => { api.get('/reports/dashboard/', { params:{ days } }).then(r => setData(r.data)) }, [days])
  if (!data) return <><PageHeader title="经营驾驶舱" subtitle="跨平台业务的统一视图"/><Skeleton active/></>
  const metrics = [
    ['销售额', money(data.sales), `${data.orders} 笔订单`],
    ['贡献利润', money(data.contribution_profit_cny), '已归集经营成本'],
    ['现有库存', Number(data.inventory.on_hand || 0).toLocaleString(), `预占 ${data.inventory.reserved || 0}`],
    ['退货率', `${data.return_rate}%`, `近 ${data.period_days} 天`],
  ]
  return <>
    <PageHeader title="经营驾驶舱" subtitle="今天的库存、履约与利润，一眼看清" actions={<Segmented value={days} onChange={v => setDays(Number(v))} options={[{label:'7天',value:7},{label:'30天',value:30},{label:'90天',value:90}]}/>}/>
    <div className="metric-grid">{metrics.map(([label,value,note]) => <div className="metric-card" key={label}><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className="metric-note">{note}</div></div>)}</div>
    <div className="section-grid">
      <div className="section-card"><div className="section-title"><span>销售趋势</span><Tag color="green">多平台汇总</Tag></div><div className="trend-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.trend}><defs><linearGradient id="sales" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#0b7a58" stopOpacity={.28}/><stop offset="95%" stopColor="#0b7a58" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#edf0eb"/><XAxis dataKey="day" tick={{fontSize:11}} axisLine={false}/><YAxis tick={{fontSize:11}} axisLine={false}/><Tooltip formatter={(v) => money(String(v))}/><Area type="monotone" dataKey="sales" stroke="#0b7a58" strokeWidth={2.5} fill="url(#sales)"/></AreaChart></ResponsiveContainer></div></div>
      <div className="section-card"><div className="section-title"><span>需要关注</span><span style={{fontSize:12,color:'#8a9690'}}>实时</span></div>
        <div className="alert-row"><div className="alert-dot"/><div><strong>{data.low_stock_skus} 个 SKU 低于安全库存</strong><span>建议进入补货中心生成建议</span></div></div>
        <div className="alert-row"><div className="alert-dot" style={{background:'#0b7a58'}}/><div><strong>{data.pending_purchase_approvals} 张采购单待审批</strong><span>审批后才能进入采购执行</span></div></div>
        <div className="alert-row"><div className="alert-dot" style={{background:data.failed_sync_jobs ? '#d04d3c':'#0b7a58'}}/><div><strong>{data.failed_sync_jobs} 个同步任务失败</strong><span>{data.failed_sync_jobs ? '请查看连接器日志并重试':'所有平台同步状态正常'}</span></div></div>
      </div>
    </div>
  </>
}

