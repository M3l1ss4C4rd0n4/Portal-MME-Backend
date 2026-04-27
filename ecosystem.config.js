// pm2 ecosystem — Backend Portal Energético MME
// Inicio:   pm2 start ecosystem.config.js
// Guardar:  pm2 save
// Ver logs: pm2 logs api-mme  |  pm2 logs dash-mme

module.exports = {
  apps: [
    {
      name: 'api-mme',
      script: '/home/admonctrlxm/server/venv/bin/gunicorn',
      args: [
        'api.main:app',
        '--workers', '4',
        '--threads', '4',
        '--worker-class', 'uvicorn.workers.UvicornWorker',
        '--bind', '127.0.0.1:8000',
        '--timeout', '120',
        '--max-requests', '1000',
        '--max-requests-jitter', '100',
        '--access-logfile', 'logs/api-access.log',
        '--error-logfile', 'logs/api-error.log',
        '--log-level', 'info',
      ].join(' '),
      cwd: '/home/admonctrlxm/server',
      interpreter: 'none',
      watch: false,
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 20,
      min_uptime: '10s',
      env: {
        PYTHONPATH: '/home/admonctrlxm/server',
        PATH: '/home/admonctrlxm/server/venv/bin:/home/admonctrlxm/.local/bin:/usr/bin:/bin',
      },
      error_file: '/home/admonctrlxm/.pm2/logs/api-mme-error.log',
      out_file: '/home/admonctrlxm/.pm2/logs/api-mme-out.log',
      merge_logs: true,
    },
    {
      name: 'dash-mme',
      script: '/home/admonctrlxm/server/venv/bin/gunicorn',
      args: '-c gunicorn_config.py app:server',
      cwd: '/home/admonctrlxm/server',
      interpreter: 'none',
      watch: false,
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 20,
      min_uptime: '10s',
      env: {
        PYTHONPATH: '/home/admonctrlxm/server',
        PATH: '/home/admonctrlxm/server/venv/bin:/home/admonctrlxm/.local/bin:/usr/bin:/bin',
      },
      error_file: '/home/admonctrlxm/.pm2/logs/dash-mme-error.log',
      out_file: '/home/admonctrlxm/.pm2/logs/dash-mme-out.log',
      merge_logs: true,
    },
  ],
};
