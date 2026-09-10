import type { ReactNode } from 'react'

export default function PageHeader({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return <div className="page-head"><div><h1>{title}</h1><p>{subtitle}</p></div><div>{actions}</div></div>
}

