from datetime import datetime, timedelta, timezone


def google_calendar(parameters: dict, player=None) -> str:
    try:
        from actions.google_auth import get_creds
        from googleapiclient.discovery import build
        creds   = get_creds()
        service = build("calendar", "v3", credentials=creds)
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Google Calendar auth failed: {e}"

    action = parameters.get("action", "list_today")

    if action in ("list_today", "list_events"):
        days = int(parameters.get("days", 1))
        now  = datetime.now(timezone.utc)
        end  = now + timedelta(days=days)
        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=10,
        ).execute()
        events = result.get("items", [])
        if not events:
            label = "today" if days == 1 else f"the next {days} days"
            return f"No events scheduled for {label}."
        lines = [f"You have {len(events)} event(s):"]
        for ev in events:
            lines.append(_fmt_event(ev))
        return "\n".join(lines)

    if action == "next_event":
        now  = datetime.now(timezone.utc)
        end  = now + timedelta(days=7)
        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=1,
        ).execute()
        events = result.get("items", [])
        if not events:
            return "No upcoming events in the next 7 days."
        ev    = events[0]
        start = ev["start"].get("dateTime", ev["start"].get("date", ""))
        if "T" in start:
            dt    = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone()
            diff  = dt - datetime.now().astimezone()
            total = int(diff.total_seconds())
            if total < 0:
                when = "now"
            elif total < 3600:
                when = f"in {total // 60} minutes"
            else:
                when = f"in {total // 3600}h {(total % 3600) // 60}m"
            time_str = dt.strftime("%A at %I:%M %p")
        else:
            when     = "on " + start
            time_str = start
        return f"Next event: {ev.get('summary', 'Untitled')} — {when} ({time_str})"

    if action == "create_event":
        from dateutil import parser as dp
        summary = parameters.get("title", parameters.get("summary", "Untitled"))
        start_s = parameters.get("start", "")
        end_s   = parameters.get("end", "")
        desc    = parameters.get("description", "")
        if not start_s:
            return "Please provide a start time for the event."
        try:
            start_dt = dp.parse(start_s, fuzzy=True)
            if start_dt.tzinfo is None:
                start_dt = start_dt.astimezone()
        except Exception:
            return f"Could not parse start time: {start_s}"
        if end_s:
            try:
                end_dt = dp.parse(end_s, fuzzy=True)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.astimezone()
            except Exception:
                end_dt = start_dt + timedelta(hours=1)
        else:
            end_dt = start_dt + timedelta(hours=1)

        body = {
            "summary":     summary,
            "description": desc,
            "start":       {"dateTime": start_dt.isoformat()},
            "end":         {"dateTime": end_dt.isoformat()},
        }
        service.events().insert(calendarId="primary", body=body).execute()
        return f"Event created: {summary} on {start_dt.strftime('%A, %B %d at %I:%M %p')}"

    if action == "delete_event":
        title = parameters.get("title", "")
        if not title:
            return "Please specify the event title to delete."
        now  = datetime.now(timezone.utc)
        end  = now + timedelta(days=30)
        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            q=title,
            singleEvents=True,
            orderBy="startTime",
            maxResults=1,
        ).execute()
        events = result.get("items", [])
        if not events:
            return f"No upcoming event found matching '{title}'."
        ev = events[0]
        service.events().delete(calendarId="primary", eventId=ev["id"]).execute()
        return f"Deleted: {ev.get('summary', title)}"

    return f"Unknown calendar action: {action}"


def _fmt_event(ev: dict) -> str:
    start = ev["start"].get("dateTime", ev["start"].get("date", ""))
    if "T" in start:
        dt       = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone()
        time_str = dt.strftime("%a %I:%M %p")
    else:
        time_str = start
    return f"• {ev.get('summary', 'Untitled')} — {time_str}"


def get_upcoming_events(minutes_ahead: int = 16) -> list[dict]:
    try:
        from actions.google_auth import get_creds
        from googleapiclient.discovery import build
        creds   = get_creds()
        service = build("calendar", "v3", credentials=creds)
        now     = datetime.now(timezone.utc)
        end     = now + timedelta(minutes=minutes_ahead)
        result  = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=5,
        ).execute()
        return result.get("items", [])
    except Exception:
        return []
