const { saveFact } = require('../memory');
const { rememberFact } = require('../cognee');

const TOOL_NAME = 'remember_fact';
const TOOL_DESCRIPTION = "Permanently store a fact, preference, or piece of information about Don for use in future sessions.";
const TOOL_SCHEMA = {
  type: 'object',
  properties: {
    fact: { type: 'string', description: 'The fact or information to remember' },
  },
  required: ['fact'],
};

async function execute({ fact, chatId }) {
  await Promise.allSettled([
    saveFact(chatId, fact),
    rememberFact(fact, String(chatId)),
  ]);
  return { ok: true, remembered: fact };
}

module.exports = { TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, execute };
