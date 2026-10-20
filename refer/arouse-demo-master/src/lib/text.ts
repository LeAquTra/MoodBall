/**
 * 轻量文本工具：归一化 + 编辑距离。
 * 语音识别结果常带空格与标点，指令匹配前先统一成「小写无标点」形态。
 */

const NON_WORD = /[^\p{L}\p{N}]/gu

export function normalize(input: string): string {
  return input.toLowerCase().replace(NON_WORD, '')
}

export function levenshtein(a: string, b: string): number {
  if (!a.length) return b.length
  if (!b.length) return a.length

  let previous = Array.from({ length: b.length + 1 }, (_, index) => index)
  const current = new Array<number>(b.length + 1)

  for (let i = 1; i <= a.length; i++) {
    current[0] = i
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
    }
    previous = [...current]
  }

  return previous[b.length]
}

export function similarity(a: string, b: string): number {
  if (!a.length || !b.length) return 0
  return 1 - levenshtein(a, b) / Math.max(a.length, b.length)
}
