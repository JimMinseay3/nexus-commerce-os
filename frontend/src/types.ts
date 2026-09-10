export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface User {
  id: number
  username: string
  first_name: string
  last_name: string
  email: string
  role: string
  company_id: string
  last_login?: string
}

export interface DashboardData {
  period_days: number
  orders: number
  sales: string
  revenue_cny: string
  contribution_profit_cny: string
  return_rate: number
  inventory: { on_hand: string; reserved: string; damaged: string }
  low_stock_skus: number
  pending_purchase_approvals: number
  failed_sync_jobs: number
  trend: Array<{ day: string; orders: number; sales: string }>
}

