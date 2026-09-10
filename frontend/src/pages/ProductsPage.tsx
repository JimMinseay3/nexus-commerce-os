import { useEffect, useState } from 'react'
import { Tabs, Tag, type TableColumnsType } from 'antd'
import api from '../api'
import PageHeader from '../components/PageHeader'
import ResourceTable from '../components/ResourceTable'
import StatusPill from '../components/StatusPill'

export default function ProductsPage() {
  const [products, setProducts] = useState<Array<{label:string;value:string}>>([])
  const [suppliers, setSuppliers] = useState<Array<{label:string;value:string}>>([])
  useEffect(() => { Promise.all([api.get('/products/',{params:{page_size:500}}),api.get('/suppliers/',{params:{page_size:500}})]).then(([p,s]) => { setProducts(p.data.results.map((x:any)=>({label:`${x.spu} · ${x.name}`,value:x.id}))); setSuppliers(s.data.results.map((x:any)=>({label:`${x.code} · ${x.name}`,value:x.id}))) }) }, [])
  const productColumns:TableColumnsType<any> = [
    {title:'SPU',dataIndex:'spu',width:150},{title:'商品名称',dataIndex:'name',width:260},{title:'品牌',dataIndex:'brand_name',render:v=>v||'—'},
    {title:'分类',dataIndex:'category_name',render:v=>v||'—'},{title:'SKU 数',dataIndex:'sku_count',width:100},{title:'状态',dataIndex:'status',render:v=><StatusPill value={v}/>,width:110},
  ]
  const skuColumns:TableColumnsType<any> = [
    {title:'SKU',dataIndex:'code',fixed:'left',width:170},{title:'SKU 名称',dataIndex:'name',width:230},{title:'所属商品',dataIndex:'product_name',width:220},
    {title:'履约',dataIndex:'fulfillment',render:v=><Tag>{String(v).toUpperCase()}</Tag>,width:100},{title:'供应商',dataIndex:'supplier_name',render:v=>v||'—',width:160},
    {title:'采购价',dataIndex:'purchase_price',render:(v,r)=>`${r.currency} ${Number(v).toFixed(2)}`,width:120},{title:'安全库存',dataIndex:'safety_stock',width:100},{title:'箱数',dataIndex:'carton_count',width:80},{title:'重量 kg',dataIndex:'gross_weight_kg',width:100},
  ]
  const supplierColumns:TableColumnsType<any> = [{title:'编码',dataIndex:'code'},{title:'供应商',dataIndex:'name'},{title:'联系人',dataIndex:'contact_name',render:v=>v||'—'},{title:'币种',dataIndex:'currency'},{title:'账期',dataIndex:'payment_terms_days',render:v=>`${v} 天`},{title:'交期',dataIndex:'default_lead_time_days',render:v=>`${v} 天`},{title:'绩效',dataIndex:'performance_score',render:v=>`${v} 分`}]
  return <><PageHeader title="商品中心" subtitle="内部商品主数据、包装属性与渠道 SKU 映射"/><Tabs items={[
    {key:'products',label:'SPU 商品',children:<ResourceTable endpoint="/products/" columns={productColumns} createTitle="新建商品" createFields={[{name:'spu',label:'SPU 编码',required:true},{name:'name',label:'商品名称',required:true},{name:'status',label:'状态',type:'select',initialValue:'active',options:[{label:'在售',value:'active'},{label:'草稿',value:'draft'}]},{name:'description',label:'描述',type:'textarea'}]}/>},
    {key:'skus',label:'SKU 与包装',children:<ResourceTable endpoint="/skus/" columns={skuColumns} createTitle="新建 SKU" createFields={[{name:'product',label:'所属商品',type:'select',options:products,required:true},{name:'code',label:'SKU 编码',required:true},{name:'name',label:'SKU 名称',required:true},{name:'barcode',label:'条码'},{name:'supplier',label:'供应商',type:'select',options:suppliers},{name:'fulfillment',label:'履约方式',type:'select',initialValue:'fbm',options:[{label:'FBM/自发货',value:'fbm'},{label:'Amazon FBA',value:'fba'},{label:'Walmart WFS',value:'wfs'},{label:'第三方仓',value:'3pl'}]},{name:'purchase_price',label:'采购价',type:'number',initialValue:0},{name:'currency',label:'币种',initialValue:'CNY'},{name:'safety_stock',label:'安全库存',type:'number',initialValue:0},{name:'moq',label:'最小起订量',type:'number',initialValue:1},{name:'case_pack',label:'整箱数',type:'number',initialValue:1},{name:'gross_weight_kg',label:'毛重 kg',type:'number',initialValue:0}]}/>},
    {key:'suppliers',label:'供应商',children:<ResourceTable endpoint="/suppliers/" columns={supplierColumns} createTitle="新建供应商" createFields={[{name:'code',label:'供应商编码',required:true},{name:'name',label:'供应商名称',required:true},{name:'contact_name',label:'联系人'},{name:'phone',label:'电话'},{name:'email',label:'邮箱'},{name:'currency',label:'币种',initialValue:'CNY'},{name:'payment_terms_days',label:'账期（天）',type:'number',initialValue:0},{name:'default_lead_time_days',label:'默认交期（天）',type:'number',initialValue:30}]}/>},
    {key:'mappings',label:'渠道映射',children:<ResourceTable endpoint="/sku-mappings/" columns={[{title:'内部 SKU',dataIndex:'sku_code'},{title:'店铺',dataIndex:'store_name'},{title:'渠道 SKU',dataIndex:'external_sku'},{title:'平台商品 ID',dataIndex:'external_product_id'},{title:'履约',dataIndex:'fulfillment',render:v=><Tag>{String(v).toUpperCase()}</Tag>},{title:'库存缓冲',dataIndex:'inventory_buffer'}]}/>} ]}/></>
}

