import { useEffect, useState } from 'react'
import { Button, message, Space, Tabs, type TableColumnsType } from 'antd'
import { CheckOutlined, SendOutlined } from '@ant-design/icons'
import api from '../api'
import PageHeader from '../components/PageHeader'
import ResourceTable from '../components/ResourceTable'
import StatusPill from '../components/StatusPill'

export default function ProcurementPage() {
  const [suppliers,setSuppliers]=useState<any[]>([]); const [warehouses,setWarehouses]=useState<any[]>([]); const [refresh,setRefresh]=useState(0)
  useEffect(()=>{Promise.all([api.get('/suppliers/',{params:{page_size:500}}),api.get('/warehouses/',{params:{page_size:500}})]).then(([s,w])=>{setSuppliers(s.data.results.map((x:any)=>({label:`${x.code} · ${x.name}`,value:x.id})));setWarehouses(w.data.results.map((x:any)=>({label:`${x.code} · ${x.name}`,value:x.id})))})},[])
  const act=async(id:string,name:string)=>{try{await api.post(`/purchase-orders/${id}/${name}/`);message.success(name==='approve'?'审批通过':'已提交审批');setRefresh(x=>x+1)}catch(e:any){message.error(e.userMessage)}}
  const poColumns:TableColumnsType<any>=[{title:'采购单号',dataIndex:'po_number',fixed:'left',width:190},{title:'供应商',dataIndex:'supplier_name',width:180},{title:'入库仓',dataIndex:'warehouse_name',width:160},{title:'预计到货',dataIndex:'expected_at',render:v=>v||'—'},{title:'金额',dataIndex:'total',render:(v,r)=>`${r.currency} ${Number(v).toFixed(2)}`},{title:'状态',dataIndex:'status',render:v=><StatusPill value={v}/>},{title:'操作',fixed:'right',width:180,render:(_,r)=><Space>{r.status==='draft'&&<Button type="link" icon={<SendOutlined/>} onClick={()=>act(r.id,'submit')}>提交</Button>}{r.status==='pending_approval'&&<Button type="link" icon={<CheckOutlined/>} onClick={()=>act(r.id,'approve')}>审批</Button>}</Space>}]
  const receiptColumns:TableColumnsType<any>=[{title:'收货单号',dataIndex:'receipt_no'},{title:'采购单',dataIndex:'purchase_order'},{title:'仓库',dataIndex:'warehouse'},{title:'收货时间',dataIndex:'received_at',render:v=>new Date(v).toLocaleString()},{title:'到岸成本',dataIndex:'landed_cost'},{title:'分摊方式',dataIndex:'allocation_method'},{title:'过账',dataIndex:'posted',render:v=><StatusPill value={v?'posted':'draft'}/>}]
  return <><PageHeader title="采购管理" subtitle="从补货建议到采购、在途、收货和到岸成本"/><Tabs items={[
    {key:'po',label:'采购订单',children:<ResourceTable endpoint="/purchase-orders/" columns={poColumns} refreshKey={refresh} createTitle="新建采购单" createFields={[{name:'po_number',label:'采购单号',required:true},{name:'supplier',label:'供应商',type:'select',options:suppliers,required:true},{name:'warehouse',label:'目标仓库',type:'select',options:warehouses,required:true},{name:'currency',label:'币种',initialValue:'CNY'},{name:'expected_at',label:'预计到货日（YYYY-MM-DD）'},{name:'notes',label:'备注',type:'textarea'}]}/>},
    {key:'receipts',label:'收货入库',children:<ResourceTable endpoint="/receipts/" columns={receiptColumns}/>},
    {key:'suppliers',label:'供应商绩效',children:<ResourceTable endpoint="/suppliers/" columns={[{title:'编码',dataIndex:'code'},{title:'供应商',dataIndex:'name'},{title:'默认交期',dataIndex:'default_lead_time_days',render:v=>`${v} 天`},{title:'账期',dataIndex:'payment_terms_days',render:v=>`${v} 天`},{title:'绩效分',dataIndex:'performance_score',render:v=>`${v} 分`},{title:'状态',dataIndex:'is_active',render:v=><StatusPill value={v?'active':'disabled'}/>} ]}/>},
  ]}/></>
}

