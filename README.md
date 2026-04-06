# IBKR Gateway Monitor

Monitors IB Gateway health and automatically restarts it via [IBC](https://github.com/IbcAlpha/IBC) when it crashes. IBC handles the login dialog so no manual credential entry is needed.

## How it works

- `monitor.py` probes the Gateway API port every 10 seconds
- After 3 consecutive failures, it triggers a restart
- `launcher.py` kills the old process, then starts Gateway via IBC in a Terminal.app window (required for the Java GUI)
- IBC enters your username/password into the login dialog automatically
- Exponential backoff between restart attempts (60s → 10min cap), up to 10 retries

## Setup

### 1. Install IB Gateway

Download from [IBKR](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php). Default install path: `~/Applications/IB Gateway <version>`.

### 2. Install IBC

Download from [IBC releases](https://github.com/IbcAlpha/IBC/releases). Extract and make scripts executable:

```bash
mkdir -p ~/opt/ibc
cp -R ~/Downloads/IBCMacos-*/* ~/opt/ibc/
chmod +x ~/opt/ibc/scripts/*.sh ~/opt/ibc/*.sh
```

### 3. Configure

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` with your IBKR credentials and paths.

### 4. Run

```bash
python3 monitor.py
```

Single health check:

```bash
python3 monitor.py --check
```

Start/stop Gateway manually:

```bash
python3 launcher.py start
python3 launcher.py stop
python3 launcher.py status
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `IBKR_HOST` | `127.0.0.1` | Gateway host |
| `IBKR_PORT` | `4002` | Gateway API port (4001=live, 4002=paper) |
| `IBKR_TRADING_MODE` | `paper` | `paper` or `live` |
| `IBKR_USERNAME` | | IB account username |
| `IBKR_PASSWORD` | | IB account password |
| `IBC_PATH` | `~/opt/ibc` | Path to IBC installation |
| `IB_GATEWAY_PATH` | `~/Applications/IB Gateway 10.44` | Path to IB Gateway |

## Requirements

- macOS (uses Terminal.app for GUI context)
- Python 3.9+
- `python-dotenv` (`pip install python-dotenv`)
