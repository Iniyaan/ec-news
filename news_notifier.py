"""
EC NEWS - Daily Public Affairs News Feed
-----------------------------------------
Searches Google News (limited to your chosen news websites) for your
Tamil Nadu / District / India / Global topics, keeps ONLY articles from
the news window below, ranks each one's URGENCY (High/Medium/Low) with
Gemini AI, writes an Executive Summary, and builds a static website page
(index.html).

NEWS WINDOW (India Standard Time):
    yesterday 6:30 PM  ->  today 4:00 PM
    e.g. a run on 08-10-2026 covers 07-10-2026 6:30 PM to 08-10-2026 4:00 PM

Designed to run once a day via GitHub Actions' free scheduled workflow.
GitHub Pages then serves index.html as your own website automatically.

The Gemini key is read from an environment variable first (set as a
GitHub Secret when deployed), falling back to the value below for local
testing.
"""

import html as html_lib
import json
import os
import time
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# India Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# ======================= CONFIG (edit this part) =======================

# Company/report name shown at the top of the page and in the Executive Summary
COMPANY_NAME = "Pou Chen Group / High Glory Footwear India"

# ---- NEWS WINDOW (India time) -----------------------------------------
# Only articles published between "yesterday at START" and "today at END" are shown.
WINDOW_START_HOUR, WINDOW_START_MINUTE = 18, 30   # yesterday 6:30 PM
WINDOW_END_HOUR, WINDOW_END_MINUTE = 16, 0        # today 4:00 PM

# ---- KEYWORDS ---------------------------------------------------------
# Each entry is  ("heading shown on the website", "Google News search query").
# In the queries:  OR  = any of these words,  "quotes" = exact phrase.

# Topics tracked for EVERY district (used by the District Focus section)
DISTRICT_TOPICS = (
    "(government OR industry OR employment OR infrastructure OR labour OR "
    "environment OR power OR water OR logistics OR accident OR incident)"
)

