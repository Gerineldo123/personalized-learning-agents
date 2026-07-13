const TZ_PATTERN = /(Z|[+-]\d{2}:?\d{2})$/i
const CHINA_TIME_ZONE = 'Asia/Shanghai'

export function parseServerDate(value?: string | number | Date | null): Date | null {
  if (!value) return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'number') {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : date
  }

  const raw = String(value).trim()
  if (!raw) return null

  let normalized = raw
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(raw) && !TZ_PATTERN.test(raw)) {
    normalized = raw.replace(' ', 'T') + 'Z'
  }

  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatLocalDateTime(value?: string | number | Date | null): string {
  const date = parseServerDate(value)
  if (!date) return ''
  return date.toLocaleString('zh-CN', { hour12: false, timeZone: CHINA_TIME_ZONE })
}

export function formatLocalTime(value?: string | number | Date | null): string {
  const date = parseServerDate(value)
  if (!date) return ''
  return date.toLocaleTimeString('zh-CN', { hour12: false, timeZone: CHINA_TIME_ZONE })
}

export function formatRelativeTime(value?: string | number | Date | null): string {
  const date = parseServerDate(value)
  if (!date) return ''
  const diffMin = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000))
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH}小时前`
  return `${Math.floor(diffH / 24)}天前`
}

export function formatMessageTime(value?: string | number | Date | null): string {
  const date = parseServerDate(value)
  if (!date) return ''
  const nowParts = getChinaDateParts(new Date())
  const msgParts = getChinaDateParts(date)
  const today = Date.UTC(nowParts.year, nowParts.month - 1, nowParts.day)
  const msgDay = Date.UTC(msgParts.year, msgParts.month - 1, msgParts.day)
  const diffDays = Math.floor((today - msgDay) / 86400000)
  const hh = String(msgParts.hour).padStart(2, '0')
  const mm = String(msgParts.minute).padStart(2, '0')
  const time = `${hh}:${mm}`
  if (diffDays === 0) return `今天 ${time}`
  if (diffDays === 1) return `昨天 ${time}`
  return `${msgParts.month}/${msgParts.day} ${time}`
}

function getChinaDateParts(date: Date) {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: CHINA_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(date)
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value || 0)
  return {
    year: value('year'),
    month: value('month'),
    day: value('day'),
    hour: value('hour'),
    minute: value('minute'),
  }
}
