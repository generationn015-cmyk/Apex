const TOOL_NAME = 'asset_risk_ops';
const TOOL_DESCRIPTION = 'Query Asset Risk Inc operational data — phlebotomist schedules, staff availability, and clinic performance metrics.';
const TOOL_SCHEMA = {
  type: 'object',
  properties: {
    action: {
      type: 'string',
      enum: ['get_schedule', 'get_staff', 'get_metrics'],
      description: 'The operation to perform',
    },
    date: { type: 'string', description: 'ISO date string (YYYY-MM-DD), defaults to today' },
  },
  required: ['action'],
};

async function execute({ action, date }) {
  // TODO: wire to Asset Risk database via ASSET_RISK_API_URL
  return {
    action,
    date: date || new Date().toISOString().split('T')[0],
    data: `${action} API not yet wired. Set ASSET_RISK_API_URL to enable live data.`,
  };
}

module.exports = { TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, execute };
