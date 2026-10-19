"""Send yearly birthday and snack-duty reminders from a public Google Sheet.

The program only reads the sheet's CSV export. It never writes to Google Sheets.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import smtplib
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DATE_RE = re.compile(r"^(?:(\d{4})[-/]?)?(\d{1,2})[月/-](\d{1,2})日?$|^(?:(\d{4})[-/])?(\d{1,2})/(\d{1,2})$")


@dataclass(frozen=True)
class Reminder:
    kind: str
    event_date: date
    name: str


def sheet_csv_url(sheet_id: str, sheet_name: str) -> str:
    query = urllib.parse.urlencode({"tqx": "out:csv", "sheet": sheet_name})
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?{query}"


def read_csv_sheet(sheet_id: str, sheet_name: str) -> list[list[str]]:
    request = urllib.request.Request(
        sheet_csv_url(sheet_id, sheet_name),
        headers={"User-Agent": "date-reminder/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8-sig")
    return [row for row in csv.reader(io.StringIO(text))]


def parse_month_day(value: str) -> tuple[int, int] | None:
    value = value.strip()
    if not value:
        return None

    match = DATE_RE.match(value)
    if not match:
        return None

    groups = match.groups()
    if groups[1] is not None:
        month, day = int(groups[1]), int(groups[2])
    else:
        month, day = int(groups[4]), int(groups[5])

    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return month, day


def reminders_from_sheet(rows: list[list[str]], kind: str, offset_days: int) -> list[Reminder]:
    reminders: list[Reminder] = []
    for row in rows:
        if len(row) < 2:
            continue
        month_day = parse_month_day(row[0])
        name = row[1].strip()
        if month_day is None or not name:
            continue

        month, day = month_day
        # The year is intentionally omitted: these are annual reminders.
        # Invalid dates, such as Feb 29 in a non-leap year, are skipped for
        # that year and will match again in the next leap year.
        try:
            event_date = date(2000, month, day)
        except ValueError:
            continue
        reminders.append(Reminder(kind, event_date, name))
    return reminders


def matches_today(reminder: Reminder, today: date) -> bool:
    target = today + timedelta(days=reminder_offset(reminder.kind))
    return (reminder.event_date.month, reminder.event_date.day) == (
        target.month,
        target.day,
    )


def reminder_offset(kind: str) -> int:
    return 3 if kind == "零食" else 0


def collect_reminders(sheet_id: str, today: date) -> list[Reminder]:
    birthday_rows = read_csv_sheet(sheet_id, "生日表")
    snack_rows = read_csv_sheet(sheet_id, "零食")
    reminders = reminders_from_sheet(birthday_rows, "生日", 0)
    reminders.extend(reminders_from_sheet(snack_rows, "零食", 3))
    return [reminder for reminder in reminders if matches_today(reminder, today)]


def make_message(reminders: list[Reminder], today: date) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"日期提醒 - {today.isoformat()}"
    lines = [f"今天是 {today.isoformat()}，提醒如下：", ""]
    for reminder in reminders:
        when = (
            f"{reminder.event_date.month}月{reminder.event_date.day}日生日"
            if reminder.kind == "生日"
            else f"{reminder.event_date.month}月{reminder.event_date.day}日零食安排（提前三天提醒）"
        )
        lines.append(f"- {reminder.kind}：{reminder.name} — {when}")
    message.set_content("\n".join(lines))
    return message


def send_email(message: EmailMessage) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    sender = os.environ.get("EMAIL_FROM") or username
    recipient = os.environ["EMAIL_TO"]
    message["From"] = sender
    message["To"] = recipient

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Use YYYY-MM-DD instead of today; useful for testing")
    parser.add_argument("--dry-run", action="store_true", help="Print the email instead of sending it")
    args = parser.parse_args()

    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    today = date.fromisoformat(args.date) if args.date else date.today()
    reminders = collect_reminders(sheet_id, today)
    if not reminders:
        print(f"No reminders for {today.isoformat()}.")
        return

    message = make_message(reminders, today)
    if args.dry_run:
        print(f"Subject: {message['Subject']}\n")
        print(message.get_content())
    else:
        send_email(message)
        print(f"Sent {len(reminders)} reminder(s) for {today.isoformat()}.")


if __name__ == "__main__":
    main()
