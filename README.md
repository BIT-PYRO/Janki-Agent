# Janki AI Backend

A FastAPI-based backend for the Janki AI voice support agent. This project powers knowledge-base FAQ handling, Vapi tool integration, and optional Shopify order/COD support.

## 🚀 Project Overview

`Janki AI Backend` is an AI agent backend for customer support workflows. It is designed to:

- ingest FAQ documents as a knowledge base
- answer customer questions using searchable support content
- provide a voice assistant system prompt for inbound calls
- trigger human handoff when needed
- optionally integrate with Shopify order lookup and COD workflows
- support Vapi tool-style requests for agent orchestration

## ✨ Features

- Knowledge-base ingestion from PDF
- FAQ question-answer API
- Vapi-compatible support endpoints
- voice-system prompt generation
- transfer-to-human action payloads
- optional Shopify order lookup / COD endpoints

## 📦 Requirements

- Python 3.10+
- Git
- Optional: Node.js 18+ for `index.js`
- Optional: `ngrok` for public webhook / Vapi testing

## 🛠️ Setup

1. Clone the repo:

```powershell
git clone <your-repo-url>
cd janki-ai-backend
```

2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

4. Create a `.env` file in the project root.

### Minimum environment variables for KB support

```env
APP_NAME=Janki Jewels Voice Support Backend
APP_ENV=development
APP_DEBUG=true
```

### Optional Shopify settings

```env
SHOPIFY_STORE=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=your_admin_api_access_token
SHOPIFY_API_VERSION=2024-01
SHOPIFY_TIMEOUT_SECONDS=20
SHOPIFY_DEFAULT_LIMIT=25
```

## ▶️ Run the API

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

If you need the package import path explicitly:

```powershell
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## ✅ API Endpoints

### Health check

```http
GET /support/health
```

### Upload knowledge base PDF

```http
POST /support/kb/upload
```

### Ask FAQ question

```http
POST /support/kb/ask
```

### Vapi-style KB query

```http
POST /support/kb/ask-vapi
```

### Get voice system prompt

```http
GET /support/prompt
```

### Transfer to human

```http
POST /support/transfer
```

## 📁 Optional Shopify endpoints

These endpoints are available only when Shopify env vars are configured.

- `POST /order`
- `POST /order/by-phone`
- `POST /cod/confirm`
- `GET /cod/pending-calls`

## 🧩 Vapi Integration

- See `vapi/SETUP.md` for Vapi onboarding.
- Update `vapi/tool_check_kb_answer.json` and `vapi/tool_transfer_to_human.json` with your deployed API URL.
- Use `ngrok http 8000` for publicly accessible webhook testing.

## 📘 GitHub Repository Setup

If you want to publish this project on GitHub:

```powershell
git init
git add .
git commit -m "Initial commit"
```

Then create a repository on GitHub and push:

```powershell
git remote add origin https://github.com/<your-username>/janki-ai-backend.git
git branch -M main
git push -u origin main
```

If you have GitHub CLI installed:

```powershell
gh repo create janki-ai-backend --public --source=. --remote=origin --push
```

## 🧪 Useful Commands

```powershell
# Run the API
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Check docs
http://127.0.0.1:8000/docs

# Freeze dependencies
pip freeze > requirements.lock.txt
```

## 💡 Notes

- The backend is built for AI-assisted customer support.
- It is resilient when Shopify is not configured.
- It supports both direct FAQ queries and Vapi-style tool call payloads.
- Use `.env` to keep secrets out of version control.
