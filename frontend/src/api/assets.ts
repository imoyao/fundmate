// src/api/assets.ts
import { http } from '@/utils/http'

export interface AssetRecord {
  id: number
  major_category: string
  minor_category: string | null
  name: string
  amount: number
  currency: string
  account_name: string | null
  allocation: string | null
  status: string
  notes: string | null
  start_date: string | null
  end_date: string | null
  extra: Record<string, any> | null
  created_at: string | null
  updated_at: string | null
}

const BASE_URL = '/api/assets'

export function getAssets(params?: Record<string, any>) {
  return http.request<any>('get', BASE_URL, { params })
}

export function createAsset(data: any) {
  return http.request<any>('post', BASE_URL, { data })
}

export function updateAsset(id: number, data: any) {
  return http.request<any>('patch', `${BASE_URL}/${id}`, { data })
}

export function deleteAsset(id: number) {
  return http.request<any>('delete', `${BASE_URL}/${id}`)
}
