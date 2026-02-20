# 🌾 PMFBY AI Agent — Crop Insurance CLI

> **Pradhan Mantri Fasal Bima Yojana** — An intelligent CLI tool that automates interactions with the [PMFBY website](https://pmfby.gov.in/) using browser automation and LLM-powered natural language understanding.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![Playwright](https://img.shields.io/badge/browser-Playwright-green.svg)
![LLM Powered](https://img.shields.io/badge/AI-LLM%20Powered-purple.svg)

---

## ✨ Features

| Task | Description |
|---|---|
| 🌿 **Insurance Application** | Fill the farmer registration / crop insurance form with step-by-step guidance |
| 💰 **Premium Calculator** | Calculate insurance premium for a given crop, season, state & area |
| 🔍 **Application Status** | Check application status using receipt or policy number |
| 📝 **Grievance Filing** | File complaints or report crop loss through the KRPH portal |
| 🗺️ **Site Explorer** | BFS traversal of the PMFBY site — builds a JSON sitemap |
| 📄 **Page Navigation** | Navigate to any page (FAQ, Contact, Sitemap, etc.) and extract content |
| ℹ️ **Scheme Info** | Get information about the PMFBY scheme, eligibility, and documents |

### Safety & Ethics
- **Never auto-submits** — all form submissions require explicit user confirmation
- **Mandatory 2–3s delays** between every browser action to respect the government server
- **CAPTCHA / OTP handoff** — pauses and hands control to the user for manual challenges
- **Screenshots** saved at key steps for audit and review

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│  pmfby_agent.py  (CLI Entry Point — argparse)   │
└──────────────────────┬──────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   agent/intent_parser.py  │  ← LLM classifies prompt → intent
         │   (OpenAI-compatible API) │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │     agent/planner.py      │  ← Maps intent → step sequence
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │     agent/executor.py     │  ← Runs steps via browser + handlers
         └──┬──────────────────────┬─┘
            │                      │
  ┌─────────▼─────────┐  ┌────────▼──────────┐
  │ browser/           │  │ tasks/             │
  │  controller.py     │  │  farmer_reg...     │
  │  (Playwright)      │  │  premium_calc...   │
  │                    │  │  application_...   │
  │  • navigate        │  │  grievance.py      │
  │  • fill / click    │  │  site_explorer.py  │
  │  • handoff_to_user │  │                    │
  └────────────────────┘  └────────────────────┘
```

**Flow:** `Prompt → Intent Parser (LLM) → Planner → Executor → Browser + Task Handlers → Results`

---

## 📋 Prerequisites

- **Python 3.10+**
- **An OpenAI-compatible API key** — works with OpenAI, Azure OpenAI, Groq, Ollama, or any provider exposing a `/v1/chat/completions` endpoint

---

## 🚀 Installation

```bash
# 1. Clone or navigate to the project
cd pmfby_agent

# 2. (Optional) Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser binaries
playwright install chromium

# 5. Configure your LLM API key
cp .env.example .env
# Edit .env with your API key
```

### `.env` Configuration

```env
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_ID=gpt-4o-mini
```

**Examples for other providers:**

| Provider | `LLM_BASE_URL` | `LLM_MODEL_ID` |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-70b-versatile` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3.1` |
| Azure OpenAI | `https://<name>.openai.azure.com/openai/deployments/<deploy>/` | `gpt-4o-mini` |

---

## 💻 Usage

```bash
python pmfby_agent.py --prompt "<your task>" [--no-headless] [--verbose]
```

### Arguments

| Flag | Short | Description |
|---|---|---|
| `--prompt` | `-p` | **(Required)** Natural language task description |
| `--no-headless` | | Run browser visibly — needed for CAPTCHA/OTP tasks |
| `--verbose` | `-v` | Enable debug output |

### Examples

```bash
# Fill the insurance application form (use --no-headless for OTP/CAPTCHA)
python pmfby_agent.py -p "help me fill the application form" --no-headless

# Calculate insurance premium
python pmfby_agent.py -p "calculate premium for wheat in Kharif season, Rajasthan, 5 hectares"

# Check application status
python pmfby_agent.py -p "check my application status using receipt number ABC123"

# File a grievance
python pmfby_agent.py -p "I want to report crop loss" --no-headless

# Explore the entire site and build a sitemap
python pmfby_agent.py -p "explore all pages on the pmfby website" -v

# Navigate to a specific page
python pmfby_agent.py -p "open the FAQ page"

# Get scheme information
python pmfby_agent.py -p "what documents are required for crop insurance?"
```

---

## 📁 Project Structure

```
pmfby_agent/
├── pmfby_agent.py              # CLI entry point (argparse)
├── requirements.txt            # Python dependencies
├── .env.example                # Environment config template
├── .gitignore
│
├── agent/                      # Core AI agent logic
│   ├── intent_parser.py        #   LLM-powered intent classification
│   ├── planner.py              #   Intent → action step planner
│   └── executor.py             #   Step executor / dispatcher
│
├── browser/                    # Browser automation layer
│   └── controller.py           #   Playwright wrapper with delays & handoff
│
├── tasks/                      # Task-specific handlers
│   ├── farmer_registration.py  #   Insurance application form
│   ├── premium_calculator.py   #   Premium calculation
│   ├── application_status.py   #   Status check
│   ├── grievance.py            #   KRPH grievance / crop loss
│   └── site_explorer.py        #   BFS site traversal & FAQ extraction
│
├── utils/                      # Shared utilities
│   ├── logger.py               #   Rich-based colored CLI output
│   └── helpers.py              #   Prompts, JSON, tables, CAPTCHA wait
│
├── tests/                      # (extensible test suite)
├── screenshots/                # Auto-generated screenshots (gitignored)
└── output/                     # JSON results & sitemap (gitignored)
```

---

## 🔧 How It Works

### 1. Intent Classification
Your natural language prompt is sent to the configured LLM with a few-shot system prompt. The LLM classifies it into one of 7 intents (`apply_insurance`, `calculate_premium`, `check_status`, `raise_grievance`, `traverse_site`, `navigate_page`, `get_info`) and extracts parameters (crop name, receipt number, state, etc.).

### 2. Action Planning
The classified intent is mapped to a sequence of executable steps. For example, `check_status` with `receipt_number=ABC123` produces:
```
Step 1: navigate → https://pmfby.gov.in/
Step 2: task → application_status.check_status(receipt_number=ABC123)
```

### 3. Browser Execution
The Playwright browser executes each step:
- **Navigation** with retry logic (3 attempts, exponential backoff)
- **Form filling** with human-like typing delays (50–120ms per keystroke)
- **Mandatory 2–3s delays** between every action
- **CAPTCHA/OTP handoff** — pauses automation and prompts the user to solve it in the browser

### 4. Results
- Structured results are printed to the terminal
- Saved as JSON to `output/last_run.json`
- Screenshots are saved to `screenshots/`

---

## ⚠️ Important Notes

- **Use `--no-headless`** for any task involving CAPTCHA or OTP (e.g., insurance application, grievance filing). The agent will pause and prompt you.
- **This is a government website** — the agent enforces mandatory delays and never spams requests.
- **Form submissions require explicit confirmation** — you'll always be asked before anything is submitted.
- **The PMFBY website structure may change** — selectors are designed to be resilient (multiple fallbacks), but updates may occasionally be needed.
- **Rate limiting / 503 errors** — the agent auto-retries with exponential backoff (up to 3 attempts).

---

## 🛠️ Extending the Agent

To add a new task:

1. **Create a handler** in `tasks/your_task.py` with a class that accepts `PMFBYBrowser` and has async methods.
2. **Register it** in `agent/executor.py` → `_get_handler()`.
3. **Add intent mapping** in `agent/intent_parser.py` → `INTENT_SCHEMA`.
4. **Add a planner** in `agent/planner.py` → create a `plan_your_task()` function and add it to `PLANNERS`.

---

## 📄 License

This project is provided as-is for educational and personal use. It interacts with a government portal — please use responsibly and in compliance with applicable laws and the website's terms of service.
