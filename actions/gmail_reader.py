import base64
from email.mime.text import MIMEText


def gmail_reader(parameters: dict, player=None) -> str:
    try:
        from actions.google_auth import get_creds
        from googleapiclient.discovery import build
        creds   = get_creds()
        service = build("gmail", "v1", credentials=creds)
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Gmail auth failed: {e}"

    action = parameters.get("action", "list_unread")

    if action == "list_unread":
        count  = int(parameters.get("count", 5))
        result = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=count
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            return "No unread emails in your inbox."
        lines = [f"You have {len(messages)} unread email(s):"]
        for msg in messages:
            m = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            hdr     = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
            subject = hdr.get("Subject", "(no subject)")
            sender  = _clean_sender(hdr.get("From", "Unknown"))
            lines.append(f"• From {sender}: {subject}")
        return "\n".join(lines)

    if action == "read_email":
        query  = parameters.get("query", "is:unread")
        result = service.users().messages().list(
            userId="me", q=query, maxResults=1
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            return "No email found."
        m   = service.users().messages().get(
            userId="me", id=messages[0]["id"], format="full"
        ).execute()
        hdr     = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
        subject = hdr.get("Subject", "(no subject)")
        sender  = hdr.get("From", "Unknown")
        body    = _extract_body(m.get("payload", {}))[:600]
        return f"From: {sender}\nSubject: {subject}\n\n{body or '(no text content)'}"

    if action == "search_emails":
        query  = parameters.get("query", "")
        count  = int(parameters.get("count", 5))
        if not query:
            return "Please provide a search query."
        result = service.users().messages().list(
            userId="me", q=query, maxResults=count
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            return f"No emails found for: {query}"
        lines = [f"Found {len(messages)} email(s) for '{query}':"]
        for msg in messages:
            m = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            hdr     = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
            subject = hdr.get("Subject", "(no subject)")
            sender  = _clean_sender(hdr.get("From", "Unknown"))
            lines.append(f"• From {sender}: {subject}")
        return "\n".join(lines)

    if action == "send_email":
        to      = parameters.get("to", "")
        subject = parameters.get("subject", "")
        body    = parameters.get("body", "")
        if not to or not body:
            return "Need 'to' and 'body' to send an email."
        msg        = MIMEText(body)
        msg["to"]      = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email sent to {to}."

    return f"Unknown gmail action: {action}"


def _clean_sender(raw: str) -> str:
    if "<" in raw:
        return raw[:raw.index("<")].strip().strip('"')
    return raw


def _extract_body(payload: dict) -> str:
    data = payload.get("body", {}).get("data", "")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            d = part.get("body", {}).get("data", "")
            if d:
                return base64.urlsafe_b64decode(d).decode("utf-8", errors="replace")
    return ""
