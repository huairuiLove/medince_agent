import type { AgentConfigInfo } from '@/types'

/** 将 skill_id 映射为中文专长名称（医生可见文案） */
export function skillTitle(agent: AgentConfigInfo, skillId: string): string {
  const meta = agent.available_skills?.find(s => s.skill_id === skillId)
  return meta?.title || skillId
}

/** 已启用专长的中文名称列表 */
export function enabledSkillTitles(agent: AgentConfigInfo): string[] {
  return (agent.enabled_skills ?? []).map(id => skillTitle(agent, id))
}

/** 是否科室专科 Agent */
export function isDepartmentAgent(agent: AgentConfigInfo): boolean {
  return Boolean(agent.is_department_agent)
}
