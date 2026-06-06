# 🚀 Deployment Guide: Botamin BI on GitHub Pages

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────┐
│                     GitHub Repository                          │
│  ┌────────────────────┐  ┌──────────────────────────────────┐  │
│  │ frontend/          │  │ Data Pipeline (Python)            │  │
│  │   React SPA        │  │ ──────────────────────────────── │  │
│  │   (builds to dist) │  │ Google Sheets/CSV → JSON          │  │
│  │                    │  │ Output: frontend/public/data/    │  │
│  │   public/data/     │←─│   - dashboard.json               │  │
│  │   (JSON served)    │  │   - calls/index.json             │  │
│  └────────────────────┘  │   - calls/page_*.json            │  │
│                          └──────────────────────────────────┘  │
└───────────────────────────────────┬───────────────────────────────┘
                                    │ git push
                                    ↓
┌───────────────────────────────────────────────────────────────┐
│                    GitHub Actions (CI/CD)                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 1. Checkout repo                                         │ │
│  │ 2. Set up Python + Node.js                              │ │
│  │ 3. Run pipeline (if data source changed)                │ │
│  │ 4. Build React frontend                                  │ │
│  │ 5. Deploy to GitHub Pages                                │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────┬───────────────────────────────┘
                                    │
                                    ↓
┌───────────────────────────────────────────────────────────────┐
│                    GitHub Pages + Fastly CDN                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Static site: username.github.io/Botamin/                 │ │
│  │ - React SPA + JSON data files                           │ │
│  │ - Automatic HTTPS                                        │ │
│  │ - Edge caching via Fastly                                │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

## Why GitHub Pages?

| Feature | GitHub Pages | Netlify | Vercel |
|---------|--------------|---------|--------|
| **Cost** | ✅ Free | Free (limited) | Free (limited) |
| **Build minutes** | ✅ Unlimited (Actions) | 300/min | 6000/min |
| **Custom domain** | ✅ Free | Free | Free |
| **HTTPS** | ✅ Automatic | Automatic | Automatic |
| **CDN** | ✅ Fastly | Netlify Edge | Vercel Edge |
| **Python in CI** | ✅ Native | Requires config | Requires config |
| **Integration** | ✅ Native | External | External |

**Verdict**: GitHub Pages is ideal for this project — completely free, unlimited build minutes, and seamless integration with GitHub Actions for the Python pipeline.

## Prerequisites

### Required
- **GitHub account** with repository for this project
- **Google Sheets** or CSV file as data source

### Local Setup
```bash
# Clone repository
git clone https://github.com/<username>/Botamin.git
cd Botamin

# Python environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend dependencies
cd frontend
npm install
```

## Step 1: Enable GitHub Pages

### 1.1 Repository Settings

1. Go to repository → **Settings** → **Pages**
2. **Source**: Select "GitHub Actions" (important!)
3. **Custom domain** (optional): Add your domain in the "Custom domain" field

### 1.2 Update Repository Name

The base URL in `vite.config.ts` assumes the repo is named "Botamin":

```typescript
base: "/Botamin/"  // Matches repo name
```

If your repo has a different name, update this in `frontend/vite.config.ts`:

```typescript
base: "/your-repo-name/"  // Change this
```

## Step 2: Connect Data Source

### Option A: Google Sheets

1. Share your Google Sheet with "Anyone with link can view"
2. Copy the share URL

### Option B: Local CSV File

```bash
# Place data file in repository
cp your-data.csv data/raw.csv
git add data/raw.csv
git commit -m "Add data source"
git push
```

## Step 3: Configure Environment (Optional)

Add secrets for LLM features:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add secrets:
   - `ANTHROPIC_API_KEY` — For Claude (Tier 2 analysis)
   - `ZAI_API_KEY` — For Z.ai (Tier 2 alternative)

## Step 4: Deploy

### First Deployment

```bash
# 1. Run pipeline locally to verify
python -m pipeline --file data/raw.csv

# 2. Commit everything
git add .
git commit -m "Initial deployment"
git push
```

This triggers GitHub Actions → automatic deploy to GitHub Pages.

### Access Your Site

```
https://<username>.github.io/Botamin/
```

Or with custom domain (if configured):
```
https://botamin.yourdomain.com/
```

## Data Update Strategies

### 1. Automatic (On Every Push)

Every push to `main` triggers:
- Pipeline runs (if `data/raw.csv` changed)
- Frontend builds
- Deploys to GitHub Pages

```bash
# Update data and push
cp new-data.csv data/raw.csv
git add data/raw.csv
git commit -m "Update data"
git push
```

### 2. Manual with Custom Parameters

