# Athena Shield — Security Command Center Frontend

A modern cybersecurity operations console for **Athena Shield**, providing defense in depth for SecureAI Guard.

## Technology Stack

- **Framework**: React 19 + TypeScript + Vite 6
- **Styling**: Tailwind CSS v4 + Custom Graphite Cyber Design System
- **Icons**: Lucide React
- **Architecture**: Bounded session state, live polling, side-by-side verification, interactive Attack Lab

## Quick Start

### 1. Start the Backend API (FastAPI)
From the repository root:
```bash
# In virtualenv
python api.py
# Running on http://127.0.0.1:8000
```

### 2. Start the Frontend Dev Server
From the `frontend` directory:
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### 3. Production Build
```bash
cd frontend
npm run build
```
Build output is generated in `frontend/dist/`.

## Environment Configuration

Configure `frontend/.env` if you need to point to a remote or non-standard backend URL:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

By default in development mode, Vite automatically proxies `/api`, `/health`, and `/ready` to `http://127.0.0.1:8000`.

## Console Views & Capabilities

1. **Security Overview (`/`)**: High-level posture metrics, real-time activity feed, engine status, and interactive processing pipeline.
2. **Live Analyzer (`#live-analyzer`)**: Primary side-by-side comparator between raw SecureAI Guard verdicts and Athena Shield's four-layer inspection. Features deep inspection traces, normalization diffs, and safe decoded representation viewers.
3. **Attack Lab (`#attack-lab`)**: Synthetic scenario workbench demonstrating 4 core vulnerability classes (Character Obfuscation, Context Confusion, Multi-Turn Session Assembly, Encoded Payloads) without generating harm.
4. **Session Shield (`#session-shield`)**: Interactive multi-turn simulator illustrating how benign-looking fragments assemble into attacks over time, tracking risk trajectory with cumulative scoring.
5. **Event Stream (`#event-stream`)**: SOC-style real-time event log with multi-engine filtering, text search, severity breakdowns, and metadata-only JSON export.
6. **Research & Findings (`#findings`)**: Clear, evidence-backed vulnerability cards for competition judges and technical evaluation.
