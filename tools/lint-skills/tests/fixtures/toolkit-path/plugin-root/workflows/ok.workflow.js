// ok.workflow.js: a line comment may name ~/.claude/agents.
/* A block comment may too,
 * ~/.claude/skills on a continuation line,
 * and ${HOME}/.claude/skills on another. */
/** A one-line block comment: ~/.claude/agents */
export const AGENT_NS = '';
const agentTypeFor = (name, ns) => (ns ? `${ns}:${name}` : name);
