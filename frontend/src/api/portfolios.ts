import request from '@/utils/request'

export const getPortfolios = (params: any) =>
  request({
    url: '/funds/portfolios',
    method: 'get',
    params
  })