KEYWORDS_BY_SCOPE = {
    "Tamil Nadu": [
        ("Government policies / GOs / notifications",
         '"Tamil Nadu" ("government order" OR "G.O." OR notification OR gazette OR policy OR cabinet)'),
        ("Industry & manufacturing",
         '"Tamil Nadu" (industry OR manufacturing OR factory OR "plant expansion" OR investment)'),
        ("SIPCOT / industrial parks",
         '(SIPCOT OR SIDCO OR "industrial park" OR "industrial estate" OR "industrial corridor") "Tamil Nadu"'),
        ("Labour & employment",
         '"Tamil Nadu" (labour OR workers OR employment OR wages OR strike OR union OR recruitment)'),
        ("TNSDC / DEO / DSO / job fairs",
         '(TNSDC OR "job fair" OR "skill development" OR "District Employment Office" OR "employment exchange") "Tamil Nadu"'),
        ("Power / TANGEDCO / industrial tariffs",
         '(TANGEDCO OR TNPDCL OR TANTRANSCO OR TNEB OR "Tamil Nadu power" OR "Tamil Nadu electricity" OR "Tamil Nadu power tariff")'),
        ("Water & environment / TNPCB",
         '(TNPCB OR "Pollution Control Board" OR "environmental clearance" OR "water supply" OR groundwater OR effluent OR pollution) "Tamil Nadu"'),
        ("Roads, logistics, ports, airports & railways",
         '"Tamil Nadu" (road OR highway OR logistics OR port OR airport OR railway)'),
        ("Footwear / leather / textile / apparel",
         '(footwear OR leather OR textile OR apparel OR garment) ("Tamil Nadu" OR Chennai OR Vellore OR Ranipet OR Ambur OR Tiruppur)'),
        ("Major risks, accidents, disruptions",
         '"Tamil Nadu" (accident OR "factory fire" OR blast OR flood OR cyclone OR "heavy rain" OR "power cut" OR disruption)'),
    ],
    "District Focus": [
        ("Chennai", f"(Chennai) {DISTRICT_TOPICS}"),
        ("Kallakurichi", f"(Kallakurichi) {DISTRICT_TOPICS}"),
        ("Chengalpattu", f"(Chengalpattu OR Chengalpet) {DISTRICT_TOPICS}"),
        ("Kancheepuram / Kanchipuram", f"(Kancheepuram OR Kanchipuram) {DISTRICT_TOPICS}"),
        ("Tiruvallur / Thiruvallur", f"(Tiruvallur OR Thiruvallur) {DISTRICT_TOPICS}"),
    ],
    "India": [
        ("Government schemes and programmes",
         '"central government" (scheme OR programme OR yojana) (launched OR approved OR announced OR extended)'),
        ("Cabinet decisions",
         '"Union Cabinet" (approves OR approved OR decision OR clears)'),
        ("New policies / rules / notifications",
         'India (policy OR rules OR notification OR guidelines OR circular) (notified OR issued OR released OR amended) (industry OR manufacturing OR trade OR labour)'),
        ("DPIIT / DGFT / Labour / Commerce / Textiles / Environment / Power",
         '(DPIIT OR DGFT OR "Ministry of Commerce" OR "Ministry of Labour" OR "Ministry of Textiles" OR "Ministry of Environment" OR "Ministry of Power")'),
        ("Manufacturing & investment",
         'India manufacturing (investment OR expansion OR "new plant" OR "new factory")'),
        ("PLI / Make in India",
         '("PLI scheme" OR "production linked incentive" OR "Make in India")'),
        ("Trade & exports",
         'India (exports OR "export growth" OR "trade deficit" OR "export promotion" OR "trade data")'),
        ("Labour and employment",
         'India ("labour code" OR "labour law" OR "minimum wage" OR EPFO OR ESIC OR "gig workers" OR employment)'),
        ("Infrastructure",
         'India (infrastructure OR highway OR railway OR "freight corridor" OR port OR airport OR "power transmission") (project OR approved OR tender OR delay)'),
        ("Major regulatory developments",
         'India (regulation OR regulatory OR "new rules" OR amendment OR "Supreme Court" OR NGT) (industry OR manufacturing OR environment OR labour OR trade)'),
    ],
    "Global": [
        ("Manufacturing",
         'global manufacturing (shift OR relocation OR slowdown OR PMI OR "factory output")'),
        ("Tariffs & trade restrictions",
         '(tariff OR tariffs OR "trade restrictions" OR "export curbs" OR "import duty") (US OR China OR EU OR India)'),
        ("India-EU / India-US / China developments",
         '("India EU" OR "India US" OR "India China") (trade OR FTA OR agreement OR tariff OR talks)'),
        ("Supply-chain disruptions",
         '("supply chain" OR "supply-chain") (disruption OR shortage OR delay OR bottleneck)'),
        ("Shipping / ports",
         '(shipping OR "container freight" OR "freight rates" OR "Red Sea" OR "port congestion" OR Suez)'),
        ("Critical minerals",
         '("critical minerals" OR "rare earth" OR lithium OR cobalt) (supply OR export OR restrictions OR India)'),
        ("Semiconductor supply chain",
         '(semiconductor OR chip OR chips) ("supply chain" OR shortage OR export OR India OR fab)'),
        ("Global footwear / textile developments",
         '(footwear OR sneaker OR "sports shoe" OR textile OR apparel OR garment) (global OR exports OR sourcing OR Vietnam OR Bangladesh OR China OR Nike OR Adidas)'),
        ("ESG / sustainability regulations",
         '(ESG OR sustainability OR "due diligence") (regulation OR rules OR directive OR mandate OR disclosure)'),
        ("EU CBAM / EUDR / CSRD / forced-labour rules",
         '(CBAM OR EUDR OR CSRD OR CSDDD OR "forced labour" OR "forced labor") (EU OR rules OR regulation OR ban OR deadline)'),
    ],
}

# Websites to search across (applies to every keyword above).
SITE = [
    "timesofindia.indiatimes.com",
    "thehindu.com",
    "ndtv.com",
    "indiatoday.in",
    "news18.com",
    "dailythanthi.com",
    "dinamalar.com",
    "thanthitv.com",
    "puthiyathalaimurai.com",
]

