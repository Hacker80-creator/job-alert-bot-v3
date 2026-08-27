# Bangalore Product Company DS/Analytics Job Alert Bot v3

This bot checks official company career feeds every 30 minutes and sends matching jobs to Discord.

## What this version does

- Discord notifications, not Telegram.
- Runs every 30 minutes using GitHub Actions.
- Product-company allowlist only.
- Includes IQVIA as an approved healthcare-data exception because you explicitly asked for it.
- Official careers pages / ATS feeds are the primary source.
- Indeed support exists as an optional fallback, but it is disabled in the production workflow.
- LinkedIn and Naukri are not scraped by default because they often require login, block automation, and are unreliable from GitHub Actions.
- Filters for Bangalore / Bengaluru / Remote India.
- Adds strict resume-aware matching for data engineering, MLOps, DevOps, platform, build/release, automation, and compute-operations roles.
- Scores jobs using title + location + description + skills + early-career signal.
- Rejects senior / principal / lead / manager roles.
- Gives a small priority boost to companies marked with better work-life-balance priority.
- Shows an expected INR CTC range; employer-posted pay is used when available, otherwise it is clearly marked as an estimate.
- Prevents duplicate alerts through `state/seen_jobs.json`.

- Uses company_allowlist.txt as a broad, restricted secondary-company universe.

## Important reality check

This is not magic. Official ATS APIs like Greenhouse, Lever, Ashby, SmartRecruiters and some Workday endpoints are reliable. Dynamic pages, LinkedIn and Indeed can break or block requests. The bot logs failures and continues instead of crashing.

The supplied company list contains 794 approved names, but approval is not the same as source coverage. The production registry currently has 262 enabled direct sources, including first-party Dell Technologies and Intel feeds. Names without a configured direct source are not scanned while `ENABLE_INDEED` is `false`. CGI's Njoyn site can block cloud requests, so CGI is best-effort.

Work-life balance is only a ranking signal. It is not a guarantee because WLB depends heavily on team, manager, project and deadline pressure.

Salary ranges are guidance for 0-3 year Bengaluru / Remote India candidates, not an offer or employer guarantee. Alerts label official posted compensation as `Posted` and market estimates as `Est.`

## Setup

### 1. Create a Discord webhook

1. Open Discord.
2. Create a private server or use your existing server.
3. Create a channel, for example `job-alerts`.
4. Go to channel settings.
5. Open **Integrations**.
6. Open **Webhooks**.
7. Click **New Webhook**.
8. Copy the webhook URL.

Keep the webhook secret. Anyone with it can post to your channel.

### 2. Upload this project to GitHub

Create a public GitHub repository, for example:

```text
bangalore-product-job-alerts
```

Upload all files and folders from this ZIP, including:

```text
.github/workflows/job-alerts.yml
companies.yaml
job_monitor.py
requirements.txt
state/seen_jobs.json
```

### 3. Add the Discord secret

In GitHub repository:

```text
Settings → Secrets and variables → Actions → New repository secret
```

Add:

```text
Name: DISCORD_WEBHOOK_URL
Secret: paste your Discord webhook URL
```

### 3a. Add the Gemini API secret for tailored resume attachments

Create a Gemini Developer API key in Google AI Studio, then add one more
repository secret:

```text
Name: GEMINI_API_KEY
Secret: paste your Gemini API key
```

Production uses `gemini-3.6-flash` first and automatically falls back to
`gemini-3.5-flash-lite`. Both support structured output. The committed
`resume/master_resume.docx` is the immutable formatting and factual source;
every alert edits a copy and attaches the generated DOCX without suppressing
the normal job card if tailoring fails. Free-tier Gemini requests are subject
to Google project quotas and may be used by Google to improve its products.

Manual runs from a non-`main` branch send one clearly labeled resume integration
test only. They do not scan companies or update the production deduplication
state. After the branch test succeeds, merge it and run `main` manually once.

### 4. Allow state saving

In GitHub repository:

```text
Settings → Actions → General → Workflow permissions
```

Select:

```text
Read and write permissions
```

Save.

### 5. Run manually once

Open:

```text
Actions → Bangalore product data job alerts → Run workflow
```

The workflow will then run automatically every 30 minutes at minute 7 and minute 37 of each hour.

## Customization

Open `companies.yaml`.

### Add a product company

Add entries like this for Greenhouse:

```json
{"name":"Example Product Co","kind":"product","wlb_score":4,"ats":"greenhouse","slug":"example","enabled":true}
```

For Lever:

```json
{"name":"Example Product Co","kind":"product","wlb_score":4,"ats":"lever","slug":"example","enabled":true}
```

For Ashby:

```json
{"name":"Example Product Co","kind":"product","wlb_score":4,"ats":"ashby","slug":"ExampleBoard","enabled":true}
```

If you only know the careers URL and not the ATS, use fallback:

```json
{"name":"Example Product Co","kind":"product","wlb_score":4,"ats":"html_search","url":"https://example.com/careers","enabled":true}
```

HTML fallback is weaker than ATS APIs.

### Disable a company

Set:

```json
"enabled": false
```

### Change filtering strictness

In `.github/workflows/job-alerts.yml`, change:

```yaml
MIN_SCORE: "70"
```

Higher score = fewer alerts, better relevance.

Suggested values:

```text
65 = more alerts, more noise
70 = balanced
80 = strict
```

## Service-company exclusion

The bot does not broadly scan all employers. It only alerts from the approved allowlist in `companies.yaml`, so service companies are excluded unless you add them manually.

## About LinkedIn / Indeed

Indeed is available as a best-effort secondary search and is filtered against the approved company list, but it is disabled in the production workflow because scraping is unreliable.

LinkedIn is not scraped by default. Trying to scrape LinkedIn from GitHub Actions is a bad idea: it is unreliable, login-heavy, and likely to get blocked. Use official company pages as primary source. That is the right architecture.

## Local test

Optional:

```bash
pip install -r requirements.txt
DISCORD_WEBHOOK_URL="your webhook" python job_monitor.py
```

On Windows PowerShell:

```powershell
$env:DISCORD_WEBHOOK_URL="your webhook"
python job_monitor.py
```
