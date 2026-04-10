"""Support system routes: email polling, ticket management, KB editor, dashboard UI.

Conditionally mounted in main.py when SUPPORT_EMAIL_ENABLED=true and
Microsoft Graph credentials are configured.
"""

import asyncio
import html as html_mod
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.config import get_settings
from app.routes.admin import _verify_admin, _require_csrf
from app.schemas.support import KBArticleCreate, TicketReplyRequest
from app.services.graph_mail_client import GraphMailClient
from app.services.openai_service import AzureOpenAIService
from app.services.support_ai import SupportAIService
from app.services.support_store import SupportStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support"])

_settings = get_settings()

# ── Module-level singletons ──────────────────────────────────────────

support_store = SupportStore(_settings.support_db_path)

_graph_client: GraphMailClient | None = None
_support_ai: SupportAIService | None = None


def _get_graph_client() -> GraphMailClient:
    global _graph_client  # noqa: PLW0603
    if _graph_client is None:
        _graph_client = GraphMailClient(
            tenant_id=_settings.support_graph_tenant_id or "",
            client_id=_settings.support_graph_client_id or "",
            client_secret=_settings.support_graph_client_secret or "",
            mailbox=_settings.support_mailbox or "",
        )
    return _graph_client


def _get_support_ai() -> SupportAIService:
    global _support_ai  # noqa: PLW0603
    if _support_ai is None:
        _support_ai = SupportAIService(
            openai_service=AzureOpenAIService(),
            support_store=support_store,
        )
    return _support_ai


