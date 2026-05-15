# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python-based Instagram automation bot using Selenium WebDriver with GoLogin browser profiles. Runs on GCP VMs with virtual display (`pyvirtualdisplay`) and manages proxy rotation (SOAX/EVOMI providers).

## Run Commands

```bash
# Run the main script (entry point)
python src/index.py

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Entry Point Flow
`src/index.py` → `MainExecutor.execute()` → handles session init → login check → login → activities

### Key Components

**Session Management (`src/gologinHandlers.py`)**
- `GologinHandler` - manages GoLogin profiles, starts browser, connects Selenium driver
- Profile creation, proxy assignment, browser connection via debugger address

**Main Orchestration (`src/main.py`)**
- `MainExecutor` - coordinates login flow, activity execution, cleanup
- Task types: `LOGIN` (save profile image), `WARMUP` (browse explore), `START_CAMPAIGNING` (send DMs)
- Retry logic with `need_task_retry` flag for recoverable failures

**Webhook System (`src/utils/WebhookUtils.py`)**
- `WebhookUtils` - communicates with backend task system via HMAC-signed webhooks
- Task data received on init (`task_type`, `profile_id`, `proxy_*`, `attributes`)
- Status updates: `update_task_status`, `update_account_status`, `update_campaign_status`

**Browser Automation Scripts (`src/scripts/`)**
- `login.py` - Instagram login with 2FA support
- `browseExplore.py`, `exploreReel.py` - warmup activities
- `updateGoToMessages.py`, `goToMessages.py` - campaign messaging
- `goToProfile.py` - profile image saving

**Anti-Detection Utilities (`src/utils/scrapping/`)**
- `HumanMouseBehavior`, `HumanTypingBehavior` - simulate human interactions
- `ScreenObserver` - monitors for UI changes, dialogs, triggers driver revival
- `BandwidthManager` / `BandwidthTracker` - manage connection throttling

**Error Hierarchy (`src/utils/exceptions.py`)**
```
InstagramScrapingBaseError
├── UIChangeError (DOM locators invalid)
├── ScriptError (JS execution failed)
├── NavigationError
├── UserSearchError
├── MessageSendError / MessageRejectedError
├── GologinError / GologinConnectionError / GologinProfileNotFoundError
└── InstagramServerError (Instagram error banner)
```

## Key Patterns

**Driver Revival**: `ScreenObserver` monitors page health and calls `health_monitor.revive_driver()` on issues

**Proxy Fallbacks**: Cities tried sequentially with network readiness checks before proxy validation

**Login Flow**: Checks existing session → if not logged in, performs login → saves cookies post-login

**DM Campaign Retry**: Retries up to 5 times with `call_for_extra_dms` webhook to fetch more messages if some failed

## Configuration

All config via `.env` (see `src/config.py`):
- `GL_API_TOKEN` - GoLogin API token
- `WEBHOOK_SECRET` / `WEBHOOK_URL` - task backend communication
- `SOAX_*` / `EVOMI_*` - proxy provider credentials
- `HEARTBEAT_INTERVAL` - heartbeat frequency in seconds