# AI Deal Pipeline — Ahsan Habib

Live pipeline of AI-native, category-defining companies at pre-seed & seed stage.

🌐 **Live site:** `https://heyahsann.github.io/ark-deal-pipeline`

---

## What this is

An actively maintained, public-facing deal pipeline — updated daily as new companies are sourced. Built for transparency with fund partners and to signal deal flow quality to co-investors.

**Focus:** AI-native, category-defining companies at pre-seed and seed stage, primarily SF-based.

---

## How to add a new deal

Open `data/deals.json` and add a new entry following this template:

```json
{
  "id": "company-slug",
  "company": "Company Name",
  "tagline": "One sentence — what they do and why it matters",
  "description": "2-3 sentences. What they build, how it works, why now.",
  "stage": "Pre-seed",
  "status": "Tracking",
  "conviction": "High",
  "category": ["AI Agents", "Dev Tools"],
  "location": "San Francisco, CA",
  "founders": [
    { "name": "Founder Name", "role": "CEO & Co-Founder" }
  ],
  "website": "https://company.com",
  "linkedin": "https://www.linkedin.com/company/slug",
  "email": "founder@company.com",
  "traction": "X customers · Y ARR · notable signal",
  "source": "How you found them",
  "firstContact": "2026-05",
  "nextAction": "What happens next",
  "openQuestions": ["Question 1?", "Question 2?"],
  "accelerator": "YC / Antler / etc (optional)",
  "investors": ["Fund 1", "Fund 2"],
  "watchouts": "Any concerns (optional)"
}
```

**Status options:** `Tracking` · `Intro Made` · `First Meeting` · `Diligence` · `Term Sheet` · `Invested` · `Passed`

**Conviction options:** `High` · `Medium` · `Watch`

Commit and push — the site auto-deploys via GitHub Actions in ~60 seconds.

---

## Repo structure

```
ark-deal-pipeline/
├── index.html              ← the full website (single file)
├── data/
│   ├── deals.json          ← all deal entries (edit this daily)
│   └── coinvestors.json    ← co-investor network
├── .github/
│   └── workflows/
│       └── deploy.yml      ← auto-deploy to GitHub Pages
└── README.md
```

---

## Setup (first time)

1. Fork or clone this repo to your GitHub account
2. Go to **Settings → Pages → Source → GitHub Actions**
3. Push any change to `main` — the site deploys automatically
4. Your live URL will be: `https://[your-username].github.io/ark-deal-pipeline`

---

## Built by

Ahsan Habib · [heyahsann.github.io/heyahsan](https://heyahsann.github.io/heyahsan) · Sourcing AI-native deals at pre-seed & seed
