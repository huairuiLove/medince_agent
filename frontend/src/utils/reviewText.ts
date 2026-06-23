/** Strip legacy conservative-degradation phrasing from stored or cached review text. */
export function sanitizeReviewText(text: string): string {
  return text
    .replace(/；?在未补全前应采用保守策略。?/g, '')
    .replace(/；?规则库未命中时由 DDI 小模型补充拦截。?/g, '')
    .replace(/建议人工复核；规则库未命中时由 DDI 小模型补充拦截。?/g, '建议人工复核并查阅说明书。')
    .replace(/\s{2,}/g, ' ')
    .trim()
}
