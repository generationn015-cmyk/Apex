const { rememberFact } = require('../cognee');
const { saveFact } = require('../memory');

const TOOL_NAME = 'web_search';
const TOOL_DESCRIPTION = 'Search DuckDuckGo for information. Automatically saves results to memory when relevant.';
const TOOL_SCHEMA = {
  type: 'object',
  properties: {
    query: { type: 'string', description: 'The search query' },
    save_to_memory: { type: 'boolean', description: 'Save results to memory for future recall', default: true },
  },
  required: ['query'],
};

async function execute({ query, save_to_memory = true, chatId }) {
  try {
    const url = `https://api.duckduckgo.com/?q=${encodeURIComponent(query)}&format=json&no_html=1&skip_disambig=1`;
    const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
    const data = await res.json();

    const results = [];
    if (data.AbstractText) results.push(data.AbstractText);
    if (data.RelatedTopics) {
      for (const t of data.RelatedTopics.slice(0, 4)) {
        if (t.Text) results.push(t.Text);
      }
    }

    const summary = results.join('\n\n') || 'No results found.';

    if (save_to_memory && chatId && summary !== 'No results found.') {
      const fact = `Research on "${query}": ${summary.slice(0, 400)}`;
      await Promise.allSettled([
        saveFact(chatId, fact),
        rememberFact(fact, String(chatId)),
      ]);
    }

    return { query, results: summary };
  } catch (err) {
    return { query, error: err.message };
  }
}

module.exports = { TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, execute };
