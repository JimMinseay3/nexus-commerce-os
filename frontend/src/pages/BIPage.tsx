import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, DatePicker, Empty, Input, message, Modal, Segmented, Select, Skeleton, Table, Tag, Tooltip as AntTooltip } from 'antd'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DownloadOutlined, EyeOutlined, FilterOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import api from '../api'
import PageHeader from '../components/PageHeader'

type FilterState = { date_from?: string; date_to?: string; channel?: string; store?: string; country?: string; warehouse?: string; sku?: string }
type Row = Record<string, any>
type BIData = {
  period: { date_from: string; date_to: string; days: number }; currency: string
  kpis: Record<string, number | string>; inventory: Record<string, number | string>
  trend: Row[]; channels: Row[]; stores: Row[]; countries: Row[]; top_skus: Row[]
  warehouse_inventory: Row[]; finance_breakdown: Row[]; order_status: Row[]; return_status: Row[]; return_reasons: Row[]
  filter_options: { channels: string[]; stores: Row[]; countries: string[]; warehouses: Row[]; skus: Row[] }
  source_summary: string[]; updated_at: string
}

const colors = ['#6758e8', '#22c7b8', '#ffb44a', '#ff7187', '#4f8cff', '#9a6bff']
const channelNames: Record<string, string> = { amazon:'Amazon', ebay:'eBay', walmart:'Walmart', wayfair:'Wayfair', lingxing:'领星', mock:'模拟器' }
const costNames: Record<string, string> = { revenue:'销售收入', product_cost:'商品成本', commission:'平台佣金', storage:'仓储费', last_mile:'尾程运费', first_mile:'头程运费', duty:'关税', vat:'VAT / 销售税', coupon:'优惠券', advertising:'广告费', refund:'退款', return_loss:'退货损失', other:'其他' }
const returnNames: Record<string, string> = { requested:'已申请', approved:'已批准', in_transit:'退回中', received:'已收货', inspected:'已质检', refunded:'已退款', closed:'已关闭', rejected:'已拒绝' }
const number = (value: any) => Number(value || 0)
const money = (value: any) => `¥${number(value).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`
const shortMoney = (value: any) => number(value) >= 10000 ? `¥${(number(value) / 10000).toFixed(1)}万` : money(value)

