import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: true,
})

const defaultLinkRender =
  md.renderer.rules.link_open ||
  function (tokens, idx, options, _env, self) {
    return self.renderToken(tokens, idx, options)
  }

md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
  const token = tokens[idx]
  if (token) {
    const href = token.attrGet('href')
    if (href) {
      token.attrSet('target', '_blank')
      token.attrSet('rel', 'noopener noreferrer')
    }
  }
  return defaultLinkRender(tokens, idx, options, env, self)
}

function stripFuncCalls(text: string): string {
  return text
    .replace(/<\s*function_calls\s*>[\s\S]*?<\/\s*function_calls\s*>/gi, '')
    .replace(/<\s*invoke\s+[^>]*>[\s\S]*?<\/\s*invoke\s*>/gi, '')
    .replace(/<\s*parameter\s+[^>]*>[\s\S]*?<\/\s*parameter\s*>/gi, '')
    .replace(/<\s*tool_call\s*>[\s\S]*?<\/\s*tool_call\s*>/gi, '')
    .trim()
}

export function renderMarkdown(raw: string): string {
  if (!raw) return ''
  const clean = stripFuncCalls(raw)
  if (!clean) return ''
  return DOMPurify.sanitize(md.render(clean))
}