def _strip_html(html_body: str) -> str:
    """Extract plain text from HTML email body."""
    text = re.sub(r"<br\s*/?>", "\n", html_body or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(text)
    return text.strip()


def _ts_to_iso(ts: float | None) -> str:
    if ts is None:
        return ""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ── Email Polling ────────────────────────────────────────────────────

async def _execute_action(action: str, sender_email: str, ai_answer: str) -> str | None:
    """Execute an automated support action. Returns a reply string or None on failure."""
    try:
        if action == "release_device":
            return await _action_release_device(sender_email)
        elif action == "resend_key":
            return await _action_resend_key(sender_email)
        elif action == "refund":
            return await _action_refund(sender_email)
    except Exception:
        logger.exception("Failed to execute support action=%s for %s", action, sender_email)
    return None


async def _action_release_device(sender_email: str) -> str | None:
    """Release device binding for all licenses under this email."""
    from app.services.license_store import license_store as _lic_store
    from app.services.license_binding_store import get_license_binding_store

    _lic_store.initialize()
    licenses = _lic_store.resolve_by_email(sender_email)
    if not licenses:
        return None  # Can't find license — escalate to human

    binding_store = get_license_binding_store(_settings)
    released = 0
    for lic in licenses:
        if lic.get("status") != "active":
            continue
        key_hash = lic.get("key_hash", "")
        if key_hash:
            result = await binding_store.release_binding(key_hash)
            if result:
                released += 1

    if released > 0:
        return (
            "שלום,\n\n"
            "שחררנו את הקישור של מפתח ההפעלה שלך מהמחשב הקודם.\n"
            "כעת תוכל/י להפעיל את CopyBar על המחשב החדש באמצעות אותו מפתח.\n\n"
            "פשוט הפעל/י את CopyBar והזן/י את מפתח ההפעלה.\n\n"
            "אם נתקלת בבעיה נוספת, אנחנו כאן לעזור.\n\n"
            "בברכה,\nצוות CopyBar"
        )
    return None


async def _action_resend_key(sender_email: str) -> str | None:
    """Look up license key by email and include masked version in reply."""
    from app.services.license_store import license_store as _lic_store

    _lic_store.initialize()
    licenses = _lic_store.resolve_by_email(sender_email)
    active = [lic for lic in licenses if lic.get("status") == "active"]
    if not active:
        return None

    lic = active[0]
    masked = lic.get("key_masked", "???")
    tier = lic.get("tier", "personal")
    tier_labels = {"trial": "ניסיון", "personal": "Personal", "pro": "Pro"}

    return (
        "שלום,\n\n"
        f"מצאנו את הרישיון שלך. הנה הפרטים:\n\n"
        f"מפתח הפעלה: {masked}\n"
        f"חבילה: {tier_labels.get(tier, tier)}\n\n"
        "אם אינך מצליח/ה להפעיל עם המפתח, שלח/י לנו מייל נוסף ונעזור.\n\n"
        "בברכה,\nצוות CopyBar"
    )


async def _action_refund(sender_email: str) -> str | None:
    """Process a refund if within 14-day window."""
    txn = support_store.find_refundable_transaction(sender_email)
    if not txn:
        # No refundable transaction — reply with policy
        return (
            "שלום,\n\n"
            "בדקנו את החשבון שלך. לצערנו לא נמצאה עסקה שעומדת בתנאי ההחזר "
            "(החזר מלא תוך 14 ימים מהרכישה).\n\n"
            "אם את/ה סבור/ה שמדובר בטעות, אנא השב/י למייל זה עם פרטים נוספים "
            "ונציג אנושי ייבדוק את הפנייה.\n\n"
            "בברכה,\nצוות CopyBar"
        )

    approval_num = txn.get("approval_num", "")
    amount = int(txn.get("amount", 0))
    if not approval_num or not amount:
        return None  # Missing data — escalate

    try:
        from app.services.payplus_service import refund_charge
        result = await refund_charge(approval_num, amount)
        if result.get("status") == "ok":
            support_store.mark_refunded(txn["transaction_id"], amount)
            return (
                "שלום,\n\n"
                f"בקשת ההחזר שלך אושרה. סכום של {amount} ש\"ח יוחזר לאמצעי התשלום "
                "המקורי תוך 14 ימי עסקים.\n\n"
                "הרישיון שלך יישאר פעיל עד סוף תקופת החיוב הנוכחית.\n\n"
                "בברכה,\nצוות CopyBar"
            )
    except Exception:
        logger.exception("PayPlus refund failed for %s", sender_email)

    return None  # Refund failed — escalate


async def poll_mailbox() -> dict:
    """Fetch unread emails and process them with AI."""
    graph = _get_graph_client()
    ai = _get_support_ai()
    support_store.initialize()

    messages = await graph.fetch_unread(top=10)
    results = {"processed": 0, "auto_replied": 0, "pending_review": 0, "errors": 0}

    for msg in messages:
        try:
            msg_id = msg.get("id", "")
            thread_id = msg.get("conversationId", msg_id)
            subject = msg.get("subject", "")
            sender_info = msg.get("from", {}).get("emailAddress", {})
            sender_email = sender_info.get("address", "unknown")
            sender_name = sender_info.get("name")
            body_html = msg.get("body", {}).get("content", "")
            body_text = _strip_html(body_html)
            # Skip if already processed
            existing = support_store.get_ticket_by_thread(thread_id)
            if existing:
                await graph.mark_read(msg_id)
                # Add as follow-up message to existing ticket
                support_store.add_message(
                    ticket_id=existing["ticket_id"],
                    graph_message_id=msg_id,
                    direction="inbound",
                    body_text=body_text,
                    body_html=body_html,
                )
                # Re-open if closed
                if existing["status"] == "closed":
                    support_store.update_ticket(existing["ticket_id"], status="open")
                continue

            # Create new ticket
            ticket_id = support_store.create_ticket(
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
            )
            support_store.add_message(
                ticket_id=ticket_id,
                graph_message_id=msg_id,
                direction="inbound",
                body_text=body_text,
                body_html=body_html,
            )

            # Process with AI
            ai_result = await ai.process_email(email_text=body_text, subject=subject)

            support_store.update_ticket(
                ticket_id,
                confidence=ai_result.confidence,
                ai_draft=ai_result.answer,
                category=ai_result.category,
            )

            # Execute automated action if detected
            action_reply = None
            if ai_result.action:
                action_reply = await _execute_action(
                    ai_result.action, sender_email, ai_result.answer
                )

            threshold = _settings.support_ai_confidence_threshold
            final_answer = action_reply if action_reply else ai_result.answer

            if action_reply or ai_result.confidence >= threshold:
                # Auto-reply
                reply_html = _format_reply_html(final_answer)
                await graph.send_reply(msg_id, reply_html)
                support_store.update_ticket(ticket_id, status="ai_replied")
                support_store.add_message(
                    ticket_id=ticket_id,
                    graph_message_id=None,
                    direction="outbound",
                    body_text=final_answer,
                    body_html=reply_html,
                )
                results["auto_replied"] += 1
            else:
                support_store.update_ticket(ticket_id, status="pending_review")
                results["pending_review"] += 1

            await graph.mark_read(msg_id)
            results["processed"] += 1

        except Exception:
            logger.exception("Error processing support email msg_id=%s", msg.get("id"))
            results["errors"] += 1

    return results


def _format_reply_html(answer_text: str) -> str:
    escaped = html_mod.escape(answer_text).replace("\n", "<br>")
    return (
        f'<div dir="rtl" style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;">'
        f"{escaped}"
        f"<br><br>"
        f'<span style="color:#888;font-size:12px;">'
        f"הודעה זו נשלחה באופן אוטומטי על ידי מערכת התמיכה של Nudge."
        f"</span></div>"
    )


# ── Background Polling Task ──────────────────────────────────────────

_polling_task: asyncio.Task | None = None


async def _polling_loop() -> None:
    interval = _settings.support_poll_interval_seconds
    while True:
        try:
            result = await poll_mailbox()
            if result["processed"] > 0:
                logger.info("Support poll: %s", result)
        except Exception:
            logger.exception("Support polling error")
        await asyncio.sleep(interval)


def start_polling() -> None:
    global _polling_task  # noqa: PLW0603
    if _polling_task is None or _polling_task.done():
        _polling_task = asyncio.create_task(_polling_loop())
        logger.info("Support email polling started (interval=%ds)", _settings.support_poll_interval_seconds)


def stop_polling() -> None:
    global _polling_task  # noqa: PLW0603
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        _polling_task = None


# ── API Routes ───────────────────────────────────────────────────────

@router.post("/admin/api/support/poll")
async def manual_poll(_admin: str = Depends(_verify_admin)) -> JSONResponse:
    """Manually trigger email polling."""
    result = await poll_mailbox()
    return JSONResponse(content=result)


@router.get("/admin/api/support/tickets")
async def list_tickets(
    _admin: str = Depends(_verify_admin),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    tickets = support_store.list_tickets(status=status_filter, limit=limit, offset=offset)
    return JSONResponse(content=[
        {
            "ticket_id": t["ticket_id"],
            "sender_email": t["sender_email"],
            "sender_name": t["sender_name"],
            "subject": t["subject"],
            "status": t["status"],
            "confidence": t["confidence"],
            "category": t["category"],
            "created_at": _ts_to_iso(t["created_ts"]),
            "updated_at": _ts_to_iso(t["updated_ts"]),
        }
        for t in tickets
    ])


@router.get("/admin/api/support/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, _admin: str = Depends(_verify_admin)) -> JSONResponse:
    ticket = support_store.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    messages = support_store.get_messages(ticket_id)
    return JSONResponse(content={
        "ticket_id": ticket["ticket_id"],
        "sender_email": ticket["sender_email"],
        "sender_name": ticket["sender_name"],
        "subject": ticket["subject"],
        "status": ticket["status"],
        "confidence": ticket["confidence"],
        "ai_draft": ticket["ai_draft"],
        "category": ticket["category"],
        "created_at": _ts_to_iso(ticket["created_ts"]),
        "updated_at": _ts_to_iso(ticket["updated_ts"]),
        "messages": [
            {
                "message_id": m["message_id"],
                "direction": m["direction"],
                "body_text": m["body_text"],
                "body_html": m["body_html"],
                "sent_at": _ts_to_iso(m["sent_ts"]),
            }
            for m in messages
        ],
    })


@router.post("/admin/api/support/tickets/{ticket_id}/reply")
async def reply_ticket(
    ticket_id: str,
    payload: TicketReplyRequest,
    request: Request,
    _admin: str = Depends(_verify_admin),
) -> JSONResponse:
    _require_csrf(request)
    ticket = support_store.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    graph = _get_graph_client()
    messages = support_store.get_messages(ticket_id)
    # Find the last inbound message to reply to
    last_inbound = None
    for m in reversed(messages):
        if m["direction"] == "inbound" and m["graph_message_id"]:
            last_inbound = m
            break

    if last_inbound and last_inbound["graph_message_id"]:
        await graph.send_reply(last_inbound["graph_message_id"], payload.body_html)
    else:
        # Fallback: send new email
        await graph.send_mail(
            to=ticket["sender_email"],
            subject=f"Re: {ticket['subject'] or 'Nudge Support'}",
            body_html=payload.body_html,
        )

    support_store.add_message(
        ticket_id=ticket_id,
        graph_message_id=None,
        direction="outbound",
        body_text=_strip_html(payload.body_html),
        body_html=payload.body_html,
    )
    support_store.update_ticket(ticket_id, status="ai_replied")
    return JSONResponse(content={"ok": True})


@router.post("/admin/api/support/tickets/{ticket_id}/close")
async def close_ticket(
    ticket_id: str,
    request: Request,
    _admin: str = Depends(_verify_admin),
) -> JSONResponse:
    _require_csrf(request)
    ticket = support_store.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    support_store.update_ticket(ticket_id, status="closed", closed_ts=time.time())
    return JSONResponse(content={"ok": True})


# ── Knowledge Base API ───────────────────────────────────────────────

@router.get("/admin/api/support/kb")
async def list_kb(_admin: str = Depends(_verify_admin)) -> JSONResponse:
    articles = support_store.list_kb_articles()
    return JSONResponse(content=[
        {
            "kb_id": a["kb_id"],
            "question": a["question"],
            "answer": a["answer"],
            "category": a["category"],
            "enabled": bool(a["enabled"]),
            "created_at": _ts_to_iso(a["created_ts"]),
            "updated_at": _ts_to_iso(a["updated_ts"]),
        }
        for a in articles
    ])


@router.post("/admin/api/support/kb")
async def create_or_update_kb(
    payload: KBArticleCreate,
    request: Request,
    _admin: str = Depends(_verify_admin),
    kb_id: str | None = Query(default=None),
) -> JSONResponse:
    _require_csrf(request)
    if kb_id:
        existing = support_store.get_kb_article(kb_id)
        if not existing:
            raise HTTPException(status_code=404, detail="KB article not found.")
        support_store.update_kb_article(
            kb_id, question=payload.question, answer=payload.answer, category=payload.category
        )
        return JSONResponse(content={"kb_id": kb_id, "updated": True})
    else:
        new_id = support_store.create_kb_article(
            question=payload.question, answer=payload.answer, category=payload.category
        )
        return JSONResponse(content={"kb_id": new_id, "created": True})


@router.delete("/admin/api/support/kb/{kb_id}")
async def delete_kb(
    kb_id: str,
    request: Request,
    _admin: str = Depends(_verify_admin),
) -> JSONResponse:
    _require_csrf(request)
    support_store.delete_kb_article(kb_id)
    return JSONResponse(content={"ok": True})


@router.get("/admin/api/support/stats")
async def support_stats(_admin: str = Depends(_verify_admin)) -> JSONResponse:
    stats = support_store.stats()
    return JSONResponse(content=stats)


# ── Dashboard UI ─────────────────────────────────────────────────────

@router.get("/admin/support", response_class=HTMLResponse)
async def support_dashboard(request: Request, _admin: str = Depends(_verify_admin)) -> HTMLResponse:
    html = """
<!doctype html>
<html dir="rtl" lang="he">
<head>
  <meta charset="utf-8" />
  <title>Nudge Support Dashboard</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; margin: 18px; background: #0f1524; color: #eaf0ff; direction: rtl; }
    .cards { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
    .card { background: #1a2338; border: 1px solid #2f3a54; border-radius: 10px; padding: 10px; }
    .title { color: #99a8cb; font-size: 12px; }
    .value { font-size: 20px; font-weight: 700; margin-top: 4px; }
    .panel { background: #151d30; border: 1px solid #2a3550; border-radius: 10px; padding: 12px; margin-bottom: 14px; }
    input, select, textarea, button { background: #10182a; color: #eaf0ff; border: 1px solid #334261; border-radius: 7px; padding: 7px; font-family: inherit; }
    textarea { width: 100%; min-height: 80px; resize: vertical; }
    button { cursor: pointer; }
    button:hover { background: #1a2a44; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { border-bottom: 1px solid #293656; text-align: right; padding: 8px; font-size: 13px; }
    th { color: #9fb0d6; }
    .muted { color: #8ea0c7; font-size: 12px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 5px; font-size: 11px; font-weight: 600; }
    .badge-open { background: #3a2a10; color: #f0c040; border: 1px solid #6b5a20; }
    .badge-ai_replied { background: #1a3a2a; color: #40e080; border: 1px solid #208050; }
    .badge-pending_review { background: #3a1a2a; color: #ff6080; border: 1px solid #802040; }
    .badge-closed { background: #1a2a3a; color: #60b0ff; border: 1px solid #2a5080; }
    .conf-bar { display: inline-block; width: 50px; height: 8px; background: #1a2338; border-radius: 4px; vertical-align: middle; margin-right: 4px; }
    .conf-fill { height: 100%; border-radius: 4px; }
    .conf-high { background: #40e080; }
    .conf-mid { background: #f0a040; }
    .conf-low { background: #ff4060; }
    .tabs { display: flex; gap: 4px; margin-bottom: 14px; }
    .tab { padding: 8px 18px; border-radius: 8px 8px 0 0; cursor: pointer; background: #1a2338; border: 1px solid #2f3a54; border-bottom: none; }
    .tab.active { background: #151d30; color: #7ba0ff; font-weight: 600; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .detail-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: none; z-index: 100; justify-content: center; align-items: center; }
    .detail-box { background: #151d30; border: 1px solid #2a3550; border-radius: 12px; padding: 20px; width: 700px; max-height: 80vh; overflow-y: auto; }
    .msg-in { background: #1a2338; border-radius: 8px; padding: 10px; margin: 6px 0; border-right: 3px solid #4f83ff; }
    .msg-out { background: #1a3020; border-radius: 8px; padding: 10px; margin: 6px 0; border-right: 3px solid #40e080; }
    .green-value { color: #10B981; }
    a { color: #7ba0ff; }
    .nav-links { margin-bottom: 10px; }
    .nav-links a { margin-left: 12px; font-size: 13px; }
  </style>
</head>
<body>
  <div class="nav-links">
    <a href="/admin">Dashboard ראשי</a>
    <a href="/admin/support">תמיכה</a>
  </div>
  <h2>Nudge Support Dashboard</h2>
  <div class="muted">ניהול פניות תמיכה, בסיס ידע ומענה AI אוטומטי</div>

  <div style="display:flex; gap:8px; margin:10px 0 14px 0;">
    <button onclick="pollNow()">סנכרן מיילים עכשיו</button>
  </div>

  <div class="cards">
    <div class="card"><div class="title">סה"כ פניות</div><div id="stat_total" class="value">-</div></div>
    <div class="card"><div class="title">ממתינות לבדיקה</div><div id="stat_pending" class="value" style="color:#ff6080;">-</div></div>
    <div class="card"><div class="title">נענו ע"י AI</div><div id="stat_ai" class="value green-value">-</div></div>
    <div class="card"><div class="title">% מענה אוטומטי</div><div id="stat_rate" class="value">-</div></div>
  </div>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('tickets')">פניות</div>
    <div class="tab" onclick="switchTab('kb')">בסיס ידע</div>
  </div>

  <!-- Tickets Tab -->
  <div id="tab-tickets" class="tab-content active">
    <div class="panel">
      <div style="display:flex; gap:8px; margin-bottom:8px;">
        <select id="statusFilter" onchange="refreshTickets()">
          <option value="">כל הסטטוסים</option>
          <option value="open">פתוח</option>
          <option value="pending_review">ממתין לבדיקה</option>
          <option value="ai_replied">נענה ע"י AI</option>
          <option value="closed">סגור</option>
        </select>
      </div>
      <table>
        <thead><tr><th>שולח</th><th>נושא</th><th>סטטוס</th><th>ביטחון AI</th><th>קטגוריה</th><th>תאריך</th><th>פעולות</th></tr></thead>
        <tbody id="tickets_tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- Knowledge Base Tab -->
  <div id="tab-kb" class="tab-content">
    <div class="panel">
      <h4>הוסף/עדכן מאמר</h4>
      <input id="kb_id_edit" type="hidden" />
      <div style="margin-bottom:8px;">
        <input id="kb_question" placeholder="שאלה" style="width:100%;" />
      </div>
      <div style="margin-bottom:8px;">
        <textarea id="kb_answer" placeholder="תשובה"></textarea>
      </div>
      <div style="display:flex; gap:8px; align-items:center;">
        <select id="kb_category">
          <option value="general">כללי</option>
          <option value="technical">טכני</option>
          <option value="billing">חיוב</option>
          <option value="account">חשבון</option>
          <option value="other">אחר</option>
        </select>
        <button onclick="saveKB()">שמור מאמר</button>
        <button onclick="clearKBForm()">נקה טופס</button>
      </div>
    </div>
    <div class="panel">
      <h4>מאמרים קיימים</h4>
      <table>
        <thead><tr><th>שאלה</th><th>קטגוריה</th><th>מופעל</th><th>עדכון</th><th>פעולות</th></tr></thead>
        <tbody id="kb_tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- Ticket Detail Overlay -->
  <div id="detailOverlay" class="detail-overlay" onclick="if(event.target===this)closeDetail()">
    <div class="detail-box" id="detailBox"></div>
  </div>

<script>
function getCsrfToken() {
  const m = document.cookie.match(/nudge_csrf=([^;]+)/);
  return m ? m[1] : '';
}

async function fetchJson(url) {
  const r = await fetch(url, { credentials: 'same-origin' });
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

async function postJson(url, body) {
  const r = await fetch(url, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

async function deleteJson(url) {
  const r = await fetch(url, {
    method: 'DELETE', credentials: 'same-origin',
    headers: { 'X-CSRF-Token': getCsrfToken() }
  });
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

// Tabs
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

// Stats
async function refreshStats() {
  try {
    const s = await fetchJson('/admin/api/support/stats');
    document.getElementById('stat_total').textContent = s.total_tickets;
    document.getElementById('stat_pending').textContent = s.pending_review;
    document.getElementById('stat_ai').textContent = s.ai_replied;
    document.getElementById('stat_rate').textContent = s.auto_resolve_rate != null ? s.auto_resolve_rate + '%' : '-';
  } catch(e) { console.error('Stats error:', e); }
}

// Tickets
function confBar(conf) {
  if (conf == null) return '-';
  const pct = Math.round(conf * 100);
  const cls = pct >= 75 ? 'conf-high' : pct >= 40 ? 'conf-mid' : 'conf-low';
  return `<span class="conf-bar"><span class="conf-fill ${cls}" style="width:${pct}%"></span></span> ${pct}%`;
}

function statusBadge(s) {
  const labels = { open: 'פתוח', ai_replied: 'נענה AI', pending_review: 'ממתין', closed: 'סגור' };
  return `<span class="badge badge-${s}">${labels[s] || s}</span>`;
}

async function refreshTickets() {
  try {
    const sf = document.getElementById('statusFilter').value;
    const url = '/admin/api/support/tickets' + (sf ? '?status=' + sf : '');
    const tickets = await fetchJson(url);
    const tbody = document.getElementById('tickets_tbody');
    tbody.innerHTML = tickets.map(t => `<tr>
      <td>${esc(t.sender_name || t.sender_email)}</td>
      <td>${esc(t.subject || '(ללא נושא)')}</td>
      <td>${statusBadge(t.status)}</td>
      <td>${confBar(t.confidence)}</td>
      <td>${esc(t.category || '-')}</td>
      <td class="muted">${new Date(t.created_at).toLocaleDateString('he-IL')}</td>
      <td>
        <button onclick="openDetail('${t.ticket_id}')">צפה</button>
        ${t.status !== 'closed' ? `<button onclick="closeTicket('${t.ticket_id}')">סגור</button>` : ''}
      </td>
    </tr>`).join('');
  } catch(e) { console.error('Tickets error:', e); }
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

async function openDetail(ticketId) {
  try {
    const t = await fetchJson('/admin/api/support/tickets/' + ticketId);
    const box = document.getElementById('detailBox');
    let html = `<h3>${esc(t.subject || '(ללא נושא)')}</h3>`;
    html += `<div class="muted">מ: ${esc(t.sender_name || '')} &lt;${esc(t.sender_email)}&gt; | ${statusBadge(t.status)} | ביטחון: ${confBar(t.confidence)}</div>`;
    if (t.ai_draft) {
      html += `<div style="margin:10px 0; padding:10px; background:#1a2a20; border-radius:8px; border: 1px solid #2a5040;"><strong>טיוטת AI:</strong><br>${esc(t.ai_draft)}</div>`;
    }
    html += '<h4>שיחה:</h4>';
    for (const m of t.messages) {
      const cls = m.direction === 'inbound' ? 'msg-in' : 'msg-out';
      const label = m.direction === 'inbound' ? 'לקוח' : 'תמיכה';
      html += `<div class="${cls}"><strong>${label}</strong> <span class="muted">${new Date(m.sent_at).toLocaleString('he-IL')}</span><br>${esc(m.body_text)}</div>`;
    }
    if (t.status !== 'closed') {
      html += `<div style="margin-top:12px;">
        <textarea id="replyText" placeholder="כתוב תשובה..."></textarea>
        <div style="margin-top:6px;">
          <button onclick="sendReply('${ticketId}')">שלח תשובה</button>
          ${t.ai_draft ? `<button onclick="document.getElementById('replyText').value=\`${t.ai_draft.replace(/`/g, "'")}\`">השתמש בטיוטת AI</button>` : ''}
          <button onclick="closeDetail()">סגור</button>
        </div>
      </div>`;
    } else {
      html += '<div style="margin-top:8px;"><button onclick="closeDetail()">סגור</button></div>';
    }
    box.innerHTML = html;
    document.getElementById('detailOverlay').style.display = 'flex';
  } catch(e) { alert('Error: ' + e.message); }
}

function closeDetail() {
  document.getElementById('detailOverlay').style.display = 'none';
}

async function sendReply(ticketId) {
  const text = document.getElementById('replyText').value.trim();
  if (!text) return alert('יש להזין תשובה');
  const bodyHtml = '<div dir="rtl" style="font-family:Segoe UI,Arial,sans-serif;">' + esc(text).replace(/\\n/g, '<br>') + '</div>';
  try {
    await postJson('/admin/api/support/tickets/' + ticketId + '/reply', { body_html: bodyHtml });
    closeDetail();
    refreshTickets();
    refreshStats();
  } catch(e) { alert('Error: ' + e.message); }
}

async function closeTicket(ticketId) {
  try {
    await postJson('/admin/api/support/tickets/' + ticketId + '/close', {});
    refreshTickets();
    refreshStats();
  } catch(e) { alert('Error: ' + e.message); }
}

async function pollNow() {
  try {
    const r = await postJson('/admin/api/support/poll', {});
    alert(`סנכרון הושלם: ${r.processed} עובדו, ${r.auto_replied} נענו, ${r.pending_review} ממתינים, ${r.errors} שגיאות`);
    refreshTickets();
    refreshStats();
  } catch(e) { alert('Error: ' + e.message); }
}

// Knowledge Base
async function refreshKB() {
  try {
    const articles = await fetchJson('/admin/api/support/kb');
    const tbody = document.getElementById('kb_tbody');
    tbody.innerHTML = articles.map(a => `<tr>
      <td>${esc(a.question)}</td>
      <td>${esc(a.category)}</td>
      <td>${a.enabled ? 'כן' : 'לא'}</td>
      <td class="muted">${new Date(a.updated_at).toLocaleDateString('he-IL')}</td>
      <td>
        <button onclick="editKB('${a.kb_id}', \`${a.question.replace(/`/g, "'")}\`, \`${a.answer.replace(/`/g, "'")}\`, '${a.category}')">ערוך</button>
        <button onclick="deleteKB('${a.kb_id}')">מחק</button>
      </td>
    </tr>`).join('');
  } catch(e) { console.error('KB error:', e); }
}

function editKB(id, q, a, cat) {
  document.getElementById('kb_id_edit').value = id;
  document.getElementById('kb_question').value = q;
  document.getElementById('kb_answer').value = a;
  document.getElementById('kb_category').value = cat;
}

function clearKBForm() {
  document.getElementById('kb_id_edit').value = '';
  document.getElementById('kb_question').value = '';
  document.getElementById('kb_answer').value = '';
  document.getElementById('kb_category').value = 'general';
}

async function saveKB() {
  const id = document.getElementById('kb_id_edit').value;
  const q = document.getElementById('kb_question').value.trim();
  const a = document.getElementById('kb_answer').value.trim();
  const cat = document.getElementById('kb_category').value;
  if (!q || !a) return alert('יש למלא שאלה ותשובה');
  const url = '/admin/api/support/kb' + (id ? '?kb_id=' + id : '');
  try {
    await postJson(url, { question: q, answer: a, category: cat });
    clearKBForm();
    refreshKB();
  } catch(e) { alert('Error: ' + e.message); }
}

async function deleteKB(id) {
  if (!confirm('למחוק מאמר זה?')) return;
  try {
    await deleteJson('/admin/api/support/kb/' + id);
    refreshKB();
  } catch(e) { alert('Error: ' + e.message); }
}

// Init
refreshStats();
refreshTickets();
refreshKB();
</script>
</body>
</html>
"""
    from fastapi.responses import HTMLResponse as _HR
    response = _HR(content=html)
    from app.routes.admin import _CSRF_COOKIE_NAME, _generate_csrf_token
    csrf = _generate_csrf_token()
    response.set_cookie(
        key=_CSRF_COOKIE_NAME,
        value=csrf,
        httponly=False,
        samesite="strict",
        path="/admin",
    )
    return response