export default function BIPage() {
  const [data, setData] = useState<BIData | null>(null)
  const [filters, setFilters] = useState<FilterState>({})
  const [section, setSection] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [views, setViews] = useState<Row[]>([])
  const [saveOpen, setSaveOpen] = useState(false)
  const [viewName, setViewName] = useState('')

  const load = useCallback(async (next: FilterState = filters) => {
    setLoading(true)
    try { setData((await api.get('/analytics/workbench/', { params: { days: 30, ...next } })).data) }
    catch (error: any) { message.error(error.userMessage || 'BI 数据加载失败') }
    finally { setLoading(false) }
  }, [filters])
  const loadViews = useCallback(() => api.get('/analytics-saved-views/', { params:{ page_size:100 } }).then(r => setViews(r.data.results || r.data)), [])
  useEffect(() => { load({}); loadViews() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const update = (key: keyof FilterState, value?: string) => { const next = { ...filters, [key]: value || undefined }; setFilters(next); load(next) }
  const setDateRange = (range: [Dayjs | null, Dayjs | null] | null) => { const next = { ...filters, date_from: range?.[0]?.format('YYYY-MM-DD'), date_to: range?.[1]?.format('YYYY-MM-DD') }; setFilters(next); load(next) }
  const clearFilters = () => { setFilters({}); load({}) }
  const applyView = (id?: string) => { const view = views.find(item => item.id === id); if (!view) return; setSection(view.dashboard || 'overview'); setFilters(view.filters || {}); load(view.filters || {}) }
  const saveView = async () => { if (!viewName.trim()) return message.warning('请输入视图名称'); await api.post('/analytics-saved-views/', { name:viewName.trim(), dashboard:section, filters, layout:{ version:1 } }); message.success('分析视图已保存'); setSaveOpen(false); setViewName(''); loadViews() }
  const exportData = async () => {
    const datasets: Record<string,string> = { overview:'trend', profit:'finance_breakdown', inventory:'warehouse_inventory', returns:'return_reasons' }
    const response = await api.get('/analytics/export/', { params:{ ...filters, dataset:datasets[section] }, responseType:'blob' })
    const url = URL.createObjectURL(response.data); const link = document.createElement('a'); link.href = url; link.download = `nexus-bi-${section}.csv`; link.click(); URL.revokeObjectURL(url)
  }

  const activeFilters = Object.values(filters).filter(Boolean).length
  const dateValue = filters.date_from && filters.date_to ? [dayjs(filters.date_from), dayjs(filters.date_to)] as [Dayjs, Dayjs] : null
  const chartTrend = useMemo(() => (data?.trend || []).map(row => ({ ...row, day:String(row.day).slice(5), gmv:number(row.gmv), profit:number(row.profit), revenue:number(row.revenue), cost:number(row.cost) })), [data])
  if (!data && loading) return <><PageHeader title="BI 分析中心" subtitle="正在构建统一经营视图"/><Skeleton active paragraph={{rows:12}}/></>
  if (!data) return <Empty description="暂无可分析数据" />

  const kpis = section === 'inventory' ? [
    ['现有库存', number(data.inventory.on_hand).toLocaleString(), '全部履约节点'], ['可用库存', number(data.inventory.available).toLocaleString(), `预占 ${number(data.inventory.reserved).toLocaleString()}`],
    ['在途库存', number(data.inventory.in_transit).toLocaleString(), '采购与调拨在途'], ['库存货值', money(data.kpis.inventory_value), `残次 ${number(data.inventory.damaged).toLocaleString()}`],
  ] : section === 'returns' ? [
    ['退货单量', number(data.kpis.returns).toLocaleString(), `占订单 ${data.kpis.return_rate}%`], ['退款金额', money(data.kpis.refund), '全额与部分退款'],
    ['订单总量', number(data.kpis.orders).toLocaleString(), `覆盖 ${data.period.days} 天`], ['平均客单价', money(data.kpis.average_order_value), '原始渠道金额'],
  ] : [
    ['GMV', money(data.kpis.gmv), `${data.kpis.orders} 笔订单`], ['净销售额', money(data.kpis.net_revenue), `${number(data.kpis.units).toLocaleString()} 件商品`],
    ['贡献利润', money(data.kpis.contribution_profit), `利润率 ${data.kpis.contribution_margin}%`], ['平均客单价', money(data.kpis.average_order_value), `退货率 ${data.kpis.return_rate}%`],
  ]

  return <>
    <PageHeader title="BI 分析中心" subtitle="销售、利润、库存与售后的一体化决策工作台" actions={<div className="bi-actions"><Select allowClear placeholder="打开已保存视图" style={{width:180}} options={views.map(v => ({value:v.id,label:`${v.name}${v.is_shared ? ' · 共享':''}`}))} onChange={applyView}/><Button icon={<SaveOutlined/>} onClick={() => setSaveOpen(true)}>保存视图</Button><Button icon={<DownloadOutlined/>} onClick={exportData}>导出数据</Button></div>}/>
    <div className="bi-hero"><div><Tag className="glow-tag" bordered={false}>NEXUS INTELLIGENCE · METRIC V1</Tag><h2>让每一个业务事件，<br/>变成下一步决策。</h2><p>统一 NEXUS 标准模型中的订单、库存、财务与退货事实；筛选、点击下钻、保存并导出你的分析视角。</p></div><div className="bi-pulse"><div><b>{data.kpis.contribution_margin}%</b><span>贡献利润率</span></div><small>数据更新于 {dayjs(data.updated_at).format('HH:mm:ss')}</small></div><i className="bi-orbit bi-orbit-a"/><i className="bi-orbit bi-orbit-b"/></div>
    <div className="bi-filterbar"><div className="bi-filter-title"><FilterOutlined/><span>全局筛选</span>{activeFilters > 0 && <Tag color="purple">{activeFilters} 项已启用</Tag>}</div><DatePicker.RangePicker value={dateValue} onChange={setDateRange} allowClear/><Select allowClear value={filters.channel} placeholder="全部渠道" onChange={v => update('channel', v)} options={data.filter_options.channels.map(v => ({value:v,label:channelNames[v] || v}))}/><Select showSearch allowClear value={filters.store} placeholder="全部店铺" onChange={v => update('store', v)} options={data.filter_options.stores.map(v => ({value:v.id,label:v.name}))}/><Select allowClear value={filters.country} placeholder="全部国家" onChange={v => update('country', v)} options={data.filter_options.countries.map(v => ({value:v,label:v}))}/><Select showSearch allowClear value={filters.warehouse} placeholder="全部仓库" onChange={v => update('warehouse', v)} options={data.filter_options.warehouses.map(v => ({value:v.id,label:v.name}))}/><Select showSearch allowClear value={filters.sku} placeholder="全部 SKU" onChange={v => update('sku', v)} optionFilterProp="label" options={data.filter_options.skus.map(v => ({value:v.id,label:`${v.code} · ${v.name}`}))}/><AntTooltip title="清空全部筛选"><Button icon={<ReloadOutlined/>} onClick={clearFilters}/></AntTooltip></div>
    <div className="bi-section-switch"><Segmented block value={section} onChange={setSection} options={[{label:'经营总览',value:'overview'},{label:'利润分析',value:'profit'},{label:'库存健康',value:'inventory'},{label:'退货洞察',value:'returns'}]}/></div>
    <div className="metric-grid bi-metrics">{kpis.map(([label,value,note], index) => <div className={`metric-card bi-metric bi-metric-${index}`} key={label}><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className="metric-note">{note}</div></div>)}</div>
    {section === 'overview' && <div className="bi-grid"><ChartCard title="GMV 与贡献利润趋势" note={`${data.period.date_from} — ${data.period.date_to}`} wide><ResponsiveContainer width="100%" height="100%"><AreaChart data={chartTrend}><defs><linearGradient id="biGmv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#6758e8" stopOpacity={.36}/><stop offset="1" stopColor="#6758e8" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#edf0f5"/><XAxis dataKey="day" axisLine={false}/><YAxis axisLine={false} tickFormatter={v => shortMoney(v).replace('¥','')}/><Tooltip formatter={(v:any, n:any) => [money(v), n === 'gmv' ? 'GMV':'贡献利润']}/><Area type="monotone" dataKey="gmv" stroke="#6758e8" strokeWidth={3} fill="url(#biGmv)"/><Line type="monotone" dataKey="profit" stroke="#22c7b8" strokeWidth={2.5} dot={false}/></AreaChart></ResponsiveContainer></ChartCard><ChartCard title="渠道销售结构" note="点击渠道可下钻"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data.channels.map(v => ({...v,value:number(v.gmv),name:channelNames[v.key] || v.key}))} dataKey="value" nameKey="name" innerRadius={55} outerRadius={86} paddingAngle={4} onClick={(entry:any) => update('channel', entry.key)}>{data.channels.map((_,i) => <Cell key={i} fill={colors[i%colors.length]}/>)}</Pie><Tooltip formatter={(v:any) => money(v)}/><Legend iconType="circle"/></PieChart></ResponsiveContainer></ChartCard><ChartCard title="热销 SKU 排名" note="点击条目按 SKU 下钻" wide><ResponsiveContainer width="100%" height="100%"><BarChart data={data.top_skus.slice(0,10)} layout="vertical" margin={{left:15}}><CartesianGrid horizontal={false} stroke="#edf0f5"/><XAxis type="number" axisLine={false} tickFormatter={v => shortMoney(v).replace('¥','')}/><YAxis type="category" dataKey="code" width={90} axisLine={false}/><Tooltip formatter={(v:any) => money(v)}/><Bar dataKey="sales" radius={[0,7,7,0]} fill="#6758e8" onClick={(entry:any) => update('sku', entry.key)}/></BarChart></ResponsiveContainer></ChartCard><ChartCard title="国家 / 地区表现" note={`${data.countries.length} 个市场`}><ResponsiveContainer width="100%" height="100%"><BarChart data={data.countries}><CartesianGrid vertical={false} stroke="#edf0f5"/><XAxis dataKey="key" axisLine={false}/><YAxis axisLine={false} tickFormatter={v => shortMoney(v).replace('¥','')}/><Tooltip formatter={(v:any) => money(v)}/><Bar dataKey="gmv" fill="#22c7b8" radius={[7,7,0,0]}/></BarChart></ResponsiveContainer></ChartCard></div>}
    {section === 'profit' && <div className="bi-grid"><ChartCard title="收入、成本与利润趋势" note="统一换算为 CNY" wide><ResponsiveContainer width="100%" height="100%"><AreaChart data={chartTrend}><CartesianGrid vertical={false} stroke="#edf0f5"/><XAxis dataKey="day" axisLine={false}/><YAxis axisLine={false}/><Tooltip formatter={(v:any) => money(v)}/><Legend/><Area type="monotone" dataKey="revenue" name="收入" fill="#dcd8ff" stroke="#6758e8"/><Area type="monotone" dataKey="cost" name="成本" fill="#ffe2d5" stroke="#ff8664"/></AreaChart></ResponsiveContainer></ChartCard><ChartCard title="费用构成" note="按经营科目归集"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data.finance_breakdown.map(v => ({...v,value:number(v.amount),name:costNames[v.key]||v.key}))} dataKey="value" nameKey="name" innerRadius={45} outerRadius={82}>{data.finance_breakdown.map((_,i) => <Cell key={i} fill={colors[i%colors.length]}/>)}</Pie><Tooltip formatter={(v:any) => money(v)}/></PieChart></ResponsiveContainer></ChartCard><div className="bi-table-card bi-wide"><div className="section-title"><span>利润科目明细</span><Tag color="cyan">可导出</Tag></div><Table rowKey="key" pagination={false} dataSource={data.finance_breakdown} columns={[{title:'经营科目',dataIndex:'key',render:v=>costNames[v]||v},{title:'笔数',dataIndex:'count'},{title:'金额',dataIndex:'amount',align:'right',render:money},{title:'金额占比',dataIndex:'amount',align:'right',render:v=>`${data.kpis.net_revenue ? (number(v)/number(data.kpis.net_revenue)*100).toFixed(1):0}%`} ]}/></div></div>}
    {section === 'inventory' && <div className="bi-grid"><ChartCard title="仓库库存健康" note="现有、预占、在途与残次" wide><ResponsiveContainer width="100%" height="100%"><BarChart data={data.warehouse_inventory}><CartesianGrid vertical={false} stroke="#edf0f5"/><XAxis dataKey="warehouse__name" axisLine={false}/><YAxis axisLine={false}/><Tooltip/><Legend/><Bar dataKey="available" stackId="a" name="可用" fill="#22c7b8"/><Bar dataKey="reserved" stackId="a" name="预占" fill="#6758e8"/><Bar dataKey="in_transit" name="在途" fill="#ffb44a"/><Bar dataKey="damaged" name="残次" fill="#ff7187"/></BarChart></ResponsiveContainer></ChartCard><ChartCard title="库存结构" note="全公司统一账本"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={[{name:'可用',value:number(data.inventory.available)},{name:'预占',value:number(data.inventory.reserved)},{name:'在途',value:number(data.inventory.in_transit)},{name:'残次',value:number(data.inventory.damaged)}]} dataKey="value" nameKey="name" innerRadius={52} outerRadius={84}>{colors.slice(0,4).map((c,i)=><Cell key={i} fill={c}/>)}</Pie><Tooltip/><Legend/></PieChart></ResponsiveContainer></ChartCard><div className="bi-table-card bi-wide"><div className="section-title"><span>履约节点明细</span><Tag color="green">实时余额</Tag></div><Table rowKey="warehouse_id" pagination={false} dataSource={data.warehouse_inventory} columns={[{title:'仓库',dataIndex:'warehouse__name'},{title:'国家',dataIndex:'warehouse__country'},{title:'现有量',dataIndex:'on_hand',align:'right'},{title:'预占量',dataIndex:'reserved',align:'right'},{title:'可用量',dataIndex:'available',align:'right'},{title:'在途量',dataIndex:'in_transit',align:'right'},{title:'残次量',dataIndex:'damaged',align:'right'}]}/></div></div>}
    {section === 'returns' && <div className="bi-grid"><ChartCard title="退货状态分布" note="从申请到退款闭环"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data.return_status.map(v => ({...v,value:v.count,name:returnNames[v.key]||v.key}))} dataKey="value" nameKey="name" innerRadius={48} outerRadius={84}>{data.return_status.map((_,i)=><Cell key={i} fill={colors[i%colors.length]}/>)}</Pie><Tooltip/><Legend/></PieChart></ResponsiveContainer></ChartCard><ChartCard title="退货原因排行" note="定位商品与履约问题" wide><ResponsiveContainer width="100%" height="100%"><BarChart data={data.return_reasons} layout="vertical" margin={{left:20}}><CartesianGrid horizontal={false} stroke="#edf0f5"/><XAxis type="number" axisLine={false}/><YAxis type="category" dataKey="key" width={110} axisLine={false}/><Tooltip/><Bar dataKey="count" fill="#ff7187" radius={[0,7,7,0]}/></BarChart></ResponsiveContainer></ChartCard><div className="bi-table-card bi-wide"><div className="section-title"><span>售后问题清单</span><Tag color="orange">质量洞察</Tag></div><Table rowKey="key" pagination={false} dataSource={data.return_reasons} columns={[{title:'退货原因',dataIndex:'key',render:v=>v||'未分类'},{title:'退货单量',dataIndex:'count',align:'right'},{title:'退款金额',dataIndex:'refund',align:'right',render:money},{title:'占全部退货',dataIndex:'count',align:'right',render:v=>`${data.kpis.returns ? (number(v)/number(data.kpis.returns)*100).toFixed(1):0}%`} ]}/></div></div>}
    <div className="bi-lineage"><EyeOutlined/><span>指标版本 v1 · 字段目录 v1.0</span>{data.source_summary.map(source => <Tag key={source}>{source}</Tag>)}</div>
    <Modal title="保存当前分析视图" open={saveOpen} onOk={saveView} onCancel={() => setSaveOpen(false)} okText="保存" cancelText="取消"><p style={{color:'#777d92'}}>保存当前标签页与全部筛选条件，下次可一键恢复。</p><Input autoFocus value={viewName} onChange={e => setViewName(e.target.value)} placeholder="例如：美国站月度利润" maxLength={120}/></Modal>
  </>
}

function ChartCard({ title, note, wide, children }: { title:string; note:string; wide?:boolean; children:React.ReactNode }) { return <div className={`bi-chart-card ${wide ? 'bi-wide':''}`}><div className="section-title"><span>{title}</span><small>{note}</small></div><div className="bi-chart-body">{children}</div></div> }
