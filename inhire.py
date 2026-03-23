from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
import urllib.parse
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


APP_DIR = Path(__file__).resolve().parent
RUNS_DIR = APP_DIR / ".streamlit_runs"
APP_TITLE = "🕵️ Schenkel JobSearch Inhire"
BASE_URL_TEMPLATE = "https://{}.inhire.app/vagas"
WAIT_FOR_JOBS_TIMEOUT = 15000
DEFAULT_TIMEOUT_MS = 15000
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)
JOB_LINK_PATTERN = re.compile(r"/vagas/[a-z0-9-]+", re.IGNORECASE)
TITLE_KEYS = ("title", "name", "jobTitle", "job_title", "position")
URL_KEYS = ("url", "href", "link", "jobUrl", "job_url", "absoluteUrl")
PATH_KEYS = ("path", "slug", "uri", "permalink")
DEFAULT_KEYWORDS = [
    "analista de dados",
    "data analyst",
    "analista de negocios",
    "business analyst",
    "dataviz",
]
DEFAULT_COMPANIES = [
"olist",
"openlabs",
"orizon",
"paytrack",
"premiersoft",
"radix",
"shareprime",
"sylvamo",
"sympla",
"talentx",
"tripla",
"unimar",
"v360",
"v4company",
"vitru",
"warren",
"zig",
"contabilizei",
"kiwify",
"bancotoyota",
"adelcoco",
"solutis",
"programmers",
"gruposabe",
"dbservices",
"grupojra",
"proselect",
"elsys",
"frete",
"sidia",
"gpcorpbr",
"talentetech",
"contaazul",
"oliveiraeantunes",
"svninvestimentos"
]

LogCallback = Callable[[str], None]


@dataclass
class ScraperConfig:
    headless: bool = True
    wait_for_jobs_timeout: int = WAIT_FOR_JOBS_TIMEOUT
    network_idle_timeout: int = 5000
    save_debug_html: bool = False
    output_dir: Path = Path(".")
    debug_dir: Path = Path("debug_html")
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))


def emit_log(logger: LogCallback | None, message: str) -> None:
    print(message)
    if logger:
        logger(message)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_only).strip().lower()


def parse_multiline_input(raw_value: str) -> list[str]:
    normalized = raw_value.replace(",", "\n").replace(";", "\n")
    items = [line.strip() for line in normalized.splitlines() if line.strip()]
    deduplicated: list[str] = []
    seen: set[str] = set()

    for item in items:
        lowered = item.lower()
        if lowered not in seen:
            deduplicated.append(lowered)
            seen.add(lowered)

    return deduplicated


def matches_keywords(text: str, keywords: list[str]) -> bool:
    normalized_text = normalize_text(text)
    return any(normalize_text(keyword) in normalized_text for keyword in keywords)


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_") or "debug"


