/** Dev proxy. /api/events is listed first so the stream is not swallowed by /api. E2E sets RD_API_TARGET. */
const api = {
  target: process.env.RD_API_TARGET || 'http://127.0.0.1:8000',
  secure: false,
  changeOrigin: true,
};

module.exports = {
  '/api/events': {
    ...api,
    timeout: 0,
    proxyTimeout: 0,
    configure(proxy) {
      proxy.on('proxyRes', (proxyRes) => {
        proxyRes.headers['cache-control'] = 'no-cache, no-transform';
        proxyRes.headers['x-accel-buffering'] = 'no';
      });
    },
  },
  '/api': api,
  '/healthz': api,
};