# Max number of articles to show per keyword section
MAX_ARTICLES = 6

# Turn AI analysis (problem summary + suggestion + urgency ranking) on or off
ENABLE_AI_ANALYSIS = True

# Get this FREE key (no credit card needed) from https://aistudio.google.com/apikey
# For GitHub Actions, this is overridden automatically by a GitHub Secret named GEMINI_API_KEY.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "PASTE_YOUR_REAL_GEMINI_KEY_HERE")

# Only analyze the top N articles per keyword section with AI, to stay under
# Gemini's free-tier rate limit (kept low on purpose)
MAX_ARTICLES_TO_ANALYZE = 1

# Filename for the generated website page (used by GitHub Pages)
OUTPUT_HTML_FILE = "index.html"

# =========================== END OF CONFIG ==============================


def compute_news_window(now=None):
    """Return (start, end) of the news window as India-time datetimes:
    yesterday at WINDOW_START  ->  today at WINDOW_END."""
    now_ist = (now or datetime.now(IST)).astimezone(IST)
    end = now_ist.replace(
        hour=WINDOW_END_HOUR, minute=WINDOW_END_MINUTE, second=0, microsecond=0
    )
    start = (now_ist - timedelta(days=1)).replace(
        hour=WINDOW_START_HOUR, minute=WINDOW_START_MINUTE, second=0, microsecond=0
    )
    return start, end


def fetch_news_for_keyword(query, window_start, window_end, seen_keys=None, max_retries=3):
    """Fetch matching articles from Google News RSS for one search query.
    Keeps only articles published inside the news window, and skips any
    article already shown under another heading (seen_keys).
    Retries with a growing delay if Google returns a transient error (like 503)."""
    if seen_keys is None:
        seen_keys = set()

    full_query = f"({query})"
    if SITE:
        if isinstance(SITE, list):
            site_filter = " OR ".join(f"site:{s}" for s in SITE)
            full_query += f" ({site_filter})"
        else:
            full_query += f" site:{SITE}"
    full_query += " when:2d"  # ask Google for the last 2 days only; exact window applied below

    encoded_query = urllib.parse.quote(full_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"

    last_error = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall("./channel/item")

            articles = []
            for item in items:
                if len(articles) >= MAX_ARTICLES:
                    break
                title = item.findtext("title", default="No title")
                link = item.findtext("link", default="")
                pub_date = item.findtext("pubDate", default="")
                source_el = item.find("source")
                source = source_el.text if source_el is not None else ""
                snippet = item.findtext("description", default="")

                # Keep only articles inside the news window (no date = can't verify = skip)
                if not pub_date:
                    continue
                try:
                    published = parsedate_to_datetime(pub_date)
                except Exception:
                    continue
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if published < window_start or published > window_end:
                    continue

                # Skip articles already shown under another heading
                link_key = link.strip()
                title_key = title.strip().lower()
                if (link_key and link_key in seen_keys) or title_key in seen_keys:
                    continue
                if link_key:
                    seen_keys.add(link_key)
                seen_keys.add(title_key)

                articles.append({
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "source": source,
                    "snippet": snippet,
                })
            return articles
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(8 * (attempt + 1))
                continue

    raise last_error


def analyze_article(title, snippet, max_retries=3):
    """Ask Gemini (free tier) to summarize the core problem, suggest a solution,
    and rank the article's URGENCY (how time-sensitive it is) as High/Medium/Low.
    Retries with a growing delay if the free tier's rate limit (429) is hit."""
    prompt = (
        "Here is a news headline and snippet:\n\n"
        f"Title: {title}\n"
        f"Snippet: {snippet}\n\n"
        "Respond with ONLY a JSON object (no markdown, no extra text) in this exact format:\n"
        '{"urgency": "High" or "Medium" or "Low", "analysis": "2-3 short sentences covering '
        '(1) the core problem/issue this news is about, and (2) one practical response or '
        'action someone could take regarding it"}\n\n'
        "Urgency guide: High = breaking/time-critical news needing action within hours/days. "
        "Medium = relevant but not urgent. Low = background/historical/opinion, no time pressure."
    )

    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
    )

    for attempt in range(max_retries):
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read())
                raw_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                cleaned = raw_text.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(cleaned)
                urgency = parsed.get("urgency", "Medium")
                if urgency not in ("High", "Medium", "Low"):
                    urgency = "Medium"
                analysis = parsed.get("analysis", "").strip()
                return urgency, analysis
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            return "Medium", f"(AI analysis unavailable: HTTP Error {e.code}: {e.reason})"
        except Exception as e:
            return "Medium", f"(AI analysis unavailable: {e})"

    return "Medium", "(AI analysis unavailable: rate limit persisted after retries)"


