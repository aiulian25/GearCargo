import { describe, it, expect } from 'vitest'
import { parseStatementCsv, normalizeStatement, cents, money } from '../utils/statementCsv'
import { cacheablePrivateApi } from '../swPrivateCache'
import { isOfflineWrite } from '../utils/offlinePolicy'
import { translations } from '../i18n/translations'

const mapping = {date:'0',amount:'1',currency:'2',vendor:'3'}
const settings = {decimal:',',dateFormat:'dmy',sign:'bank'}
describe('local statement selection', () => {
  it('never caches statement data or queues statement writes', () => {
    for (const path of ['/api/reconciliation','/api/reconciliation/1','/api/reconciliation/1/rows/2','/api/reconciliation/1/summary.csv']) {
      const url=new URL(path,'https://gearcargo.invalid')
      expect(cacheablePrivateApi(url)).toBe(false)
      for (const method of ['POST','PUT','DELETE']) expect(isOfflineWrite(url,method,url.origin)).toBe(false)
    }
  })
  it('uploads only mapped selected data with explicit sign, dates and decimal conventions', () => {
    const parsed=parseStatementCsv('Date;Amount;Currency;Vendor;Private\r\n01/10/2026;-100,10;GBP;"Garage; A";ACCOUNT-SECRET\r\n02/10/2026;20,00;GBP;Refund;OTHER-SECRET\r\n03/10/2026;-50;GBP;PRIVATE-ROW;PRIVATE', ';')
    const rows=normalizeStatement(parsed,new Set([2,3]),mapping,settings)
    expect(rows).toEqual([{row_number:2,date:'2026-10-01',amount:'100.10',currency:'GBP',vendor:'Garage; A'},{row_number:3,date:'2026-10-02',amount:'-20.00',currency:'GBP',vendor:'Refund'}])
    expect(JSON.stringify(rows)).not.toContain('SECRET');expect(JSON.stringify(rows)).not.toContain('PRIVATE')
  })
  it('handles quoted newlines, doubled quotes, BOM and trailing empty cells', () => {
    expect(parseStatementCsv('\ufeffa,b,c\r\n"line\nnext","say ""yes""",').rows[0].cells).toEqual(['line\nnext','say "yes"',''])
  })
  it.each(['a,b\n"open,b','a,b\n"closed"junk,b','a,b\na"b,c','a,b\none'])('rejects malformed CSV %s', text=>expect(()=>parseStatementCsv(text)).toThrow())
  it.each(['1.001','NaN','Infinity','1,000.00','1e2','£10','100000000'])('rejects ambiguous or inexact amount %s', value=>expect(()=>cents(value)).toThrow())
  it('uses exact signed cents including the maximum stored value',()=>{
    expect(money(cents('0.10')+cents('0.20'))).toBe('0.30')
    expect(money(cents('-99999999.99'))).toBe('-99999999.99')
  })
  it('rejects invalid dates and missing currency mapping',()=>{
    const parsed=parseStatementCsv('Date,Amount,Currency,Vendor\n31/02/2026,10,GBP,A')
    expect(()=>normalizeStatement(parsed,new Set([2]),mapping,settings)).toThrow()
    expect(()=>normalizeStatement(parsed,new Set([2]),{...mapping,currency:''},settings)).toThrow('mappingRequired')
  })
  it('translates all feature keys',()=>{
    expect(Object.keys(translations.ro.reconciliation).sort()).toEqual(Object.keys(translations.en.reconciliation).sort())
    expect(Object.keys(translations.es.reconciliation).sort()).toEqual(Object.keys(translations.en.reconciliation).sort())
  })
})
