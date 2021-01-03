// TODO: 为什么不能import
export function splitFloatHandler(splitFloat:number) {
  let splitArr: any
  splitArr = String(splitFloat).split('.')
  return splitArr
}