def analyze_and_sort_articles(articles):
    """Run AI analysis on the top articles of one keyword section and sort by urgency."""
    analyzed = []
    for i, a in enumerate(articles):
        if ENABLE_AI_ANALYSIS and i < MAX_ARTICLES_TO_ANALYZE:
            urgency, analysis = analyze_article(a["title"], a["snippet"])
            time.sleep(6.5)
        else:
            urgency, analysis = "Unranked", ""
        analyzed.append({**a, "urgency": urgency, "analysis": analysis})

    urgency_order = {"High": 0, "Medium": 1, "Low": 2, "Unranked": 3}
    analyzed.sort(key=lambda x: urgency_order.get(x["urgency"], 3))
    return analyzed


def generate_executive_summary(results_by_scope, max_retries=3):
    """Make ONE combined Gemini call across the day's most urgent articles to
    produce an Executive Summary: top Key Findings, each with a business
    Implication for COMPANY_NAME, plus an Overall Risk Rating."""
    candidates = []
    for scope, results_by_keyword in results_by_scope.items():
        for keyword, analyzed in results_by_keyword.items():
            for a in analyzed:
                if a["urgency"] != "Unranked" and a["analysis"]:
                    candidates.append({**a, "scope": scope, "keyword": keyword})

    if not candidates:
        return None  # nothing analyzed today, skip the summary

    urgency_order = {"High": 0, "Medium": 1, "Low": 2}
    candidates.sort(key=lambda x: urgency_order.get(x["urgency"], 3))
    top_candidates = candidates[:12]  # cap input size to keep the prompt short

    bullet_lines = []
    for c in top_candidates:
        bullet_lines.append(
            f"- [{c['urgency']}] ({c['scope']}) {c['title']}: {c['analysis']}"
        )
    articles_block = "\n".join(bullet_lines)

    prompt = (
        f"You are a business intelligence analyst writing a daily briefing for {COMPANY_NAME}, "
        "a footwear manufacturer in India. Below are today's most relevant news items, each "
        "tagged with an urgency level and a short analysis:\n\n"
        f"{articles_block}\n\n"
        "Respond with ONLY a JSON object (no markdown, no extra text) in this exact format:\n"
        '{"key_findings": [{"finding": "one sentence describing the finding", '
        '"implication": "one sentence on what this means for the company"}, ... up to 3 items], '
        '"overall_risk": "High" or "Medium" or "Low", '
        '"overall_risk_reason": "one or two sentences explaining the overall rating"}\n\n'
        "Pick the 3 most business-relevant findings across all the items above. "
        "Be specific and practical, in the style of a corporate intelligence report."
    )

    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
    )

    for attempt in range(max_retries):
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read())
                raw_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                cleaned = raw_text.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(cleaned)
                if parsed.get("overall_risk") not in ("High", "Medium", "Low"):
                    parsed["overall_risk"] = "Medium"
                return parsed
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            print(f"Executive summary unavailable: HTTP Error {e.code}: {e.reason}")
            return None
        except Exception as e:
            print(f"Executive summary unavailable: {e}")
            return None

    return None


