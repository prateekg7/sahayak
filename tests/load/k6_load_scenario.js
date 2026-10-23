import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 25 },  // Ramp up to 25 VUs
    { duration: '1m', target: 100 },  // Scale to 100 RPS
    { duration: '2m', target: 100 },  // Steady state at 100 RPS
    { duration: '30s', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<800'],  // 95% of requests must complete below 800ms
    http_req_failed: ['rate<0.01'],    // Error rate must remain under 1%
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';

export default function () {
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream, application/json',
      'Authorization': 'Bearer perf_test_token',
    },
  };

  // 1. Health check probe
  const healthResp = http.get(`${BASE_URL}/healthz`);
  check(healthResp, {
    'healthz status is 200': (r) => r.status === 200,
  });

  // 2. Cached MCP Tool Call (topic_brief)
  const toolPayload = JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: {
      name: 'topic_brief',
      arguments: { topic: 'General Science', length: 'short' },
    },
  });

  const toolResp = http.post(`${BASE_URL}/mcp`, toolPayload, params);
  check(toolResp, {
    'mcp tool call status is 200': (r) => r.status === 200,
  });

  sleep(1);
}