1. Go to **Actions** tab in GitHub
2. Select "Build and Deploy" workflow
3. Click "Run workflow"
4. Fill parameters:
   - `sheet_url`: Google Sheets URL (optional)
   - `file_path`: CSV path (default: `data/raw.csv`)
   - `llm_scope`: `off` | `focus` | `full` | `sample`

### 3. Scheduled Updates

Create `.github/workflows/scheduled-data.yml`:

```yaml
name: Scheduled Data Update

on:
  schedule:
    - cron: '0 */4 * * *'  # Every 4 hours
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install -r requirements.txt
      - run: python -m pipeline --sheet "$SHEET_URL"
        env:
          SHEET_URL: ${{ secrets.SHEET_URL }}
      - run: |
          git config user.name "github-actions[bot]"
          git add frontend/public/data/
          git commit -m "chore: scheduled data update [skip ci]"
          git push
```

## Troubleshooting

### 404 on Page Refresh

**Problem**: Refreshing a page (e.g., `/calls`) shows 404

**Solution**: Verify GitHub Pages source is set to "GitHub Actions", not "Deploy from a branch"

```
Settings → Pages → Build and deployment → Source: GitHub Actions
```

### Assets Not Loading

**Problem**: JS/CSS files return 404

**Solution**: Check `vite.config.ts` base path matches repo name

```typescript
// If repo is "my-bi-app", use:
base: "/my-bi-app/"
```

### Data Not Updating

**Problem**: Changes to `data/raw.csv` don't reflect on site

**Solution**: Check Actions tab — did workflow run? Look for red ❌

```bash
# Check if data files are in git
git ls-files frontend/public/data/

# Should show:
# frontend/public/data/dashboard.json
# frontend/public/data/calls/index.json
# frontend/public/data/calls/page_*.json
```

### Build Fails in Actions

**Problem**: Build error in GitHub Actions

**Common causes**:
1. **Node version mismatch**: Check `NODE_VERSION` in workflow
2. **Python dependency error**: `requirements.txt` changed?
3. **TypeScript error**: Local build passes but remote fails?

```bash
# Test build locally
cd frontend
npm ci --legacy-peer-deps
npm run build
```

## Performance at Scale

### Current Setup (11,000+ calls)

```
Storage per deploy: ~90MB
- index.json: 1.5MB
- 220 pages × 400KB: 88MB
- dashboard.json: 55KB
```

### GitHub Pages Limits

| Resource | Limit | Notes |
|----------|-------|-------|
| Repository size | 1GB soft, 5GB hard | Plenty of headroom |
| Bandwidth | 100GB/month | ~10,000 pageviews |
| Build time | Unlimited (Actions) | 2000 min/month free |

### Future Scaling (>50GB/month)

**Options**:
1. **Netlify/Vercel** — More generous bandwidth
2. **Cloudflare Pages** — Unlimited bandwidth
3. **CDN proxy** — Cloudflare in front of GitHub Pages

## Custom Domain (Optional)

### 1. Add Domain in GitHub

Settings → Pages → Custom domain → Add your domain

### 2. Configure DNS

At your DNS provider, add:

| Type | Name | Value |
|------|------|-------|
| CNAME | www | `<username>.github.io |
| CNAME | @ | `<username>.github.io |

### 3. HTTPS (Automatic)

GitHub provisions SSL certificate automatically. Takes 5-30 minutes.

## Security Checklist

- [ ] `.env` NOT in git (use GitHub Secrets)
- [ ] API keys in Secrets, not code
- [ ] Google Sheets shared "view only"
- [ ] Repository private (if sensitive data)
- [ ] Regular dependency updates

## Cost Breakdown

### Current (Free Tier)

| Service | Cost | What you get |
|---------|------|--------------|
| GitHub Pages | $0 | Hosting, SSL, CDN |
| GitHub Actions | $0 | 2000 min/month builds |
| Google Sheets | $0 | Up to 10M cells |

### Total: **$0/month** ✅

### When to Pay

| Trigger | Solution | Cost |
|---------|----------|------|
| >2000 min builds | GitHub Pro | $4/мес |
| >100GB bandwidth | Cloudflare proxy | $0 |
| Custom domain | Already free | $0 |

## Quick Start Commands

```bash
# Local development
cd frontend
npm run dev

# Run pipeline locally
python -m pipeline --file data/raw.csv

# Build for production
npm run build

# Deploy (just push)
git push
```

---

**Live site**: `https://<username>.github.io/Botamin/`
**Status**: `https://github.com/<username>/Botamin/deployments`
**Actions**: `https://github.com/<username>/Botamin/actions`
