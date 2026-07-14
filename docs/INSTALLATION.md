# INSTALLATION

Product: Flowza v1.0  
Version: Flowza v1.0.1

## Requirements

- Python 3.12
- Linux or compatible server runtime
- Telegram bot token

## Setup

1. Create virtual environment:
   - python3 -m venv .venv
2. Activate virtual environment:
   - source .venv/bin/activate
3. Install dependencies:
   - pip install -r requirements.txt

## Environment Configuration

Configure .env with:

- BOT_TOKEN
- OWNER_ID
- DATABASE
- LOG_LEVEL
- TIMEZONE

## Run

- .venv/bin/python bot.py

## Verification

- Compile check:
  - python3 -m py_compile $(find . -name '*.py' -not -path './.venv/*')
- Startup check:
  - .venv/bin/python bot.py
- Confirm startup logs and successful polling start.