def build_html_page(results_by_scope, executive_summary=None, window_start=None, window_end=None):
    """Build a static HTML page showing the news window's articles, grouped by scope
    (Tamil Nadu -> District Focus -> India -> Global), then by heading within each,
    ranked by urgency, with AI analysis. All times are shown in India time (IST)."""
    updated_at = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    urgency_colors = {"High": "#dc2626", "Medium": "#d97706", "Low": "#16a34a", "Unranked": "#6b7280"}

    window_label = ""
    if window_start and window_end:
        window_label = (
            f"News window: {window_start.astimezone(IST):%d %b, %I:%M %p} "
            f"&rarr; {window_end.astimezone(IST):%d %b, %I:%M %p} IST &middot; "
        )

    nav_links = []
    scope_blocks = []

    for scope, results_by_keyword in results_by_scope.items():
        scope_id = html_lib.escape(scope.lower().replace(" ", "-").replace("(", "").replace(")", ""))
        nav_links.append(f'<a href="#{scope_id}">{html_lib.escape(scope)}</a>')

        sections_html = []
        for keyword, analyzed in results_by_keyword.items():
            cards = []
            if not analyzed:
                cards.append('<p class="empty">No new articles in this news window.</p>')
            for a in analyzed:
                color = urgency_colors.get(a["urgency"], "#6b7280")
                badge = (
                    f'<span class="badge" style="background:{color}">{html_lib.escape(a["urgency"].upper())}</span>'
                    if a["urgency"] != "Unranked" else ""
                )
                analysis_html = (
                    f'<p class="analysis">{html_lib.escape(a["analysis"])}</p>' if a["analysis"] else ""
                )
                published_str = ""
                if a.get("pub_date"):
                    try:
                        dt = parsedate_to_datetime(a["pub_date"])
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        published_str = dt.astimezone(IST).strftime("%d %b, %I:%M %p IST")
                    except Exception:
                        published_str = ""
                source_line = html_lib.escape(a["source"])
                if published_str:
                    source_line += f" &middot; {html_lib.escape(published_str)}"
                cards.append(f'''
                <div class="card">
                  {badge}
                  <h3><a href="{html_lib.escape(a["link"])}" target="_blank" rel="noopener">{html_lib.escape(a["title"])}</a></h3>
                  <p class="source">{source_line}</p>
                  {analysis_html}
                </div>''')

            sections_html.append(f'''
            <section>
              <h3 class="keyword-heading">{html_lib.escape(keyword)}</h3>
              <div class="grid">{"".join(cards)}</div>
            </section>''')

        scope_blocks.append(f'''
        <div class="scope-block" id="{scope_id}">
          <h2 class="scope-heading">{html_lib.escape(scope)}</h2>
          {"".join(sections_html)}
        </div>''')

    nav_html = " &nbsp;|&nbsp; ".join(nav_links)

    exec_summary_html = ""
    if executive_summary:
        risk = executive_summary.get("overall_risk", "Medium")
        risk_colors = {"High": "#dc2626", "Medium": "#d97706", "Low": "#16a34a"}
        risk_color = risk_colors.get(risk, "#6b7280")
        reason = html_lib.escape(executive_summary.get("overall_risk_reason", ""))

        findings_html = []
        for i, kf in enumerate(executive_summary.get("key_findings", []), 1):
            findings_html.append(f'''
            <div class="finding">
              <p class="finding-title">Key Finding {i}: {html_lib.escape(kf.get("finding", ""))}</p>
              <p class="finding-implication">&rarr; Implication for {html_lib.escape(COMPANY_NAME)}: {html_lib.escape(kf.get("implication", ""))}</p>
            </div>''')

        exec_summary_html = f'''
        <div class="exec-summary">
          <h2 class="exec-title">EXECUTIVE SUMMARY</h2>
          {"".join(findings_html)}
          <p class="overall-risk">
            Overall risk rating:
            <span class="risk-dot" style="background:{risk_color}"></span>
            <strong>{html_lib.escape(risk)}</strong> &mdash; {reason}
          </p>
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EC NEWS</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:#f8fafc; color:#1e293b; margin:0; padding:0 0 60px; }}
  header {{ background:#1e293b; color:#fff; padding:28px 20px; text-align:center; }}
  header h1 {{ margin:0 0 6px; font-size:1.6rem; }}
  header p {{ margin:0; color:#94a3b8; font-size:0.9rem; }}
  nav {{ background:#0f172a; text-align:center; padding:12px; font-size:0.9rem; }}
  nav a {{ color:#93c5fd; text-decoration:none; font-weight:600; }}
  nav a:hover {{ text-decoration:underline; }}
  main {{ max-width:1000px; margin:0 auto; padding:24px 20px; }}
  .exec-summary {{ background:#fff; border:1px solid #cbd5e1; border-left:5px solid #1d4ed8; border-radius:10px; padding:22px 24px; margin-bottom:36px; }}
  .exec-title {{ font-size:1.1rem; letter-spacing:0.05em; color:#1d4ed8; margin:0 0 16px; }}
  .finding {{ margin-bottom:14px; }}
  .finding-title {{ font-weight:600; margin:0 0 4px; }}
  .finding-implication {{ color:#334155; margin:0; padding-left:14px; font-size:0.94rem; }}
  .overall-risk {{ margin-top:18px; padding-top:14px; border-top:1px solid #e2e8f0; font-size:0.95rem; }}
  .risk-dot {{ display:inline-block; width:12px; height:12px; border-radius:50%; margin:0 4px; vertical-align:middle; }}
  .scope-block {{ margin-bottom:48px; scroll-margin-top:16px; }}
  .scope-heading {{ font-size:1.5rem; background:#1e293b; color:#fff; padding:10px 16px; border-radius:8px; margin-bottom:8px; }}
  section {{ margin-bottom:30px; margin-top:20px; }}
  .keyword-heading {{ font-size:1.05rem; color:#334155; border-bottom:2px solid #e2e8f0; padding-bottom:8px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(280px,1fr)); gap:16px; margin-top:14px; }}
  .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:16px; position:relative; }}
  .card h3 {{ margin:8px 0 4px; font-size:1rem; line-height:1.4; }}
  .card h3 a {{ color:#1e293b; text-decoration:none; }}
  .card h3 a:hover {{ text-decoration:underline; }}
  .source {{ color:#64748b; font-size:0.8rem; margin:0 0 8px; }}
  .analysis {{ font-size:0.88rem; color:#334155; background:#f1f5f9; padding:10px; border-radius:6px; margin:0; }}
  .badge {{ display:inline-block; color:#fff; font-size:0.7rem; font-weight:600; padding:2px 8px; border-radius:999px; margin-bottom:6px; }}
  .empty {{ color:#94a3b8; font-style:italic; }}
</style>
</head>
<body>
<header>
  <h1>{html_lib.escape(COMPANY_NAME)}</h1>
  <p>EC NEWS &middot; {window_label}Updated: {updated_at}</p>
</header>
<nav>{nav_html}</nav>
<main>
{exec_summary_html}
{"".join(scope_blocks)}
</main>
</body>
</html>'''


