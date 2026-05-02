const { recallFacts } = require('../cognee');
const { getFacts } = require('../memory');

const TOOL_NAME = 'search_memory';
const TOOL_DESCRIPTION = "Search Don's accumulated knowledge, stored facts, and conversation history. Use this before answering questions about Don's preferences, history, or past decisions.";
const TOOL_SCHEMA = {
  type: 'object',
  properties: {
    query: { type: 'string', description: 'What to search for in memory' },
  },
  required: ['query'],
};

async function execute({ query, chatId }) {
  const [cogneeResults, pgFacts] = await Promise.all([
    recallFacts(query, String(chatId)).catch(() => []),
    getFacts(chatId).catch(() => []),
  ]);

  return {
    knowledge_graph: cogneeResults.map(r => r.content || String(r)),
    stored_facts: pgFacts,
  };
}

module.exports = { TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, execute };
