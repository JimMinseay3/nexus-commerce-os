import { useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, message, Modal, Select, Space, Table, type TableColumnsType } from 'antd'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import api from '../api'
import type { Paginated } from '../types'

export interface FormField {
  name: string
  label: string
  type?: 'text' | 'number' | 'select' | 'textarea' | 'password'
  required?: boolean
  options?: Array<{ label: string; value: string | number }>
  initialValue?: unknown
}

interface Props<T extends object> {
  endpoint: string
  columns: TableColumnsType<T>
  rowKey?: string
  createTitle?: string
  createFields?: FormField[]
  extraTools?: React.ReactNode
  refreshKey?: number
}

export default function ResourceTable<T extends object>({ endpoint, columns, rowKey = 'id', createTitle, createFields, extraTools, refreshKey }: Props<T>) {
  const [rows, setRows] = useState<T[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async (nextPage = page, query = search) => {
    setLoading(true)
    try {
      const { data } = await api.get<Paginated<T>>(endpoint, { params: { page: nextPage, search: query } })
      setRows(data.results); setTotal(data.count); setPage(nextPage)
    } catch (error: any) { message.error(error.userMessage) }
    finally { setLoading(false) }
  }

  useEffect(() => { void load(1) }, [endpoint, refreshKey])

  const create = async () => {
    try {
      const values = await form.validateFields()
      await api.post(endpoint, values)
      message.success('保存成功'); setOpen(false); form.resetFields(); await load(1)
    } catch (error: any) { if (error.userMessage) message.error(error.userMessage) }
  }

  return <div className="data-card">
    <div className="table-tools">
      <Space>
        <Input allowClear prefix={<SearchOutlined />} placeholder="搜索编号、名称…" value={search} onChange={e => setSearch(e.target.value)} onPressEnter={() => load(1)} style={{ width: 260 }} />
        <Button onClick={() => load(1)}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={() => load()}/>
      </Space>
      <Space>{extraTools}{createFields && <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{createTitle || '新建'}</Button>}</Space>
    </div>
    <Table<T> rowKey={rowKey} loading={loading} columns={columns} dataSource={rows} scroll={{ x: 950 }} pagination={{ current: page, total, pageSize: 30, showTotal: n => `共 ${n} 条`, onChange: p => load(p) }} />
    <Modal title={createTitle || '新建记录'} open={open} onCancel={() => setOpen(false)} onOk={create} okText="保存" cancelText="取消" width={620} destroyOnHidden>
      <Form form={form} layout="vertical" className="form-grid" style={{ marginTop: 22 }}>
        {createFields?.map(field => <Form.Item key={field.name} name={field.name} label={field.label} rules={field.required ? [{ required: true, message: `请输入${field.label}` }] : []} initialValue={field.initialValue} className={field.type === 'textarea' ? 'full-span' : ''}>
          {field.type === 'select' ? <Select options={field.options} /> : field.type === 'number' ? <InputNumber style={{ width: '100%' }} /> : field.type === 'textarea' ? <Input.TextArea rows={3} /> : <Input type={field.type === 'password' ? 'password' : 'text'} />}
        </Form.Item>)}
      </Form>
    </Modal>
  </div>
}