def main():
    window_start, window_end = compute_news_window()
    shown_end = min(window_end, datetime.now(IST))
    print(
        f"News window (IST): {window_start:%d %b %Y %I:%M %p} -> {shown_end:%d %b %Y %I:%M %p}"
    )

    seen_keys = set()  # so the same article isn't repeated under several headings
    total_articles = 0
    results_by_scope = {}
    for scope, entries in KEYWORDS_BY_SCOPE.items():
        results_by_scope[scope] = {}
        for label, query in entries:
            try:
                articles = fetch_news_for_keyword(query, window_start, window_end, seen_keys)
                total_articles += len(articles)
                results_by_scope[scope][label] = analyze_and_sort_articles(articles)
            except Exception as e:
                results_by_scope[scope][label] = []
                print(f"Error fetching news for '{label}': {e}")
            time.sleep(3)  # small pause between searches to avoid Google News rate limiting

    print(f"Total articles found in the news window: {total_articles}")

    print("Generating executive summary...")
    executive_summary = generate_executive_summary(results_by_scope)

    html_page = build_html_page(results_by_scope, executive_summary, window_start, shown_end)
    with open(OUTPUT_HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_page)
    print(f"Website page written to {OUTPUT_HTML_FILE}")


if __name__ == "__main__":
    main()
