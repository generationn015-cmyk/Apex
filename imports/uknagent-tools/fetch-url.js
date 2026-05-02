const TOOL_NAME = 'fetch_url';
const TOOL_DESCRIPTION = 'Fetch and extract readable text content from a URL. Use for summarizing articles, docs, or any web page.';
const TOOL_SCHEMA = {
  type: 'object',
  properties: {
    url: { type: 'string', description: 'The full URL to fetch' },
  },
  required: ['url'],
};

async function execute({ url }) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
    const text = await res.text();
    const clean = text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 3000);
    return { url, content: clean };
  } catch (err) {
    return { url, error: err.message };
  }
}

module.exports = { TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, execute };
