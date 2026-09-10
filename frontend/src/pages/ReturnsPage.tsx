import { Tag, type TableColumnsType } from 'antd'
import PageHeader from '../components/PageHeader'
import ResourceTable from '../components/ResourceTable'
import StatusPill from '../components/StatusPill'

export default function ReturnsPage(){
  const columns:TableColumnsType<any>=[{title:'平台退货号',dataIndex:'external_id',render:v=>v||'本地创建'},{title:'订单号',dataIndex:'order_external_id'},{title:'状态',dataIndex:'status',render:v=><StatusPill value={v}/>},{title:'退货原因',dataIndex:'reason',width:260},{title:'退款金额',dataIndex:'refund_amount',render:(v,r)=>`${r.currency} ${Number(v).toFixed(2)}`},{title:'退回运费',dataIndex:'return_shipping_cost'},{title:'明细数',dataIndex:'items',render:v=><Tag>{v?.length||0} 件</Tag>},{title:'更新时间',dataIndex:'updated_at',render:v=>new Date(v).toLocaleString()}]
  return <><PageHeader title="退货售后" subtitle="从平台申请到质检、重新入库、报废与利润调整"/><ResourceTable endpoint="/returns/" columns={columns}/></>
}

