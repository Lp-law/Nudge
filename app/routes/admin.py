import csv
import hmac
import io
import json
import secrets
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
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
from app.services.license_store import license_store
from app.services.usage_store import usage_store


router = APIRouter(tags=["admin"])
security = HTTPBasic(auto_error=False)
security_dependency = Depends(security)
settings = get_settings()
lead_store = LeadStore(settings.leads_db_path)


_CSRF_COOKIE_NAME = "nudge_csrf"
_CSRF_HEADER_NAME = "X-CSRF-Token"


def _generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _get_csrf_token_from_cookie(request: Request) -> str:
    return (request.cookies.get(_CSRF_COOKIE_NAME) or "").strip()


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


def _verify_csrf(request: Request) -> None:
    """Validate CSRF token from header/form against the cookie value."""
    cookie_token = _get_csrf_token_from_cookie(request)
    header_token = (request.headers.get(_CSRF_HEADER_NAME) or "").strip()
    provided_token = header_token
    if not provided_token:
        return  # Will be checked after body parse for form posts; for API calls header is required
    if not cookie_token or not provided_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    if not hmac.compare_digest(cookie_token, provided_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")


def _require_csrf(request: Request) -> None:
    """Strictly require a valid CSRF token (for state-changing endpoints)."""
    cookie_token = _get_csrf_token_from_cookie(request)
    header_token = (request.headers.get(_CSRF_HEADER_NAME) or "").strip()
    if not cookie_token or not header_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")


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


# ---------------------------------------------------------------------------
# Revenue, Retention & Funnel API endpoints
# ---------------------------------------------------------------------------


@router.get("/admin/api/revenue")
async def admin_revenue(_admin: str = Depends(_verify_admin)) -> dict:
    license_store.initialize()
    s = get_settings()
    prices = {"personal": s.personal_price_ils, "pro": s.pro_price_ils}
    with license_store._connect(readonly=True) as conn:
        rows = conn.execute(
            "SELECT tier, COUNT(*) AS cnt FROM licenses WHERE status='active' AND kind='paid' GROUP BY tier"
        ).fetchall()
    by_tier = {str(r["tier"]): int(r["cnt"]) for r in rows}
    personal_count = by_tier.get("personal", 0)
    pro_count = by_tier.get("pro", 0)
    mrr = personal_count * prices["personal"] + pro_count * prices["pro"]
    total_paid = personal_count + pro_count
    arpu = round(mrr / total_paid, 2) if total_paid else 0
    return {
        "mrr": mrr,
        "arr": mrr * 12,
        "arpu": arpu,
        "active_subscribers": total_paid,
        "by_tier": {"personal": personal_count, "pro": pro_count},
        "currency": "ILS",
    }


@router.get("/admin/api/retention")
async def admin_retention(_admin: str = Depends(_verify_admin)) -> dict:
    usage_store.initialize()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_dt = datetime.now(timezone.utc)
    day_7_ago = (today_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    day_30_ago = (today_dt - timedelta(days=30)).strftime("%Y-%m-%d")
    day_31_ago = (today_dt - timedelta(days=31)).strftime("%Y-%m-%d")
    day_60_ago = (today_dt - timedelta(days=60)).strftime("%Y-%m-%d")
    day_14_ago = (today_dt - timedelta(days=14)).strftime("%Y-%m-%d")

    with usage_store._connect(readonly=True) as conn:
        dau = int(conn.execute(
            "SELECT COUNT(DISTINCT principal) AS c FROM usage_events WHERE day = ?", (today,)
        ).fetchone()["c"])
        wau = int(conn.execute(
            "SELECT COUNT(DISTINCT principal) AS c FROM usage_events WHERE day >= ?", (day_7_ago,)
        ).fetchone()["c"])
        mau = int(conn.execute(
            "SELECT COUNT(DISTINCT principal) AS c FROM usage_events WHERE day >= ?", (day_30_ago,)
        ).fetchone()["c"])
        dau_mau = round((dau / mau) * 100, 1) if mau else 0

        churned_rows = conn.execute(
            """
            SELECT COUNT(*) AS c FROM (
                SELECT DISTINCT principal FROM usage_events WHERE day >= ? AND day < ?
                EXCEPT
                SELECT DISTINCT principal FROM usage_events WHERE day >= ?
            )
            """,
            (day_60_ago, day_31_ago, day_30_ago),
        ).fetchone()
        churned = int(churned_rows["c"])
        churn_rate = round((churned / (mau + churned)) * 100, 1) if (mau + churned) else 0

        total_events_month = int(conn.execute(
            "SELECT COUNT(*) AS c FROM usage_events WHERE day >= ?", (day_30_ago,)
        ).fetchone()["c"])
        avg_req = round(total_events_month / mau, 1) if mau else 0

        trend_rows = conn.execute(
            "SELECT day, COUNT(DISTINCT principal) AS dau FROM usage_events WHERE day >= ? GROUP BY day ORDER BY day",
            (day_14_ago,),
        ).fetchall()
        dau_trend = [{"day": str(r["day"]), "dau": int(r["dau"])} for r in trend_rows]

    return {
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "dau_mau": dau_mau,
        "churned": churned,
        "churn_rate": churn_rate,
        "avg_requests_per_user": avg_req,
        "dau_trend": dau_trend,
    }


@router.get("/admin/api/funnel")
async def admin_funnel(_admin: str = Depends(_verify_admin)) -> dict:
    license_store.initialize()
    usage_store.initialize()
    today_dt = datetime.now(timezone.utc)
    day_7_ago = (today_dt - timedelta(days=7)).strftime("%Y-%m-%d")

    with license_store._connect(readonly=True) as conn:
        total_trials = int(conn.execute(
            "SELECT COUNT(*) AS c FROM licenses WHERE kind='trial'"
        ).fetchone()["c"])

        trial_principals = [
            str(r["principal"]) for r in conn.execute(
                "SELECT principal FROM licenses WHERE kind='trial'"
            ).fetchall()
        ]

    active_trials = 0
    if trial_principals:
        with usage_store._connect(readonly=True) as uconn:
            placeholders = ",".join("?" for _ in trial_principals)
            active_trials = int(uconn.execute(
                f"SELECT COUNT(DISTINCT principal) AS c FROM usage_events WHERE principal IN ({placeholders}) AND day >= ?",
                [*trial_principals, day_7_ago],
            ).fetchone()["c"])

    with license_store._connect(readonly=True) as conn:
        converted = int(conn.execute(
            """
            SELECT COUNT(DISTINCT t.account_id) AS c
            FROM licenses t
            JOIN licenses p ON t.account_id = p.account_id AND p.kind = 'paid'
            WHERE t.kind = 'trial'
            """
        ).fetchone()["c"])

        conversion_rate = round((converted / total_trials) * 100, 1) if total_trials else 0

        tier_rows = conn.execute(
            "SELECT tier, COUNT(*) AS cnt FROM licenses WHERE status='active' GROUP BY tier"
        ).fetchall()
        tier_dist = {str(r["tier"]): int(r["cnt"]) for r in tier_rows}

    return {
        "total_trials": total_trials,
        "active_trials": active_trials,
        "converted": converted,
        "conversion_rate": conversion_rate,
        "tier_distribution": tier_dist,
    }


# ---------------------------------------------------------------------------
# Dashboard HTML
# ---------------------------------------------------------------------------


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, _admin: str = Depends(_verify_admin)) -> HTMLResponse:
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
    .tier-badge { display: inline-block; padding: 2px 8px; border-radius: 5px; font-size: 11px; font-weight: 600; }
    .tier-trial { background: #3a2a10; color: #f0c040; border: 1px solid #6b5a20; }
    .tier-personal { background: #1a2a3a; color: #60b0ff; border: 1px solid #2a5080; }
    .tier-pro { background: #1a3a2a; color: #40e080; border: 1px solid #208050; }
    .quota-bar-bg { width: 70px; height: 8px; background: #1a2338; border-radius: 4px; display: inline-block; vertical-align: middle; margin-left: 6px; }
    .quota-bar-fill { height: 100%; border-radius: 4px; }
    .quota-ok { background: #4f83ff; }
    .quota-warn { background: #f0a040; }
    .quota-full { background: #ff4060; }
    .green-value { color: #10B981; }
    .funnel-row { display: flex; align-items: center; margin-bottom: 10px; }
    .funnel-label { width: 160px; font-size: 13px; color: #99a8cb; flex-shrink: 0; }
    .funnel-bar-bg { flex: 1; height: 28px; background: #1a2338; border-radius: 6px; overflow: hidden; position: relative; }
    .funnel-bar-fill { height: 100%; border-radius: 6px; display: flex; align-items: center; padding-left: 10px; font-size: 12px; font-weight: 600; color: #fff; min-width: 40px; }
    .funnel-count { margin-left: 10px; font-size: 13px; font-weight: 600; flex-shrink: 0; width: 80px; text-align: right; }
  </style>
</head>
<body>
  <h2>Nudge Admin Dashboard</h2>
  <div class="muted">Lead/user management only. No clipboard/OCR/user-content data is stored here.</div>
  <div style="display:flex; gap:8px; margin:10px 0 14px 0;">
    <button onclick="downloadBackup()">Backup (.zip)</button>
    <button onclick="downloadCsv('/admin/api/export/licenses?format=csv', 'nudge-licenses.csv')">Export All Licenses</button>
    <button onclick="logoutDashboard()">Logout</button>
  </div>
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
    <div class="cards" style="grid-template-columns: repeat(3, minmax(100px, 1fr)); margin-bottom: 10px;">
      <div class="card"><div class="title"><span class="tier-badge tier-trial">Trial</span> users</div><div id="tier_trial_count" class="value">-</div></div>
      <div class="card"><div class="title"><span class="tier-badge tier-personal">Personal</span> users</div><div id="tier_personal_count" class="value">-</div></div>
      <div class="card"><div class="title"><span class="tier-badge tier-pro">Pro</span> users</div><div id="tier_pro_count" class="value">-</div></div>
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
      <thead><tr><th>User</th><th>License</th><th>Tier</th><th>Quota</th><th>Devices</th><th>Events</th><th>AI</th><th>OCR</th><th>Est. OpenAI $</th><th>Est. OCR $</th><th>Est. total $</th><th>Last seen</th></tr></thead>
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

  <!-- Revenue Panel -->
  <div class="panel">
    <h3>Revenue</h3>
    <div class="cards">
      <div class="card"><div class="title">MRR (Monthly Recurring)</div><div id="rev_mrr" class="value green-value">-</div></div>
      <div class="card"><div class="title">ARR (Annual Run Rate)</div><div id="rev_arr" class="value">-</div></div>
      <div class="card"><div class="title">Active Subscribers</div><div id="rev_subscribers" class="value">-</div></div>
      <div class="card"><div class="title">ARPU</div><div id="rev_arpu" class="value">-</div></div>
    </div>
    <div class="cards" style="grid-template-columns: repeat(2, minmax(100px, 1fr));">
      <div class="card"><div class="title"><span class="tier-badge tier-personal">Personal</span> subscribers</div><div id="rev_personal" class="value">-</div></div>
      <div class="card"><div class="title"><span class="tier-badge tier-pro">Pro</span> subscribers</div><div id="rev_pro" class="value">-</div></div>
    </div>
  </div>

  <!-- Retention & Engagement Panel -->
  <div class="panel">
    <h3>Retention & Engagement</h3>
    <div class="cards" style="grid-template-columns: repeat(3, minmax(100px, 1fr));">
      <div class="card"><div class="title">DAU (today)</div><div id="ret_dau" class="value">-</div></div>
      <div class="card"><div class="title">WAU (7d)</div><div id="ret_wau" class="value">-</div></div>
      <div class="card"><div class="title">MAU (30d)</div><div id="ret_mau" class="value">-</div></div>
      <div class="card"><div class="title">DAU/MAU ratio</div><div id="ret_dau_mau" class="value">-</div></div>
      <div class="card"><div class="title">Churn rate (30d)</div><div id="ret_churn" class="value">-</div></div>
      <div class="card"><div class="title">Avg req/user (30d)</div><div id="ret_avg_req" class="value">-</div></div>
    </div>
    <h4>DAU trend (last 14 days)</h4>
    <div id="dau_trend_chart"></div>
  </div>

  <!-- Conversion Funnel Panel -->
  <div class="panel">
    <h3>Conversion Funnel</h3>
    <div id="funnel_chart"></div>
    <div style="margin-top: 14px;">
      <h4>Tier Distribution (active licenses)</h4>
      <div id="tier_dist_chart"></div>
    </div>
  </div>

  <script>
    function getCsrfToken() {
      const m = document.cookie.match(/(?:^|;\\s*)nudge_csrf=([^;]*)/);
      return m ? decodeURIComponent(m[1]) : '';
    }
    async function fetchJson(url) {
      const r = await fetch(url, { credentials: 'same-origin', headers: { 'X-CSRF-Token': getCsrfToken() } });
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

    async function refreshRevenue() {
      const d = await fetchJson('/admin/api/revenue');
      document.getElementById('rev_mrr').textContent = '\\u20AA' + d.mrr.toLocaleString();
      document.getElementById('rev_arr').textContent = '\\u20AA' + d.arr.toLocaleString();
      document.getElementById('rev_subscribers').textContent = d.active_subscribers;
      document.getElementById('rev_arpu').textContent = '\\u20AA' + d.arpu.toLocaleString();
      document.getElementById('rev_personal').textContent = d.by_tier.personal;
      document.getElementById('rev_pro').textContent = d.by_tier.pro;
    }

    async function refreshRetention() {
      const d = await fetchJson('/admin/api/retention');
      document.getElementById('ret_dau').textContent = d.dau;
      document.getElementById('ret_wau').textContent = d.wau;
      document.getElementById('ret_mau').textContent = d.mau;
      document.getElementById('ret_dau_mau').textContent = d.dau_mau + '%';
      document.getElementById('ret_churn').textContent = d.churn_rate + '%';
      document.getElementById('ret_avg_req').textContent = d.avg_requests_per_user;
      const maxDau = Math.max(1, ...d.dau_trend.map(x => x.dau));
      document.getElementById('dau_trend_chart').innerHTML = d.dau_trend.map(x =>
        `<div style="margin-bottom:8px"><div class="muted">${esc(x.day)} (${x.dau})</div><div class="bar" style="width:${pct(x.dau,maxDau)}"></div></div>`
      ).join('') || '<div class="muted">No data</div>';
    }

    async function refreshFunnel() {
      const d = await fetchJson('/admin/api/funnel');
      const maxVal = Math.max(1, d.total_trials);
      const steps = [
        { label: 'Total Trials', count: d.total_trials, pctOf: d.total_trials, color: '#4f83ff' },
        { label: 'Active Trials (7d)', count: d.active_trials, pctOf: d.total_trials, color: '#7b6dff' },
        { label: 'Converted to Paid', count: d.converted, pctOf: d.total_trials, color: '#10B981' },
      ];
      document.getElementById('funnel_chart').innerHTML = steps.map(s => {
        const pctVal = s.pctOf ? Math.round((s.count / s.pctOf) * 100) : 0;
        const barW = Math.max(3, Math.round((s.count / maxVal) * 100));
        return `<div class="funnel-row">
          <div class="funnel-label">${esc(s.label)}</div>
          <div class="funnel-bar-bg">
            <div class="funnel-bar-fill" style="width:${barW}%;background:${s.color};">${pctVal}%</div>
          </div>
          <div class="funnel-count">${s.count}</div>
        </div>`;
      }).join('') + `<div class="muted" style="margin-top:6px;">Conversion rate: <strong>${d.conversion_rate}%</strong></div>`;

      // Tier distribution
      const dist = d.tier_distribution || {};
      const tiers = Object.entries(dist);
      const totalLic = tiers.reduce((s, [, v]) => s + v, 0) || 1;
      const tierColors = { trial: '#f0c040', personal: '#60b0ff', pro: '#40e080' };
      document.getElementById('tier_dist_chart').innerHTML = tiers.map(([tier, cnt]) => {
        const pctVal = Math.round((cnt / totalLic) * 100);
        const barW = Math.max(3, pctVal);
        const color = tierColors[tier] || '#4f83ff';
        return `<div class="funnel-row">
          <div class="funnel-label"><span class="tier-badge tier-${esc(tier)}">${esc(tier)}</span></div>
          <div class="funnel-bar-bg">
            <div class="funnel-bar-fill" style="width:${barW}%;background:${color};">${pctVal}%</div>
          </div>
          <div class="funnel-count">${cnt}</div>
        </div>`;
      }).join('') || '<div class="muted">No data</div>';
    }

    async function bootstrap() {
      try {
        await Promise.all([refreshStats(), refreshUsers(), refreshUsage(), refreshRevenue(), refreshRetention(), refreshFunnel()]);
      } catch {
        alert('Failed to load dashboard data.');
      }
    }
    function logoutDashboard() {
      window.location.href = `/admin/logout?ts=${Date.now()}`;
    }
    async function downloadBackup() {
      const r = await fetch('/admin/api/backup', { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': getCsrfToken() } });
      if (!r.ok) { alert('Backup failed.'); return; }
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      const cd = r.headers.get('Content-Disposition') || '';
      const fnMatch = cd.match(/filename="?([^"]+)"?/);
      a.download = fnMatch ? fnMatch[1] : 'nudge-admin-backup.zip';
      a.click();
      URL.revokeObjectURL(a.href);
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
        `<div style="display:flex;justify-content:space-between;margin-bottom:6px"><span>${esc(row.principal_label)}${row.is_self ? ' <strong>(Me/Admin)</strong>' : ''}<span class="muted" style="margin-left:6px">(${esc(row.principal)})</span></span><strong>${row.total_events} / $${money(row.estimated_cost_usd)}</strong></div>`
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
          <td>${esc(row.principal_label)} ${row.is_self ? '<strong>(Me/Admin)</strong>' : ''}<div class="muted">${esc(row.account_email || row.principal)}</div></td>
          <td>${esc((row.license_kind || '-') + ' / ' + (row.license_status || '-'))}<div class="muted">${esc(row.key_masked || '')}</div></td>
          <td>${row.distinct_devices}</td>
          <td>${row.total_events}</td>
          <td>${row.ai_events}</td>
          <td>${row.ocr_events}</td>
          <td>$${money(row.estimated_cost_openai_usd)}</td>
          <td>$${money(row.estimated_cost_ocr_usd)}</td>
          <td>$${money(row.estimated_cost_usd)}</td>
          <td>${esc(row.last_seen_at)}</td>
        </tr>
      `).join('') || '<tr><td colspan="10" class="muted">No usage rows found</td></tr>';
      renderHeavy('usage_heavy_events', heavyEvents.items);
      renderHeavy('usage_heavy_cost', heavyCost.items);
    }
    bootstrap();
  </script>
</body>
</html>
    """.strip()
    csrf_token = _get_csrf_token_from_cookie(request) or _generate_csrf_token()
    response = HTMLResponse(content=html)
    response.set_cookie(
        key=_CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # JS needs to read it
        samesite="strict",
        secure=False,  # set True in production behind HTTPS
        path="/admin",
    )
    return response


@router.get("/admin/logout", response_class=HTMLResponse)
async def admin_logout(_admin: str = Depends(_verify_admin)) -> HTMLResponse:
    html = """
<!doctype html>
<html>
<head><meta charset="utf-8" /><title>Nudge Admin Logout</title></head>
<body style="font-family:Segoe UI,Arial,sans-serif; margin:20px;">
  <h3>Logged out</h3>
  <div>Close this tab or open <a href="/admin">/admin</a> to sign in again.</div>
</body>
</html>
    """.strip()
    return HTMLResponse(
        content=html,
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Basic"},
    )


@router.post("/admin/api/backup")
async def admin_backup(request: Request, _admin: str = Depends(_verify_admin)) -> StreamingResponse:
    _require_csrf(request)
    candidates = [Path(settings.leads_db_path).expanduser()]
    existing = [p for p in candidates if p.exists() and p.is_file()]
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No backup files found.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    content = io.BytesIO()
    with zipfile.ZipFile(content, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in existing:
            zf.write(file_path, arcname=f"data/{file_path.name}")
        zf.writestr(
            "metadata.json",
            json.dumps(
                {
                    "generated_at_utc": generated_at,
                    "files": [f"data/{p.name}" for p in existing],
                    "note": "Contains admin dashboard metadata databases only.",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    content.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    headers = {"Content-Disposition": f'attachment; filename="nudge-admin-backup-{stamp}.zip"'}
    return StreamingResponse(content, media_type="application/zip", headers=headers)


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
    profiles = license_store.profiles_by_principal([str(r["principal"]) for r in rows])

    # Batch lookup leads by account emails
    account_emails = [
        str(profiles.get(str(r["principal"]), {}).get("account_email") or "")
        for r in rows
    ]
    leads_map = lead_store.leads_by_emails([e for e in account_emails if e])

    # Compute quota limits per tier
    _settings = get_settings()

    items: list[UsageUserRow] = []
    for row in rows:
        p = str(row["principal"])
        prof = profiles.get(p, {})
        email = str(prof.get("account_email") or "") or None
        tier = str(prof.get("license_tier") or "") or None
        lead = leads_map.get((email or "").strip().lower(), {}) if email else {}
        total_ev = int(row["total_events"] or 0)

        # Quota: trial=50 lifetime, personal=200/month, pro=unlimited
        quota_limit: int | None = None
        quota_used: int | None = None
        if tier == "trial":
            quota_limit = _settings.trial_max_requests
            quota_used = total_ev
        elif tier == "personal":
            quota_limit = _settings.personal_monthly_requests
            quota_used = total_ev
        elif tier == "pro":
            quota_limit = None
            quota_used = None

        items.append(
            UsageUserRow(
                principal=p,
                principal_label=(
                    str(prof.get("account_full_name") or "").strip()
                    or str(prof.get("account_email") or "").strip()
                    or p
                ),
                account_email=email,
                license_kind=str(prof.get("license_kind") or "") or None,
                license_tier=tier,
                license_status=str(prof.get("license_status") or "") or None,
                key_masked=str(prof.get("key_masked") or "") or None,
                is_self=_is_self_principal(p),
                distinct_devices=int(row["distinct_devices"] or 0),
                total_events=total_ev,
                ai_events=int(row["ai_events"] or 0),
                ocr_events=int(row["ocr_events"] or 0),
                estimated_cost_openai_usd=float(row["cost_openai"] or 0.0),
                estimated_cost_ocr_usd=float(row["cost_ocr"] or 0.0),
                estimated_cost_usd=float(row["cost_total"] or 0.0),
                last_seen_at=datetime.fromisoformat(str(row["last_seen_at"])),
                lead_full_name=lead.get("full_name"),
                lead_phone=lead.get("phone"),
                lead_occupation=lead.get("occupation"),
                lead_source=lead.get("source"),
                quota_used=quota_used,
                quota_limit=quota_limit,
            )
        )
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
    profiles = license_store.profiles_by_principal([str(r["principal"]) for r in rows])
    items = [
        UsageHeavyRow(
            principal=str(row["principal"]),
            principal_label=(
                str(profiles.get(str(row["principal"]), {}).get("account_full_name") or "").strip()
                or str(profiles.get(str(row["principal"]), {}).get("account_email") or "").strip()
                or str(row["principal"])
            ),
            account_email=str(profiles.get(str(row["principal"]), {}).get("account_email") or "") or None,
            license_kind=str(profiles.get(str(row["principal"]), {}).get("license_kind") or "") or None,
            license_status=str(profiles.get(str(row["principal"]), {}).get("license_status") or "") or None,
            key_masked=str(profiles.get(str(row["principal"]), {}).get("key_masked") or "") or None,
            is_self=_is_self_principal(str(row["principal"])),
            total_events=int(row["total_events"]),
            estimated_cost_usd=float(row["estimated_cost_usd"]),
        )
        for row in rows
    ]
    return UsageHeavyResponse(period=period, metric=metric, items=items)


# ---------------------------------------------------------------------------
# CSV Export endpoints
# ---------------------------------------------------------------------------


def _csv_response(rows: list[dict], columns: list[str], filename: str) -> StreamingResponse:
    """Build a CSV StreamingResponse from a list of dicts."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers=headers,
    )


@router.get("/admin/api/export/leads")
async def admin_export_leads(
    request: Request,
    _admin: str = Depends(_verify_admin),
    search: str = Query(default="", max_length=120),
    occupation: str = Query(default="", max_length=120),
    source: str = Query(default="", max_length=30),
    format: str = Query(default="csv", max_length=10),
) -> StreamingResponse:
    _verify_csrf(request)
    total, rows = lead_store.list_leads(
        search=search,
        occupation=occupation,
        source=source,
        joined_from=None,
        joined_to=None,
        limit=10000,
        offset=0,
    )
    items = [
        {
            "full_name": str(r["full_name"]),
            "email": str(r["email"]),
            "phone": str(r["phone"] or ""),
            "occupation": str(r["occupation"]),
            "source": str(r["source"]),
            "app_version": str(r["app_version"]),
            "status": str(r["status"]),
            "joined_at": str(r["created_at"]),
        }
        for r in rows
    ]
    columns = ["full_name", "email", "phone", "occupation", "source", "app_version", "status", "joined_at"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _csv_response(items, columns, f"nudge-leads-{stamp}.csv")


@router.get("/admin/api/export/usage")
async def admin_export_usage(
    request: Request,
    _admin: str = Depends(_verify_admin),
    period: UsagePeriod = Query(default="month"),
    format: str = Query(default="csv", max_length=10),
) -> StreamingResponse:
    _verify_csrf(request)
    total, rows = usage_store.users(
        period=period,
        search="",
        route_type="",
        action="",
        principals=None,
        limit=10000,
        offset=0,
    )
    profiles = license_store.profiles_by_principal([str(r["principal"]) for r in rows])
    items = []
    for row in rows:
        principal = str(row["principal"])
        profile = profiles.get(principal, {})
        items.append(
            {
                "principal": principal,
                "account_email": str(profile.get("account_email") or ""),
                "full_name": str(profile.get("account_full_name") or ""),
                "tier": str(profile.get("license_tier") or ""),
                "total_events": int(row["total_events"] or 0),
                "ai_events": int(row["ai_events"] or 0),
                "ocr_events": int(row["ocr_events"] or 0),
                "estimated_cost_openai_usd": float(row["cost_openai"] or 0.0),
                "estimated_cost_ocr_usd": float(row["cost_ocr"] or 0.0),
                "estimated_cost_usd": float(row["cost_total"] or 0.0),
                "last_seen_at": str(row["last_seen_at"]),
            }
        )
    columns = [
        "principal", "account_email", "full_name", "tier",
        "total_events", "ai_events", "ocr_events",
        "estimated_cost_openai_usd", "estimated_cost_ocr_usd", "estimated_cost_usd",
        "last_seen_at",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _csv_response(items, columns, f"nudge-usage-{stamp}.csv")


@router.get("/admin/api/export/licenses")
async def admin_export_licenses(
    request: Request,
    _admin: str = Depends(_verify_admin),
    format: str = Query(default="csv", max_length=10),
) -> StreamingResponse:
    _verify_csrf(request)
    items = license_store.all_licenses_for_export()
    columns = [
        "account_email", "full_name", "kind", "tier", "status",
        "created_at", "expires_at", "key_masked",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _csv_response(items, columns, f"nudge-licenses-{stamp}.csv")
