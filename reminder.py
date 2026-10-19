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
import urllib.error
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


def normalize_sheet_id(value: str) -> str:
    """Accept either a raw spreadsheet ID or a full Google Sheets URL."""
    value = value.strip().strip('"\'')
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    raise ValueError(
        "GOOGLE_SHEET_ID must be the spreadsheet ID or a Google Sheets URL"
    )


def read_csv_sheet(sheet_id: str, sheet_name: str) -> list[list[str]]:
    request = urllib.request.Request(
        sheet_csv_url(sheet_id, sheet_name),
        headers={"User-Agent": "date-reminder/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                "Google Sheet not found. Check that GOOGLE_SHEET_ID contains "
                "the correct spreadsheet ID and that the sheet is readable."
            ) from exc
        raise
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


def parse_requested_date(value: str) -> date:
    """Parse the manual test date, accepting dash or slash separators."""
    try:
        return date.fromisoformat(value.strip().replace("/", "-"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected a date like 2026-11-06 or 2026/11/06"
        ) from exc


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


def collect_monthly_birthdays(sheet_id: str, today: date) -> list[Reminder]:
    """Return every birthday in the current month for the email summary."""
    rows = read_csv_sheet(sheet_id, "\u751f\u65e5\u8868")
    birthdays = reminders_from_sheet(rows, "\u751f\u65e5", 0)
    return [birthday for birthday in birthdays if birthday.event_date.month == today.month]


def make_fellowship_message(
    reminders: list[Reminder], monthly_birthdays: list[Reminder], today: date
) -> EmailMessage:
    """Build a short, scannable email with due reminders and this month's birthdays."""
    message = EmailMessage()
    message["Subject"] = f"\u56e2\u5951\u63d0\u9192 \u2022 {today.isoformat()}"
    lines = [f"\u56e2\u5951\u63d0\u9192 | {today.isoformat()}", ""]

    birthday_reminders = [
        reminder for reminder in reminders if reminder.kind == "\u751f\u65e5"
    ]
    snack_reminders = [
        reminder for reminder in reminders if reminder.kind == "\u96f6\u98df"
    ]

    if birthday_reminders:
        lines.append("\U0001f382 \u4eca\u5929\u7684\u751f\u65e5")
        for reminder in birthday_reminders:
            lines.append(
                f"- {reminder.event_date.month}\u6708{reminder.event_date.day}\u65e5 | "
                f"{reminder.name} \uff08\u4eca\u5929\uff09"
            )

    if snack_reminders:
        if birthday_reminders:
            lines.append("")
        lines.append("\U0001f36a \u96f6\u98df\u63d0\u9192")
        for reminder in snack_reminders:
            lines.append(
                f"- {reminder.event_date.month}\u6708{reminder.event_date.day}\u65e5 | "
                f"{reminder.name} \uff08\u63d0\u524d3\u5929\uff09"
            )

    lines.append("")
    lines.append(f"\U0001f4c5 {today.month}\u6708\u672c\u6708\u751f\u65e5")
    if monthly_birthdays:
        for birthday in sorted(monthly_birthdays, key=lambda item: item.event_date.day):
            lines.append(
                f"- {birthday.event_date.month}\u6708{birthday.event_date.day}\u65e5 | "
                f"{birthday.name}"
            )
    else:
        lines.append("- \u672c\u6708\u6682\u65e0\u5df2\u8bb0\u5f55\u7684\u751f\u65e5")

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
    parser.add_argument(
        "--date",
        type=parse_requested_date,
        help="Use YYYY-MM-DD or YYYY/MM/DD instead of today; useful for testing",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the email instead of sending it")
    args = parser.parse_args()

    sheet_id = normalize_sheet_id(os.environ["GOOGLE_SHEET_ID"])
    today = args.date if args.date else date.today()
    reminders = collect_reminders(sheet_id, today)
    if not reminders:
        print(f"No reminders for {today.isoformat()}.")
        return

    monthly_birthdays = collect_monthly_birthdays(sheet_id, today)
    message = make_fellowship_message(reminders, monthly_birthdays, today)
    if args.dry_run:
        print(f"Subject: {message['Subject']}\n")
        print(message.get_content())
    else:
        send_email(message)
        print(f"Sent {len(reminders)} reminder(s) for {today.isoformat()}.")


if __name__ == "__main__":
    main()
