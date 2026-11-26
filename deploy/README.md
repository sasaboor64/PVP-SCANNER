# Deploying on AWS Lightsail

One small Ubuntu server runs everything:

```
browser ──https──> Caddy (:443, automatic Let's Encrypt certificate)
                     ├── /        -> static frontend   (/opt/pvp-scanner/docs)
                     └── /api/*   -> FastAPI on 127.0.0.1:8000 (systemd service "pvp-scanner")
                                       └── DexScreener, Shrine, X, Claude API
```

Allow about 20 minutes. You need: the Lightsail instance (Ubuntu 22.04 or 24.04), a DuckDNS account, and a Claude API key.

## 1. Lightsail: static IP and firewall

In the Lightsail console, open your instance:

1. **Networking → Attach static IP.** Create one and attach it, so the address survives reboots. Note the IP.
2. **Networking → IPv4 Firewall → Add rule → HTTPS (TCP 443).** HTTP (80) and SSH (22) are open by default; keep 80, Caddy needs it to get the certificate.

## 2. DuckDNS: point a name at the server

1. Sign in at https://www.duckdns.org.
2. Add a subdomain, e.g. `pvpscan` → `pvpscan.duckdns.org`.
3. Put the static IP in **current ip** and click **update ip**.

Check from your computer: `ping pvpscan.duckdns.org` should show the static IP. Because the IP is static, you don't need DuckDNS's update cron job.

## 3. Install

Open the instance's browser SSH (**Connect using SSH**) and run, with your own subdomain:

```bash
curl -fsSL https://raw.githubusercontent.com/sasaboor64/PVP-SCANNER/main/deploy/setup.sh \
  | sudo DOMAIN=pvpscan.duckdns.org BRANCH=main bash
```

If the code isn't merged into `main` yet, use the working branch in both places (the URL and `BRANCH=`).

The script installs Python, git and Caddy, clones the repo into `/opt/pvp-scanner`, installs dependencies, and starts two services: `pvp-scanner` (the API) and `caddy` (HTTPS and the frontend). It is safe to run again.

## 4. Add the Claude API key

1. Create a key at https://console.anthropic.com → API keys. Also set a monthly **spend limit** there as a second safety net.
2. On the server:
   ```bash
   sudo nano /etc/pvp-scanner.env          # fill in ANTHROPIC_API_KEY=sk-ant-...
   sudo systemctl restart pvp-scanner
   sudo bash /opt/pvp-scanner/deploy/check.sh
   ```
   `check.sh` confirms both services run, the HTTPS site answers, and sends one tiny Claude request (well under 1 cent). It should end with `status: ok`.

Never paste the key into chat, a commit or the frontend. It only lives in `/etc/pvp-scanner.env` (readable by root only).

## 5. Open the site

`https://pvpscan.duckdns.org`. The header should show a green dot and **AI review on**.

## Costs and limits (all in `/etc/pvp-scanner.env`)

| Setting | Default | Meaning |
|---|---|---|
| `PVP_AI_DAILY_BUDGET_USD` | `5` | Estimated Claude spend per UTC day. After it is reached, scans still work with keyword scoring only. |
| `PVP_SCANS_PER_IP` / `PVP_RATE_WINDOW_SECONDS` | `6` / `600` | Each visitor can start 6 scans per 10 minutes. |
| `PVP_MAX_CONCURRENT_SCANS` | `4` | Scans running at once; extra visitors wait up to 20 s, then get "busy". |
| `PVP_AI_MODEL` / `PVP_AI_EFFORT` | `claude-opus-5-5` / `medium` | Model and reasoning effort for the review. |

A scan reviews up to 12 candidates in one Claude call, roughly $0.05-0.10 with Opus 5.5. Verdicts are cached for 24 hours per token pair, so re-scans are cheaper. Restart after changing settings: `sudo systemctl restart pvp-scanner`.

## Day-to-day

```bash
sudo journalctl -u pvp-scanner -f          # live API logs (scans, AI cost per call)
sudo bash /opt/pvp-scanner/deploy/setup.sh # pull the latest code and restart
sudo bash /opt/pvp-scanner/deploy/check.sh # health check
sudo sqlite3 /var/lib/pvp-scanner/pvp_scans.sqlite3 'select * from ai_usage'   # AI spend per day (apt install sqlite3)
```

## Troubleshooting

- **Site doesn't load / certificate error:** check that port 443 is open in the Lightsail firewall, the DuckDNS IP matches the static IP, then `sudo journalctl -u caddy -n 50`.
- **Red dot / "Offline":** `sudo systemctl status pvp-scanner` and `sudo journalctl -u pvp-scanner -n 50`.
- **"AI review off":** the key is missing from `/etc/pvp-scanner.env`, or the service wasn't restarted.
- **"AI review was unavailable":** look for `AI review failed` in the API logs; `check.sh` shows the exact error.
