const success = ['active', 'completed', 'shipped', 'succeeded', 'approved', 'converted', 'production', 'posted']
const warning = ['pending', 'pending_approval', 'allocating', 'picking', 'ready', 'partial', 'partially_shipped', 'open', 'queued', 'running', 'in_transit']
const danger = ['failed', 'cancelled', 'rejected', 'backorder', 'refunded', 'damaged']

const labels: Record<string, string> = {
  active:'在售', draft:'草稿', completed:'已完成', shipped:'已发货', succeeded:'成功', approved:'已批准', converted:'已转单',
  pending:'待确认', pending_approval:'待审批', allocating:'待分配', picking:'待拣货', ready:'待发货', partial:'部分收货',
  partially_shipped:'部分发货', open:'待处理', queued:'排队中', running:'执行中', in_transit:'在途', failed:'失败', cancelled:'已取消',
  rejected:'已拒绝', backorder:'缺货', refunded:'已退款', closed:'已关闭', production:'生产中', requested:'已申请', inspected:'已质检',
  received:'已收货', phasing_out:'清退中', discontinued:'已停产', uploaded:'已上传', previewed:'已预览', sandbox:'沙箱', production_env:'生产',
}

export default function StatusPill({ value }: { value?: string }) {
  const status = value || 'unknown'
  const cls = success.includes(status) ? 'success' : warning.includes(status) ? 'warning' : danger.includes(status) ? 'danger' : 'neutral'
  return <span className={`status-pill status-${cls}`}>{labels[status] || status}</span>
}