def ensure_directories(config: ScraperConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    if config.save_debug_html:
        config.debug_dir.mkdir(parents=True, exist_ok=True)


def create_context(playwright, config: ScraperConfig):
    browser = playwright.chromium.launch(
        headless=config.headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-infobars",
        ],
    )

    context = browser.new_context(
        locale="pt-BR",
        user_agent=DEFAULT_USER_AGENT,
        viewport={"width": 1440, "height": 900},
    )
    context.route(
        "**/*",
        lambda route, request: route.abort()
        if request.resource_type in {"image", "font", "media"}
        else route.continue_(),
    )

    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = window.chrome || { runtime: {} };
        Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        """
    )
    return browser, context


def save_debug_html(config: ScraperConfig, filename: str, html: str) -> None:
    if not config.save_debug_html:
        return

    config.debug_dir.mkdir(parents=True, exist_ok=True)
    (config.debug_dir / filename).write_text(html, encoding="utf-8")


def warm_up_listing(page) -> None:
    page.wait_for_timeout(600)
    for _ in range(2):
        page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.9))")
        page.wait_for_timeout(400)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(250)


def wait_for_listing(page, config: ScraperConfig) -> None:
    selectors = [
        "a[href*='/vagas/']",
        "[class*='job']",
        "[class*='vaga']",
        "[class*='card']",
        "main",
    ]
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=config.wait_for_jobs_timeout)
            return
        except PlaywrightTimeout:
            continue


def parse_json_candidate(value: str) -> Any | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def first_non_empty_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def build_candidate_url(raw_url: str | None, raw_path: str | None, listing_url: str) -> str | None:
    if raw_url:
        candidate = urllib.parse.urljoin(listing_url, raw_url)
        if "/vagas/" in candidate:
            return candidate

    if not raw_path:
        return None

    raw_path = raw_path.strip()
    if not raw_path:
        return None

    if "/vagas/" in raw_path:
        return urllib.parse.urljoin(listing_url, raw_path)

    if re.fullmatch(r"[a-z0-9-]{8,}", raw_path, flags=re.IGNORECASE):
        return urllib.parse.urljoin(listing_url, f"/vagas/{raw_path}")

    return None


def normalize_job_title(title: str) -> str:
    return re.sub(r"\s+", " ", title or "").strip()


def extract_links_from_payload(payload: Any, listing_url: str, keywords: list[str]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            title = first_non_empty_str(node, TITLE_KEYS)
            raw_url = first_non_empty_str(node, URL_KEYS)
            raw_path = first_non_empty_str(node, PATH_KEYS)
            candidate_url = build_candidate_url(raw_url, raw_path, listing_url)
            if title and candidate_url and matches_keywords(title, keywords):
                found.append(
                    {
                        "nome_vaga": normalize_job_title(title),
                        "link": candidate_url,
                        "origem_extracao": "json",
                    }
                )
            for value in node.values():
                walk(value)
            return

        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def extract_links_from_embedded_json(html: str, listing_url: str, keywords: list[str]) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict[str, str]] = []
    script_candidates: list[str] = []

    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data:
        script_candidates.append(next_data.get_text(strip=True))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        script_candidates.append(script.get_text(strip=True))

    for raw_json in script_candidates:
        payload = parse_json_candidate(raw_json)
        if payload is not None:
            found.extend(extract_links_from_payload(payload, listing_url, keywords))

    return found


def extract_links_from_dom(page, listing_url: str, keywords: list[str]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    selectors = ["a[href*='/vagas/']", "[href*='/vagas/']"]

    for selector in selectors:
        try:
            candidates = page.locator(selector).evaluate_all(
                """
                elements => elements.map(element => ({
                    href: element.href || element.getAttribute('href') || '',
                    text: (element.innerText || element.textContent || '').trim()
                }))
                """
            )
        except Exception:
            continue

        for item in candidates:
            href = (item.get("href") or "").strip()
            text = normalize_job_title(item.get("text") or "")
            if not href or not text:
                continue

            full_url = urllib.parse.urljoin(listing_url, href)
            if "/vagas/" not in full_url:
                continue

            if matches_keywords(text, keywords):
                found.append(
                    {
                        "nome_vaga": text,
                        "link": full_url,
                        "origem_extracao": "dom",
                    }
                )

    return found


def extract_links_from_html(html: str, listing_url: str, keywords: list[str]) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict[str, str]] = []

    for link in soup.find_all("a", href=JOB_LINK_PATTERN):
        href = (link.get("href") or "").strip()
        text = normalize_job_title(link.get_text(separator=" ", strip=True))
        if not href or not text:
            continue

        full_url = urllib.parse.urljoin(listing_url, href)
        if matches_keywords(text, keywords):
            found.append(
                {
                    "nome_vaga": text,
                    "link": full_url,
                    "origem_extracao": "html",
                }
            )

    return found


def deduplicate_jobs(items: list[dict[str, str]], company: str, listing_url: str) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in items:
        link = item["link"]
        if link in seen:
            continue

        unique.append(
            {
                "empresa": company.upper(),
                "nome_vaga": item["nome_vaga"],
                "link": link,
                "origem_extracao": item["origem_extracao"],
                "pagina_listagem": listing_url,
                "data_coleta": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        seen.add(link)

    return unique


def register_json_capture(page, payloads: list[Any]) -> None:
    def handle_response(response) -> None:
        try:
            if response.request.resource_type not in {"xhr", "fetch"}:
                return

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower():
                return

            payloads.append(response.json())
        except Exception:
            return

    page.on("response", handle_response)


def fetch_company_jobs(
    context,
    company: str,
    config: ScraperConfig,
    logger: LogCallback | None = None,
) -> list[dict[str, str]]:
    url = BASE_URL_TEMPLATE.format(company)
    emit_log(logger, f"  Acessando: {url}")
    page = context.new_page()
    try:
        network_payloads: list[Any] = []
        register_json_capture(page, network_payloads)
        page.goto(url, timeout=60000, wait_until="domcontentloaded")

        try:
            page.wait_for_load_state("networkidle", timeout=config.network_idle_timeout)
        except PlaywrightTimeout:
            pass

        warm_up_listing(page)
        wait_for_listing(page, config)
        page.wait_for_timeout(700)

        html = page.content()
        save_debug_html(config, f"{safe_filename(company)}_listing.html", html)

        combined_jobs: list[dict[str, str]] = []
        for payload in network_payloads:
            combined_jobs.extend(extract_links_from_payload(payload, url, config.keywords))
        combined_jobs.extend(extract_links_from_dom(page, url, config.keywords))
        combined_jobs.extend(extract_links_from_html(html, url, config.keywords))
        combined_jobs.extend(extract_links_from_embedded_json(html, url, config.keywords))

        jobs = deduplicate_jobs(combined_jobs, company, url)
        emit_log(logger, f"  Vagas candidatas encontradas: {len(jobs)}")

        if not jobs:
            page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            emit_log(logger, f"  Nenhuma vaga com as keywords foi localizada em {company}.")
            emit_log(logger, f"  Trecho da pagina: {page_text[:300]}")

        return jobs
    finally:
        page.close()


def run_scraper(
    companies: list[str],
    config: ScraperConfig,
    logger: LogCallback | None = None,
) -> pd.DataFrame:
    ensure_directories(config)
    all_jobs: list[dict[str, str]] = []

    emit_log(logger, "Iniciando busca de vagas InHire")
    emit_log(logger, "=" * 80)
    emit_log(logger, f"Empresas: {len(companies)}")
    emit_log(logger, f"Keywords: {', '.join(config.keywords)}")
    emit_log(logger, f"Modo headless: {'sim' if config.headless else 'nao'}")
    emit_log(logger, "=" * 80)

    with sync_playwright() as playwright:
        browser, context = create_context(playwright, config)
        try:
            total = len(companies)
            for index, company in enumerate(companies, start=1):
                emit_log(logger, f"\n[{index}/{total}] Empresa: {company.upper()}")
                emit_log(logger, "-" * 80)
                try:
                    jobs = fetch_company_jobs(context, company, config, logger=logger)
                    if jobs:
                        emit_log(logger, f"  {len(jobs)} vagas encontradas.")
                        all_jobs.extend(jobs)
                    else:
                        emit_log(logger, "  Nenhuma vaga encontrada.")
                except Exception as exc:
                    emit_log(logger, f"  Erro na empresa {company}: {exc}")
        finally:
            browser.close()

    df = pd.DataFrame(all_jobs)
    if df.empty:
        return df

    return df.drop_duplicates(subset=["link"]).reset_index(drop=True)


def save_results(df: pd.DataFrame, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"vagas_{timestamp}.csv"
    excel_path = output_dir / f"vagas_{timestamp}.xlsx"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(excel_path, index=False, engine="openpyxl")
    return csv_path, excel_path


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli-run", action="store_true")
    parser.add_argument("--company", action="append")
    parser.add_argument("--keyword", action="append")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=WAIT_FOR_JOBS_TIMEOUT)
    parser.add_argument("--save-debug-html", action="store_true")
    parser.add_argument("--output-dir", default=".")
    return parser.parse_args()


def cli_main() -> int:
    args = parse_cli_args()
    companies = args.company or list(DEFAULT_COMPANIES)
    keywords = list(DEFAULT_KEYWORDS)
    if args.keyword:
        keywords.extend(keyword.strip() for keyword in args.keyword if keyword.strip())

    config = ScraperConfig(
        headless=not args.headed,
        wait_for_jobs_timeout=args.timeout_ms,
        save_debug_html=args.save_debug_html,
        output_dir=Path(args.output_dir),
        debug_dir=Path(args.output_dir) / "debug_html",
        keywords=keywords,
    )

    df = run_scraper(companies, config)
    print("\n" + "=" * 80)
    print(f"Resultado final: {len(df)} vagas")
    print("=" * 80)

    if df.empty:
        print("Nenhuma vaga encontrada.")
        return 0

    print(df[["empresa", "nome_vaga", "link"]].to_string(index=False))
    csv_path, excel_path = save_results(df, config.output_dir)
    print("\nArquivos gerados:")
    print(f"- {csv_path}")
    print(f"- {excel_path}")
    if config.save_debug_html:
        print(f"- {config.debug_dir} (debug)")
    return 0


def get_default_companies_text() -> str:
    return "\n".join(DEFAULT_COMPANIES)


def get_default_keywords_text() -> str:
    return "\n".join(DEFAULT_KEYWORDS)


def build_download_frame(df: pd.DataFrame) -> pd.DataFrame:
    ordered_columns = ["empresa", "nome_vaga", "link"]
    available_columns = [column for column in ordered_columns if column in df.columns]
    return df[available_columns].copy()


def build_command(
    companies: list[str],
    keywords: list[str],
    timeout_ms: int,
    headless: bool,
    save_debug_html: bool,
    output_dir: Path,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--cli-run",
        "--output-dir",
        str(output_dir),
        "--timeout-ms",
        str(timeout_ms),
    ]

    if not headless:
        command.append("--headed")
    if save_debug_html:
        command.append("--save-debug-html")

    for company in companies:
        command.extend(["--company", company])
    for keyword in keywords:
        command.extend(["--keyword", keyword])

    return command


def run_cli_search(
    companies: list[str],
    keywords: list[str],
    timeout_ms: int,
    headless: bool,
    save_debug_html: bool,
) -> tuple[pd.DataFrame, Path, int, str]:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = RUNS_DIR / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        build_command(companies, keywords, timeout_ms, headless, save_debug_html, run_dir),
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    csv_files = sorted(run_dir.glob("vagas_*.csv"))
    if csv_files:
        df = pd.read_csv(csv_files[-1])
    else:
        df = pd.DataFrame(columns=["empresa", "nome_vaga", "link"])

    combined_output = "\n".join(
        chunk.strip() for chunk in [result.stdout, result.stderr] if chunk and chunk.strip()
    )
    return df, run_dir, result.returncode, combined_output


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(210, 231, 255, 0.9), transparent 28%),
                radial-gradient(circle at top right, rgba(255, 237, 212, 0.95), transparent 24%),
                linear-gradient(180deg, #f7f4ec 0%, #f3efe5 100%);
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1180px;
        }
        .hero-card {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(34, 55, 90, 0.08);
            border-radius: 24px;
            padding: 1.6rem 1.8rem;
            box-shadow: 0 18px 45px rgba(43, 55, 72, 0.08);
            backdrop-filter: blur(8px);
            margin-bottom: 1rem;
        }
        .hero-title {
            font-size: 2rem;
            font-weight: 700;
            color: #1d3557;
            letter-spacing: -0.02em;
            margin-bottom: 0.25rem;
        }
        .hero-subtitle {
            color: #4d5b72;
            font-size: 1rem;
            line-height: 1.5;
            margin-bottom: 0;
        }
        .summary-card {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(29, 53, 87, 0.08);
            border-radius: 20px;
            padding: 1rem 1.1rem;
            box-shadow: 0 14px 30px rgba(43, 55, 72, 0.06);
        }
        .summary-label {
            color: #6d7a8e;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.35rem;
        }
        .summary-value {
            color: #18314f;
            font-size: 1.55rem;
            font-weight: 700;
            line-height: 1.1;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def summary_card(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="summary-card">
            <div class="summary-label">{label}</div>
            <div class="summary-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_app() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    apply_theme()

    if "results_df" not in st.session_state:
        st.session_state.results_df = None
    if "run_dir" not in st.session_state:
        st.session_state.run_dir = ""
    if "return_code" not in st.session_state:
        st.session_state.return_code = 0
    if "run_output" not in st.session_state:
        st.session_state.run_output = ""

    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-title">{APP_TITLE}</div>
            <p class="hero-subtitle">
                Busca vagas diretamente nas listagens do InHire e entrega uma planilha simples com empresa,
                nome da vaga e link para candidatura.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    default_companies = get_default_companies_text()
    default_keywords = get_default_keywords_text()

    with st.sidebar:
        st.header("Preferencias")
        headless = st.toggle("Rodar headless", value=True)
        save_debug_html = st.toggle("Salvar HTML da listagem", value=False)
        timeout_ms = st.number_input(
            "Timeout da listagem (ms)",
            min_value=5000,
            max_value=120000,
            value=DEFAULT_TIMEOUT_MS,
            step=1000,
        )
        st.caption("Os campos ja carregam as empresas e termos padrao da busca.")

    with st.form("search_form"):
        left_col, right_col = st.columns([1.2, 1])

        with left_col:
            companies_raw = st.text_area(
                "Empresas",
                value=default_companies,
                height=340,
                help="Uma empresa por linha. Tambem aceita virgulas ou ponto e virgula.",
            )

        with right_col:
            keywords_raw = st.text_area(
                "Termos de busca",
                value=default_keywords,
                height=340,
                help="Um termo por linha. Tambem aceita virgulas ou ponto e virgula.",
            )

        submitted = st.form_submit_button("Buscar vagas", type="primary", use_container_width=True)

    status_placeholder = st.empty()

    if submitted:
        companies = parse_multiline_input(companies_raw)
        keywords = parse_multiline_input(keywords_raw)

        st.session_state.results_df = None
        st.session_state.run_dir = ""
        st.session_state.return_code = 0
        st.session_state.run_output = ""

        if not companies:
            st.error("Informe pelo menos uma empresa.")
            st.stop()

        if not keywords:
            st.error("Informe pelo menos um termo de busca.")
            st.stop()

        with status_placeholder.container():
            st.info("Buscando vagas nas empresas selecionadas...")

        try:
            with st.spinner("Executando busca, isso pode levar alguns instantes..."):
                df, run_dir, return_code, run_output = run_cli_search(
                    companies=companies,
                    keywords=keywords,
                    timeout_ms=int(timeout_ms),
                    headless=headless,
                    save_debug_html=save_debug_html,
                )
            st.session_state.results_df = df
            st.session_state.run_dir = str(run_dir)
            st.session_state.return_code = return_code
            st.session_state.run_output = run_output
        except Exception as exc:
            status_placeholder.error(f"Erro ao executar busca: {exc}")

    results_df = st.session_state.results_df

    if results_df is not None:
        if st.session_state.return_code != 0:
            status_placeholder.error("Nao foi possivel concluir a busca.")
        elif results_df.empty:
            status_placeholder.warning("Nenhuma vaga encontrada com os filtros atuais.")
        else:
            display_df = build_download_frame(results_df)
            status_placeholder.success(f"{len(display_df)} vagas encontradas.")

            companies_count = display_df["empresa"].nunique() if "empresa" in display_df.columns else 0
            jobs_count = len(display_df)

            metrics_col1, metrics_col2 = st.columns(2)
            with metrics_col1:
                summary_card("Empresas com resultado", str(companies_count))
            with metrics_col2:
                summary_card("Vagas encontradas", str(jobs_count))

            actions_col1, actions_col2 = st.columns([1, 1])
            csv_bytes = display_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            with actions_col1:
                st.download_button(
                    "Baixar CSV",
                    data=csv_bytes,
                    file_name="schenkel_jobsearch_inhire.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                display_df.to_excel(writer, index=False)

            with actions_col2:
                st.download_button(
                    "Baixar Excel",
                    data=excel_buffer.getvalue(),
                    file_name="schenkel_jobsearch_inhire.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            st.dataframe(
                display_df,
                use_container_width=True,
                column_config={"link": st.column_config.LinkColumn("Link da vaga")},
                hide_index=True,
            )

            if save_debug_html and st.session_state.run_dir:
                debug_dir = Path(st.session_state.run_dir) / "debug_html"
                st.caption(f"HTML de debug salvo em `{debug_dir}`.")


if __name__ == "__main__" and "--cli-run" in sys.argv:
    raise SystemExit(cli_main())


render_app()
