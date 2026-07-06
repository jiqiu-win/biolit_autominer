# Run daily PMC downloads in the cloud (PC can sleep)

Your Mac crontab **only works while the Mac is awake**. To download automatically without your PC:

| Option | Runs on | Cost | Best for |
|--------|---------|------|----------|
| **A. GitHub Actions** (recommended) | GitHub cloud | Free tier | Students — easiest setup |
| **B. AWS Lambda + EventBridge** | Amazon AWS | ~Free for small daily runs | If you want everything on AWS |
| **C. Mac crontab** | Your Mac | Free | Only if Mac is on at 00:01 |

---

## Important distinction

- **`pmc-oa-opendata`** = PMC's public S3 bucket (where full text **comes from**)
- **Your S3 bucket** = where **your** database, summaries, and downloaded `.txt` files are **stored** between cloud runs

The download script already reads from PMC's AWS bucket. You need a **separate cloud scheduler** to run the script without your Mac.

---

## Option A — GitHub Actions (easiest, no PC awake)

### 1. Push code to GitHub

```bash
cd ~/Downloads/biolit_autominer
git push origin main
```

### 2. Add secrets (GitHub repo → Settings → Secrets and variables → Actions)

| Secret | Value |
|--------|--------|
| `NCBI_EMAIL` | `jq2430@columbia.edu` |
| `NCBI_API_KEY` | your NCBI API key |

Optional — save outputs to **your** AWS S3 bucket:

| Secret | Value |
|--------|--------|
| `BIOLIT_S3_BUCKET` | your bucket name |
| `AWS_ACCESS_KEY_ID` | IAM user key |
| `AWS_SECRET_ACCESS_KEY` | IAM secret |

### 3. Workflow file (already in repo)

`.github/workflows/daily_pmc_aws.yml` runs daily at **~00:01 AM Eastern** (04:01 UTC).

Manual test: GitHub → **Actions** → **Daily PMC AWS Download** → **Run workflow**.

### 4. Get results

- **Actions → latest run → Artifacts** → download `pmc-daily-*.zip` (summary JSON, xlsx, txt files)
- If S3 configured: files also at `s3://YOUR_BUCKET/biolit_autominer/`

### 5. Disable Mac crontab (optional)

```bash
crontab -e
# delete the line, save with :wq
```

---

## Option B — AWS Lambda + EventBridge (pure AWS)

### Overview

```
EventBridge (cron daily)
    → Lambda (runs run_daily_pmc_aws_cloud.py logic)
        → reads PMC text from pmc-oa-opendata (public)
        → saves state to YOUR S3 bucket
```

### 1. Create an S3 bucket (your data)

Example: `biolit-autominer-jqiu` in `us-east-1`

### 2. Create IAM role for Lambda

Permissions: `s3:GetObject`, `s3:PutObject` on your bucket; basic Lambda execution.

### 3. Deploy Lambda

- Runtime: Python 3.11
- Handler: `infra.aws.lambda_handler.handler`
- Package: zip project + `pip install -t package .`
- Timeout: 10–15 minutes
- Memory: 512 MB+
- Environment:
  ```
  NCBI_EMAIL=jq2430@columbia.edu
  NCBI_API_KEY=...
  BIOLIT_S3_BUCKET=biolit-autominer-jqiu
  BIOLIT_S3_PREFIX=biolit_autominer
  PMC_DAILY_LIMIT=50
  ```

### 4. EventBridge rule

- Schedule: `cron(1 0 * * ? *)` for 00:01 UTC daily (adjust for your timezone)
- Target: your Lambda function

### 5. Download results from your bucket

```
s3://biolit-autominer-jqiu/biolit_autominer/articles_database.xlsx
s3://biolit-autominer-jqiu/biolit_autominer/summaries/2026-06-30_summary.json
s3://biolit-autominer-jqiu/biolit_autominer/pmc_staging/*.txt
```

---

## Option C — Mac crontab (current setup)

Works only if Mac is **awake** at 00:01. Good as backup, not for "PC off" requirement.

---

## Sync state between cloud and Mac

When you open your Mac later, pull latest from your S3 bucket:

```bash
export BIOLIT_S3_BUCKET=your-bucket-name
export BIOLIT_S3_PREFIX=biolit_autominer
python -c "
from biolit_autominer.config import config
from biolit_autominer.cloud_state import restore_state
config.setup()
restore_state()
"
```

Or download artifacts from GitHub Actions.

---

## Recommended path for you

1. **Use GitHub Actions** first (already configured in this repo)
2. Add `NCBI_EMAIL` and `NCBI_API_KEY` secrets
3. Push to GitHub
4. Remove Mac crontab if cloud runs work
5. Add S3 secrets later if you want long-term storage on AWS
