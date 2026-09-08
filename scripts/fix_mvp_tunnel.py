from sshutil import load_env, run, ssh_connect

c = ssh_connect(load_env())
cmd = """
grep -q 'protocol http2' /etc/systemd/system/mvp1-tunnel.service || \
  sed -i 's|--no-autoupdate|--no-autoupdate --protocol http2|' /etc/systemd/system/mvp1-tunnel.service
systemctl daemon-reload
systemctl restart mvp1-tunnel
sleep 15
grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' /opt/mvp_1/cloudflared.log | tail -1
tail -3 /opt/mvp_1/cloudflared.log
"""
_, t = run(c, cmd, timeout=60)
print(t)
c.close()
