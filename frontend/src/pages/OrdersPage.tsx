import { useState } from 'react'
import { Button, Drawer, message, Space, Tag, type TableColumnsType } from 'antd'
import { EyeOutlined, PartitionOutlined } from '@ant-design/icons'
import api from '../api'
import PageHeader from '../components/PageHeader'
import ResourceTable from '../components/ResourceTable'
import StatusPill from '../components/StatusPill'

export default function OrdersPage() {
  const [selected,setSelected]=useState<any>(null); const [refresh,setRefresh]=useState(0)
  const allocate = async (id:string) => { try { await api.post(`/orders/${id}/allocate/`); message.success('库存分配完成'); setRefresh(x=>x+1) } catch(e:any){ message.error(e.userMessage) } }
  const columns:TableColumnsType<any>=[
    {title:'平台订单号',dataIndex:'external_id',fixed:'left',width:190},{title:'平台',dataIndex:'provider',render:v=><Tag>{String(v).toUpperCase()}</Tag>,width:100},{title:'店铺',dataIndex:'store_name',width:150},
    {title:'下单时间',dataIndex:'ordered_at',width:180,render:v=>new Date(v).toLocaleString()},{title:'状态',dataIndex:'status',render:v=><StatusPill value={v}/>,width:110},
    {title:'履约',dataIndex:'fulfillment',render:v=>String(v).toUpperCase(),width:90},{title:'金额',dataIndex:'total',render:(v,r)=>`${r.currency} ${Number(v).toFixed(2)}`,width:130},
    {title:'买家',dataIndex:'buyer_name',render:v=>v||'已脱敏',width:120},{title:'操作',fixed:'right',width:170,render:(_,r)=><Space><Button type="link" icon={<EyeOutlined/>} onClick={()=>setSelected(r)}>详情</Button>{['pending','allocating','backorder'].includes(r.status)&&<Button type="link" icon={<PartitionOutlined/>} onClick={()=>allocate(r.id)}>分仓</Button>}</Space>},
  ]
  return <><PageHeader title="订单履约" subtitle="聚合多平台订单，完成分仓、拣货、出库与追踪回传"/><ResourceTable endpoint="/orders/" columns={columns} refreshKey={refresh}/>
    <Drawer title={`订单 ${selected?.external_id||''}`} width={680} open={!!selected} onClose={()=>setSelected(null)}>{selected&&<><div className="section-card" style={{marginBottom:16}}><div className="section-title">订单概览 <StatusPill value={selected.status}/></div><p>店铺：{selected.store_name} · {selected.provider}</p><p>金额：{selected.currency} {selected.total}　履约：{selected.fulfillment?.toUpperCase()}</p><p>收货地：{[selected.ship_to?.country,selected.ship_to?.state,selected.ship_to?.city,selected.ship_to?.postal_code].filter(Boolean).join(' / ')||'平台已脱敏'}</p></div><div className="section-card"><div className="section-title">商品明细</div>{selected.items?.map((x:any)=><div className="alert-row" key={x.id}><div><strong>{x.external_sku} · {x.title||x.sku_code||'未映射商品'}</strong><span>数量 {x.quantity}　单价 {selected.currency} {x.unit_price}　已发 {x.shipped_quantity}</span></div></div>)}</div></>}</Drawer>
  </>
}

