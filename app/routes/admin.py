import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import get_settings
from app.schemas.leads import LeadCreateRequest, LeadCreateResponse, LeadListResponse, LeadRecord, LeadStatsResponse, create_lead_id
from app.schemas.usage import (
    UsageHeavyResponse,
    UsageHeavyRow,
    UsageMetric,
    UsagePeriod,
    UsageSummaryResponse,
    UsageUserRow,
    UsageUsersResponse,
)
from app.services.lead_store import LeadStore
from app.services.usage_store import usage_store


router = APIRouter(tags=["admin"])
security = HTTPBasic(auto_error=False)
security_dependency = Depends(security)
settings = get_settings()
lead_store = LeadStore(settings.leads_db_path)


def _require_admin_enabled() -> None:
    if not settings.admin_dashboard_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


def _verify_admin(credentials: HTTPBasicCredentials | None = security_dependency) -> str:
    _require_admin_enabled()
    username = (settings.admin_dashboard_username or "").strip()
    password = (settings.admin_dashboard_password or "").strip()
    provided_username = (credentials.username if credentials else "").strip()
    provided_password = (credentials.password if credentials else "").strip()
    if not (
        username
        and password
        and hmac.compare_digest(provided_username, username)
        and hmac.compare_digest(provided_password, password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return provided_username


def _parse_self_principals(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for chunk in (raw or "").replace("\r", "\n").replace("\n", ",").split(","):
        item = chunk.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _is_self_principal(principal: str) -> bool:
    self_principals = _parse_self_principals(settings.admin_self_principals)
    return principal in self_principals


@router.post("/leads/register", response_model=LeadCreateResponse)
async def register_lead(payload: LeadCreateRequest) -> LeadCreateResponse:
    result = lead_store.upsert_lead(
        lead_id=create_lead_id(),
        full_name=payload.full_name,
        email=str(payload.email),
        phone=payload.phone,
        occupation=payload.occupation,
        source=payload.source,
        app_version=payload.app_version,
    )
    return LeadCreateResponse(
        lead_id=result.lead_id,
        created=result.created,
        joined_at=result.joined_at,
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(_admin: str = Depends(_verify_admin)) -> HTMLResponse:
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Nudge Admin Dashboard</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; margin: 18px; background: #0f1524; color: #eaf0ff; }
    .cards { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
    .card { background: #1a2338; border: 1px solid #2f3a54; border-radius: 10px; padding: 10px; }
    .title { color: #99a8cb; font-size: 12px; }
    .value { font-size: 20px; font-weight: 700; margin-top: 4px; }
    .panel { background: #151d30; border: 1px solid #2a3550; border-radius: 10px; padding: 12px; margin-bottom: 14px; }
    input, select, button { background: #10182a; color: #eaf0ff; border: 1px solid #334261; border-radius: 7px; padding: 7px; }
    button { cursor: pointer; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { border-bottom: 1px solid #293656; text-align: left; padding: 8px; font-size: 13px; }
    th { color: #9fb0d6; }
    .cols { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
    .muted { color: #8ea0c7; font-size: 12px; }
    .bar { height: 10px; background: linear-gradient(90deg, #4f83ff, #7b6dff); border-radius: 6px; }
  </style>
</head>
<body>
  <h2>Nudge Admin Dashboard</h2>
  <div class="muted">Lead/user management only. No clipboard/OCR/user-content data is stored here.</div>
  <div class="cards">
    <div class="card"><div class="title">Total users</div><div id="total_users" class="value">-</div></div>
    <div class="card"><div class="title">Joined today</div><div id="joined_today" class="value">-</div></div>
    <div class="card"><div class="title">Joined week</div><div id="joined_week" class="value">-</div></div>
    <div class="card"><div class="title">Joined month</div><div id="joined_month" class="value">-</div></div>
  </div>

  <div class="panel">
    <form id="filters" onsubmit="event.preventDefault(); refreshUsers();">
      <input id="search" placeholder="Search name/email/phone" />
      <input id="occupation" placeholder="Occupation/industry" />
      <select id="source">
        <option value="">Any source</option>
        <option value="website">website</option>
        <option value="direct">direct</option>
        <option value="referral">referral</option>
        <option value="unknown">unknown</option>
      </select>
      <label>From <input id="joined_from" type="date" /></label>
      <label>To <input id="joined_to" type="date" /></label>
      <button type="submit">Apply</button>
    </form>
    <table>
      <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Occupation</th><th>Source</th><th>Joined</th><th>App</th></tr></thead>
      <tbody id="users_tbody"></tbody>
    </table>
  </div>

  <div class="cols">
    <div class="panel">
      <h4>Joined by day (last 30)</h4>
      <div id="by_day"></div>
    </div>
    <div class="panel">
      <h4>Occupation breakdown</h4>
      <div id="occupation_breakdown"></div>
    </div>
  </div>

  <div class="panel">
    <h3>Usage & Estimated Cost (metadata-only)</h3>
    <div class="muted">Self/Admin view is based on server-configured principals.</div>
    <div class="cards">
      <div class="card"><div class="title">Events</div><div id="usage_total_events" class="value">-</div></div>
      <div class="card"><div class="title">Active users</div><div id="usage_active_users" class="value">-</div></div>
      <div class="card"><div class="title">AI events</div><div id="usage_ai_events" class="value">-</div></div>
      <div class="card"><div class="title">OCR events</div><div id="usage_ocr_events" class="value">-</div></div>
      <div class="card"><div class="title">Est. OpenAI $</div><div id="usage_cost_openai" class="value">-</div></div>
      <div class="card"><div class="title">Est. OCR $</div><div id="usage_cost_ocr" class="value">-</div></div>
      <div class="card"><div class="title">Est. total $</div><div id="usage_cost_total" class="value">-</div></div>
      <div class="card"><div class="title">My events</div><div id="usage_my_events" class="value">-</div></div>
      <div class="card"><div class="title">My cost $</div><div id="usage_my_cost_total" class="value">-</div></div>
    </div>
    <form id="usage_filters" onsubmit="event.preventDefault(); refreshUsage();">
      <select id="usage_period">
        <option value="day">day</option>
        <option value="week">week</option>
        <option value="month" selected>month</option>
      </select>
      <select id="usage_route_type">
        <option value="">all routes</option>
        <option value="ai_action">ai_action</option>
        <option value="ocr">ocr</option>
      </select>
      <input id="usage_action" placeholder="action key" />
      <input id="usage_search" placeholder="search principal" />
      <label><input id="usage_self_only" type="checkbox" /> self only</label>
      <button type="submit">Apply</button>
    </form>
    <table>
      <thead><tr><th>Principal</th><th>Devices</th><th>Events</th><th>AI</th><th>OCR</th><th>Est. OpenAI $</th><th>Est. OCR $</th><th>Est. total $</th><th>Last seen</th></tr></thead>
      <tbody id="usage_users_tbody"></tbody>
    </table>
    <div class="cols" style="margin-top:12px;">
      <div class="panel">
        <h4>Heavy users by events</h4>
        <div id="usage_heavy_events"></div>
      </div>
      <div class="panel">
        <h4>Heavy users by cost</h4>
        <div id="usage_heavy_cost"></div>
      </div>
    </div>
  </div>

  <script>
    async function fetchJson(url) {
      const r = await fetch(url, { credentials: 'same-origin' });
      if (!r.ok) throw new Error("Request failed");
      return r.json();
    }
    function esc(v) {
      return String(v ?? "").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
    }
    function pct(count, max) {
      if (!max) return "0%";
      return `${Math.max(2, Math.round((count / max) * 100))}%`;
    }
    async function refreshStats() {
      const stats = await fetchJson('/admin/api/stats');
      document.getElementById('total_users').textContent = stats.total_users;
      document.getElementById('joined_today').textContent = stats.joined_today;
      document.getElementById('joined_week').textContent = stats.joined_week;
      document.getElementById('joined_month').textContent = stats.joined_month;
      const maxDay = Math.max(1, ...stats.joined_by_day.map(x => x.count));
      document.getElementById('by_day').innerHTML = stats.joined_by_day.map(x =>
        `<div style="margin-bottom:8px"><div class="muted">${esc(x.day)} (${x.count})</div><div class="bar" style="width:${pct(x.count,maxDay)}"></div></div>`
      ).join('') || '<div class="muted">No data</div>';
      document.getElementById('occupation_breakdown').innerHTML = stats.occupation_breakdown.map(x =>
        `<div style="display:flex;justify-content:space-between;margin-bottom:6px"><span>${esc(x.occupation)}</span><strong>${x.count}</strong></div>`
      ).join('') || '<div class="muted">No data</div>';
    }
    async function refreshUsers() {
      const q = new URLSearchParams();
      for (const id of ['search','occupation','source','joined_from','joined_to']) {
        const v = document.getElementById(id).value.trim();
        if (v) q.set(id, v);
      }
      const data = await fetchJson(`/admin/api/users?${q.toString()}`);
      document.getElementById('users_tbody').innerHTML = data.items.map(row => `
        <tr>
          <td>${esc(row.full_name)}</td>
          <td>${esc(row.email)}</td>
          <td>${esc(row.phone || '')}</td>
          <td>${esc(row.occupation)}</td>
          <td>${esc(row.source)}</td>
          <td>${esc(row.joined_at)}</td>
          <td>${esc(row.app_version || '')}</td>
        </tr>
      `).join('') || '<tr><td colspan="7" class="muted">No users found</td></tr>';
    }
    async function bootstrap() {
      try {
        await Promise.all([refreshStats(), refreshUsers(), refreshUsage()]);
      } catch {
        alert('Failed to load dashboard data.');
      }
    }
    function money(v) {
      const n = Number(v || 0);
      return n.toFixed(4);
    }
    function usageQueryBase() {
      const q = new URLSearchParams();
      q.set('period', document.getElementById('usage_period').value || 'month');
      const routeType = document.getElementById('usage_route_type').value.trim();
      const action = document.getElementById('usage_action').value.trim();
      const search = document.getElementById('usage_search').value.trim();
      const selfOnly = document.getElementById('usage_self_only').checked;
      if (routeType) q.set('route_type', routeType);
      if (action) q.set('action', action);
      if (search) q.set('search', search);
      if (selfOnly) q.set('self_only', 'true');
      return q;
    }
    function renderHeavy(elId, items) {
      document.getElementById(elId).innerHTML = items.map(row =>
        `<div style="display:flex;justify-content:space-between;margin-bottom:6px"><span>${esc(row.principal)}${row.is_self ? ' <strong>(Me/Admin)</strong>' : ''}</span><strong>${row.total_events} / $${money(row.estimated_cost_usd)}</strong></div>`
      ).join('') || '<div class="muted">No data</div>';
    }
    async function refreshUsage() {
      const q = usageQueryBase();
      const [summary, users, heavyEvents, heavyCost] = await Promise.all([
        fetchJson(`/admin/api/usage/summary?${q.toString()}`),
        fetchJson(`/admin/api/usage/users?${q.toString()}`),
        fetchJson(`/admin/api/usage/heavy?${q.toString()}&metric=events`),
        fetchJson(`/admin/api/usage/heavy?${q.toString()}&metric=cost`),
      ]);
      document.getElementById('usage_total_events').textContent = summary.total_events;
      document.getElementById('usage_active_users').textContent = summary.active_users;
      document.getElementById('usage_ai_events').textContent = summary.ai_events;
      document.getElementById('usage_ocr_events').textContent = summary.ocr_events;
      document.getElementById('usage_cost_openai').textContent = `$${money(summary.estimated_cost_openai_usd)}`;
      document.getElementById('usage_cost_ocr').textContent = `$${money(summary.estimated_cost_ocr_usd)}`;
      document.getElementById('usage_cost_total').textContent = `$${money(summary.estimated_cost_usd)}`;
      document.getElementById('usage_my_events').textContent = summary.my_events;
      document.getElementById('usage_my_cost_total').textContent = `$${money(summary.my_estimated_cost_usd)}`;
      document.getElementById('usage_users_tbody').innerHTML = users.items.map(row => `
        <tr>
          <td>${esc(row.principal)} ${row.is_self ? '<strong>(Me/Admin)</strong>' : ''}</td>
          <td>${row.distinct_devices}</td>
          <td>${row.total_events}</td>
          <td>${row.ai_events}</td>
          <td>${row.ocr_events}</td>
          <td>$${money(row.estimated_cost_openai_usd)}</td>
          <td>$${money(row.estimated_cost_ocr_usd)}</td>
          <td>$${money(row.estimated_cost_usd)}</td>
          <td>${esc(row.last_seen_at)}</td>
        </tr>
      `).join('') || '<tr><td colspan="9" class="muted">No usage rows found</td></tr>';
      renderHeavy('usage_heavy_events', heavyEvents.items);
      renderHeavy('usage_heavy_cost', heavyCost.items);
    }
    bootstrap();
  </script>
</body>
</html>
    """.strip()
    return HTMLResponse(content=html)


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


@router.get("/admin/api/stats", response_model=LeadStatsResponse)
async def admin_stats(_admin: str = Depends(_verify_admin)) -> LeadStatsResponse:
    return LeadStatsResponse(**lead_store.stats())


@router.get("/admin/api/users", response_model=LeadListResponse)
async def admin_users(
    _admin: str = Depends(_verify_admin),
    search: str = Query(default="", max_length=120),
    occupation: str = Query(default="", max_length=120),
    source: str = Query(default="", max_length=30),
    joined_from: str = Query(default=""),
    joined_to: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> LeadListResponse:
    from_dt = _parse_date(joined_from)
    to_dt = _parse_date(joined_to)
    if to_dt is not None:
        to_dt = to_dt + timedelta(days=1) - timedelta(seconds=1)

    total, rows = lead_store.list_leads(
        search=search,
        occupation=occupation,
        source=source,
        joined_from=from_dt,
        joined_to=to_dt,
        limit=limit,
        offset=offset,
    )
    items = [
        LeadRecord(
            lead_id=str(row["lead_id"]),
            full_name=str(row["full_name"]),
            email=str(row["email"]),
            phone=str(row["phone"]) if row["phone"] else None,
            occupation=str(row["occupation"]),
            source=str(row["source"]),
            app_version=str(row["app_version"]),
            status=str(row["status"]),
            joined_at=datetime.fromisoformat(str(row["created_at"])),
        )
        for row in rows
    ]
    return LeadListResponse(total=total, items=items)


@router.get("/admin/api/usage/summary", response_model=UsageSummaryResponse)
async def admin_usage_summary(
    _admin: str = Depends(_verify_admin),
    period: UsagePeriod = Query(default="month"),
    self_only: bool = Query(default=False),
) -> UsageSummaryResponse:
    self_principals = _parse_self_principals(settings.admin_self_principals)
    principals_filter = self_principals if self_only else None
    base = usage_store.summary(period=period, principals=principals_filter)
    mine = usage_store.summary(period=period, principals=self_principals) if self_principals else {
        "total_events": 0,
        "estimated_cost_openai_usd": 0.0,
        "estimated_cost_ocr_usd": 0.0,
        "estimated_cost_usd": 0.0,
    }
    return UsageSummaryResponse(
        period=period,
        total_events=int(base["total_events"]),
        active_users=int(base["active_users"]),
        ai_events=int(base["ai_events"]),
        ocr_events=int(base["ocr_events"]),
        estimated_cost_openai_usd=float(base["estimated_cost_openai_usd"]),
        estimated_cost_ocr_usd=float(base["estimated_cost_ocr_usd"]),
        estimated_cost_usd=float(base["estimated_cost_usd"]),
        my_events=int(mine["total_events"]),
        my_active=bool(int(mine["total_events"]) > 0),
        my_estimated_cost_openai_usd=float(mine["estimated_cost_openai_usd"]),
        my_estimated_cost_ocr_usd=float(mine["estimated_cost_ocr_usd"]),
        my_estimated_cost_usd=float(mine["estimated_cost_usd"]),
        usage_by_feature=list(base["usage_by_feature"]),
    )


@router.get("/admin/api/usage/users", response_model=UsageUsersResponse)
async def admin_usage_users(
    _admin: str = Depends(_verify_admin),
    period: UsagePeriod = Query(default="month"),
    search: str = Query(default="", max_length=160),
    route_type: str = Query(default="", max_length=40),
    action: str = Query(default="", max_length=80),
    self_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> UsageUsersResponse:
    self_principals = _parse_self_principals(settings.admin_self_principals)
    principals_filter = self_principals if self_only else None
    total, rows = usage_store.users(
        period=period,
        search=search,
        route_type=route_type,
        action=action,
        principals=principals_filter,
        limit=limit,
        offset=offset,
    )
    items = [
        UsageUserRow(
            principal=str(row["principal"]),
            is_self=_is_self_principal(str(row["principal"])),
            distinct_devices=int(row["distinct_devices"] or 0),
            total_events=int(row["total_events"] or 0),
            ai_events=int(row["ai_events"] or 0),
            ocr_events=int(row["ocr_events"] or 0),
            estimated_cost_openai_usd=float(row["cost_openai"] or 0.0),
            estimated_cost_ocr_usd=float(row["cost_ocr"] or 0.0),
            estimated_cost_usd=float(row["cost_total"] or 0.0),
            last_seen_at=datetime.fromisoformat(str(row["last_seen_at"])),
        )
        for row in rows
    ]
    return UsageUsersResponse(total=total, items=items)


@router.get("/admin/api/usage/heavy", response_model=UsageHeavyResponse)
async def admin_usage_heavy(
    _admin: str = Depends(_verify_admin),
    period: UsagePeriod = Query(default="month"),
    metric: UsageMetric = Query(default="events"),
    self_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=200),
) -> UsageHeavyResponse:
    self_principals = _parse_self_principals(settings.admin_self_principals)
    principals_filter = self_principals if self_only else None
    rows = usage_store.heavy_users(
        period=period,
        metric=metric,
        principals=principals_filter,
        limit=limit,
    )
    items = [
        UsageHeavyRow(
            principal=str(row["principal"]),
            is_self=_is_self_principal(str(row["principal"])),
            total_events=int(row["total_events"]),
            estimated_cost_usd=float(row["estimated_cost_usd"]),
        )
        for row in rows
    ]
    return UsageHeavyResponse(period=period, metric=metric, items=items)
