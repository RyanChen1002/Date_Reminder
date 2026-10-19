# Date Reminder

This GitHub Actions job reads two read-only tabs from a Google Sheet and sends email reminders:

- `生日表`: sends an email on the person's birthday.
- `零食`: sends an email three days before the snack date.
- Every reminder email uses the subject `团契提醒` and includes a compact list of birthdays in the current month.

Dates are matched by month and day, so the same rows work every year. The program reads the latest sheet data each time it runs and never edits the Google Sheet or its formatting.

## How it runs

The workflow in `.github/workflows/daily-reminder.yml` runs once each day at 8:00 AM America/Chicago time:

```text
GitHub Actions → reminder.py → Google Sheet → Gmail email
```

If there is no reminder for the day, no email is sent.

## Important privacy rules

This repository should be private. Never commit any of the following:

- Gmail App Passwords or normal passwords
- Google OAuth tokens or private keys
- The full Google Sheet URL or spreadsheet ID
- `.env` files
- `reminder_date.xlsx` if it contains personal information

The local workbook is excluded by `.gitignore`. The spreadsheet ID and email credentials are entered as GitHub Actions repository secrets instead.

## One-time GitHub setup

### 1. Upload the safe project files

Push these files to the repository:

```text
reminder.py
requirements.txt
README.md
.gitignore
.github/workflows/daily-reminder.yml
```

Do not upload the local Excel workbook.

### 2. Create a Gmail App Password

Use a Gmail account that will send the reminders. Enable 2-Step Verification, then create an App Password named `Date Reminder` at:

<https://myaccount.google.com/apppasswords>

The App Password is not your normal Gmail password. Copy it when Google displays it; do not put it in this repository.

### 3. Add GitHub Actions secrets

In the GitHub repository, open:

```text
Settings → Secrets and variables → Actions → Secrets → New repository secret
```

Create these five repository secrets:

| Secret name | What to enter |
| --- | --- |
| `GOOGLE_SHEET_ID` | The ID between `/d/` and `/edit` in the Google Sheets URL |
| `SMTP_USERNAME` | The full Gmail address that owns the App Password |
| `SMTP_PASSWORD` | The Gmail App Password |
| `EMAIL_TO` | The email address that receives reminders |
| `EMAIL_FROM` | Usually the same address as `SMTP_USERNAME` |

Do not include quotation marks. For `GOOGLE_SHEET_ID`, enter only the ID, not the complete URL.

### 4. Test the workflow

Open:

```text
Actions → Daily date reminders → Run workflow
```

You can enter an optional test date such as `2026-10-20`. This test may send a real email, so use your own address first.

## Local dry run

The local dry run reads the sheet but does not send email:

```powershell
$env:GOOGLE_SHEET_ID = "your-spreadsheet-id"
& .venv\Scripts\python.exe reminder.py --date 2026-10-20 --dry-run
```

## Security notes

GitHub Actions secrets are referenced by the workflow only while the job runs. Do not print them in logs. Anyone with write access to a repository may be able to influence workflows, so keep this repository private and give access only to people you trust.

The Google Sheet must be readable by the CSV export used by the program. If the sheet is publicly readable, hiding its ID in GitHub does not make the sheet private; use authenticated Google Sheets API access if the data must be private.
