# 🎯 Botamin BI

> **Voice Agent Analytics Dashboard** — Transform raw call data into actionable insights with Python pipeline + React SPA

[![Build Status](https://github.com/Gorby200/Botamin-BI/actions/workflows/deploy.yml/badge.svg)](https://github.com/Gorby200/Botamin-BI/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-1310/)
[![React 19](https://img.shields.io/badge/react-19-61DAFB.svg)](https://react.dev)

---

## ✨ Overview

Botamin BI is a full-stack analytics platform for voice agent call centers. It processes conversation data through a deterministic analysis engine and optional LLM-powered insights, then presents results through an interactive React dashboard.

**Live Demo:** [https://gorby200.github.io/Botamin-BI/](https://gorby200.github.io/Botamin-BI/)

### Key Features

- **📊 Multi-dimensional Analytics** — Funnel analysis, voice quality, driver attribution, bottleneck detection
- **🤖 Three-tier LLM Architecture** — Batch screening, deep dive analysis, and research synthesis
- **🔍 Call-level Exploration** — Browse individual conversations with transcripts, stage markup, and audio playback
- **🎨 Modern UX/UI** — Clean design system with custom typography, motion animations, and responsive layouts
- **⚡ Optimized Performance** — Page-based data storage, LRU caching, and compact JSON for 11,000+ calls
- **🔧 Configurable Thresholds** — Live metric band adjustment without redeploys

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Data Layer                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ Google Sheets│───→│  Python      │───→│  JSON Files      │   │
│  │  / CSV       │    │  Pipeline    │    │  (public/data/)  │   │
│  └──────────────┘    │              │    └──────────────────┘   │
│                      │  • Deterministic│                           │
│                      │  • LLM Tier 1-3 │                           │
│                      └───────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend Layer                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  React 19 SPA + Tailwind 4 + Recharts + Motion           │  │
│  │                                                           │  │
│  │  Pages: Overview | Funnel | Voice Agent | Technical      │  │
│  │         Calls | CustDev | Backlog | Methodology | Settings│  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Deployment Layer                               │
│  GitHub Actions → Build → GitHub Pages + Fastly CDN             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.13+**
- **Node.js 20+**
- **Google Sheets** (or CSV/XLSX file) with call data

### 1. Clone and Install

```bash
git clone https://github.com/Gorby200/Botamin-BI.git
cd Botamin-BI

# Python environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend dependencies
cd frontend
npm install
```

### 2. Configure Environment

Create `.env` file in the root directory:

```bash
# Data source (Google Sheets URL or local file path)
SHEET_URL=https://docs.google.com/spreadsheets/d/...

# LLM Configuration (optional but recommended)
ANTHROPIC_API_KEY=sk-ant-...
ZAI_API_KEY=...

# LLM Analysis Scope
# Options: off | focus (default) | full | sample
LLM_SCOPE=focus

# Sample size for LLM (when scope=sample)
LLM_SAMPLE_SIZE=100

# CustDev prompt template
CUSTDEV_PROMPT="What are the top client objections?"
```

> **⚠️ Security:** Never commit `.env` to git. It's already in `.gitignore`.

### 3. Run Pipeline

```bash
# From Google Sheets
python -m pipeline --sheet "https://docs.google.com/spreadsheets/d/..."

# Or from local CSV/XLSX file
python -m pipeline --file data/raw.csv

# With specific LLM scope
python -m pipeline --file data/raw.csv --llm-scope full
```

### 4. Start Development Server

```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

---

## 📖 Documentation

### Data Format

The pipeline expects call data with the following columns:

| Column | Description | Required |
|--------|-------------|----------|
| `datetime` | Call timestamp | ✅ Yes |
| `duration_raw` | Duration (e.g., "2m 34s") | ✅ Yes |
| `status` | Call status (connected/failed) | ✅ Yes |
| `end_reason` | How the call ended | ✅ Yes |
| `dialogue` | Full conversation transcript | ✅ Yes |
| `audio_url` | Link to recording (optional) | No |

**Example:**
```csv
datetime,duration_raw,status,end_reason,dialogue,audio_url
2025-01-15 10:23,3m 12s,connected,meeting_agreed,"Bot: Hello... Client: Hi...",https://...
```

### LLM Integration

#### Three-tier Architecture

1. **Tier 1: Batch Screening**
   - Analyzes all calls for basic signals
   - Identifies candidates for deep analysis
   - Cost: ~$0.01 per 100 calls

2. **Tier 2: Deep Dive**
   - Detailed analysis of selected calls
   - Stage evidence, pattern detection, objections
   - Cost: ~$0.10-0.50 per call

3. **Tier 3: Research Synthesis**
   - Cross-call pattern discovery
   - Temporal analysis, failure clustering
   - Generates research.json

#### LLM Scopes

| Scope | Description | When to Use |
|-------|-------------|-------------|
| `off` | Deterministic only | Testing, no API key |
| `focus` | Dialogues with ≥3 client turns | **Default** - best value |
| `full` | All connected calls | Complete coverage |
| `sample` | Random sample (N=`LLM_SAMPLE_SIZE`) | Rapid prototyping |

### Pages Overview

| Page | Description |
|------|-------------|
| **Overview** | KPI dashboard with metric bands and health indicators |
| **Funnel** | Stage-by-stage conversion with drop attribution |
| **Voice Agent** | Dialogue quality metrics and patterns |
| **Technical** | ASR quality, connection metrics, instrumentation gaps |
| **Calls** | Individual call browser with transcripts |
| **CustDev** | Customer development insights + Tier 3 research |
| **Backlog** | Prioritized improvement hypotheses with A/B design |
| **Methodology** | Explanation of analysis approach and metrics |
| **Settings** | Threshold configuration and system status |

---

## 🔧 Configuration

### Metric Thresholds

Adjust metric bands in Settings or via `frontend/src/thresholds.ts`:

```typescript
const DEFAULT_THRESHOLDS: ThresholdOverride[] = [
  { key: "connect_rate", good: 0.85, ok: 0.70 },
  { key: "conversation_rate", good: 0.70, ok: 0.50 },
  { key: "meeting_rate", good: 0.25, ok: 0.15 },
  // ...
];
```

### Data Storage

The pipeline uses **page-based storage** for scalability:

```
frontend/public/data/
├── dashboard.json           # All metrics and KPIs
├── backlog.json             # Improvement hypotheses
├── custdev.json             # Customer insights
├── research.json            # Tier 3 findings (if available)
└── calls/
    ├── index.json           # Compact index (1-2MB)
    ├── page_000.json       # 50 calls per page (~400KB)
    ├── page_001.json
    └── ...
```

**At 11,000 calls:**
- ~220 page files instead of 11,000 individual files
- 98% reduction in file count
- Optimized for browser caching

---

## 🌐 Deployment

### GitHub Pages (Recommended)

Fully automated deployment via GitHub Actions:

1. **Enable Pages:** Settings → Pages → Source: `GitHub Actions`
2. **Add Secrets:** Settings → Secrets and variables → Actions → New repository secret
   - `ANTHROPIC_API_KEY` (optional, for LLM features)
   - `ZAI_API_KEY` (optional, alternative provider)
3. **Push:** Every push to `main` triggers automatic deployment

```bash
git add .
git commit -m "Update data"
git push
```

Access at: `https://gorby200.github.io/Botamin-BI/`

### Manual Data Updates

Use **Actions → Build and Deploy → Run workflow** with parameters:
- `sheet_url`: Google Sheets URL
- `file_path`: CSV path (e.g., `data/raw.csv`)
- `llm_scope`: `off` | `focus` | `full` | `sample`

For detailed deployment guide, see [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 📊 Project Structure

```
Botamin-BI/
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions CI/CD
├── config/                     # Configuration files
├── data/                       # Raw data cache
├── frontend/
│   ├── public/
│   │   └── data/              # Generated JSON (not in .gitignore)
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   ├── pages/             # Page components
│   │   ├── format.ts          # Formatting utilities
│   │   ├── hooks.ts           # Custom React hooks
│   │   ├── thresholds.ts     # Metric threshold logic
│   │   ├── types.ts           # TypeScript definitions
│   │   └── App.tsx            # Main app with routing
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts         # Build config with base path
├── pipeline/
│   ├── llm/                   # LLM orchestrator and tiers
│   ├── build.py               # Main pipeline entry point
│   ├── config.py              # Settings and env loading
│   ├── custdev.py             # CustDev generation
│   ├── diagnostics.py         # Pattern audits
│   ├── ingest.py              # Data ingestion
│   ├── metrics.py             # Metric computation
│   ├── profile.py             # Data profiling
│   └── stages.py              # Stage classification
├── .env.example               # Environment template
├── .gitignore
├── .gitattributes
├── requirements.txt
├── build.sh                   # Local build script
└── README.md
```

---

## 🔐 Security

### API Keys

**⚠️ CRITICAL:** API keys must NEVER be committed to the repository.

| Location | Purpose | Visibility |
|----------|---------|------------|
| `.env` (local) | Local development | ❌ In .gitignore |
| GitHub Secrets | CI/CD pipeline | ❌ Only repository owner |
| Repository code | ❌ NEVER | ✅ Public to all |

**How to add API keys securely:**

1. **For local development:** Create `.env` file (already in `.gitignore`)
   ```bash
   ANTHROPIC_API_KEY=sk-ant-...
   ZAI_API_KEY=...
   ```

2. **For GitHub Actions:**
   - Go to repository → **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**
   - Name: `ANTHROPIC_API_KEY`, Value: `sk-ant-...`
   - Repeat for `ZAI_API_KEY`

The workflow automatically injects these secrets as environment variables during pipeline execution.

### Data Privacy

- Ensure Google Sheets are shared with "view only"
- Consider **private repository** for sensitive call data
- Redact PII (personally identifiable information) from transcripts

---

## 🛠️ Development

### Running Locally

```bash
# Terminal 1: Watch data changes
python -m pipeline --file data/raw.csv

# Terminal 2: Dev server
cd frontend && npm run dev
```

### Building for Production

```bash
cd frontend
npm run build
# Output: frontend/dist/
```

### Running Tests

```bash
# Python tests (when available)
pytest

# Frontend tests (when available)
cd frontend
npm test
```

---

## 📈 Performance

### Optimizations Implemented

| Area | Technique | Impact |
|------|-----------|--------|
| **Data storage** | Page-based (50 calls/page) | 98% fewer files |
| **Memory** | LRU cache (20 pages) | ~10MB browser memory |
| **Loading** | pageHint from index | Avoids N+1 queries |
| **JSON** | Compact mode (`separators=(",", ":")`) | 30-50% smaller |
| **Routing** | Code splitting (lazy pages) | Faster initial load |

### Benchmarks (11,000 calls)

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Call detail load | ~610ms | ~100ms | **6x faster** |
| Index size | ~3MB | ~1.5MB | **50% reduction** |
| File count | 11,000+ | 220 | **98% reduction** |

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

1. **Virtual scrolling** for calls list at scale
2. **Web Worker** for client-side filtering
3. **Additional metrics** and visualizations
4. **Audio waveform** visualization
5. **Export functionality** (PDF, CSV)

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Make changes with clear commits
4. Test thoroughly
5. Submit a pull request

---

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- **Design System:** Custom typography with Hanken Grotesk + Fraunces variable fonts
- **Icons:** [Lucide React](https://lucide.dev/)
- **Charts:** [Recharts](https://recharts.org/)
- **Build:** Vite 8 + Tailwind CSS 4
- **LLM:** Claude (Anthropic) + Z.ai integration

---

## 📞 Support

- 📧 Issues: [GitHub Issues](https://github.com/Gorby200/Botamin-BI/issues)
- 📖 Documentation: [DEPLOYMENT.md](DEPLOYMENT.md)
- 💬 Discussions: [GitHub Discussions](https://github.com/Gorby200/Botamin-BI/discussions)

---

**Built with ❤️ for voice agent analytics**
