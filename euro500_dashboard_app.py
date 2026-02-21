from __future__ import annotations
from pathlib import Path
import pandas as pd
from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_widget
import plotly.express as px


# =============================================================================
# Data configuration & loading
# =============================================================================
# Expected input:
# Quarterly Euro500 constituents panel with at least:
# - date (datetime): quarter-end formation date
# - firm_id (preferred stable identifier), or other company ID columns
#
# Optional (used if available):
# name, hq_country, hq_code, sector, trbc_sector, trbc_sector_code, mcap_eur, rank_mcap
# =============================================================================

DATA_FILE = Path("euro500_dashboard_table.parquet")


def load_euro500_data() -> pd.DataFrame:
    # --- debug: show what Python sees ---
    print("Working directory:", Path.cwd())
    print("Looking for data at:", DATA_FILE)
    print("Exists?", DATA_FILE.exists())

    if not DATA_FILE.exists():
        # show helpful directory listing
        parent = DATA_FILE.parent
        msg = [f"Euro500 dashboard table parquet not found at:\n{DATA_FILE}\n"]
        if parent.exists():
            msg.append(f"Files in {parent}:\n" + "\n".join(sorted(p.name for p in parent.iterdir())[:200]))
        else:
            msg.append(f"Directory does not exist: {parent}")
        raise FileNotFoundError("\n".join(msg))

    df = pd.read_parquet(DATA_FILE)

    if "date" not in df.columns:
        raise ValueError("Dataset must contain a 'date' column.")

    df = df.copy()
    # Avoid duplicate derived columns if they already exist in source
    df = df.drop(columns=["q_year", "q_num", "q_label"], errors="ignore")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].copy()
    df["year"] = df["date"].dt.year.astype(int)
    # Quarter labeling rule:
    # - 31-12-1998 -> Q1 1999
    # - 31-03-1999 -> Q2 1999
    # - 30-06-1999 -> Q3 1999
    # - 30-09-1999 -> Q4 1999
    month = df["date"].dt.month
    qnum_map = {12: 1, 3: 2, 6: 3, 9: 4}
    df["q_num"] = month.map(qnum_map)
    # Fallback for non-standard months: use calendar quarter
    df["q_num"] = df["q_num"].fillna(((month - 1) // 3 + 1).astype(int))
    df["q_year"] = df["date"].dt.year + (month == 12).astype(int)
    df["q_label"] = df["q_year"].astype(int).astype(str) + "Q" + df["q_num"].astype(int).astype(str)

    preferred = [
        "date", "year", "firm_id", "name",
        "hq_country", "hq_code",
        "sector", "trbc_sector", "trbc_sector_code",
        "mcap_eur", "rank_mcap",
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    extra = ["q_year", "q_num", "q_label"]
    all_cols = list(dict.fromkeys(cols + extra))
    return df[all_cols]


# IMPORTANT: call the right loader
DF = load_euro500_data()
YEARS = sorted(DF["q_year"].unique().tolist()) if "q_year" in DF.columns else sorted(DF["year"].unique().tolist())

from shiny import ui

# -----------------------------
# UI (dashboard-style)
# -----------------------------
app_ui = ui.page_fluid(
    ui.tags.head(ui.tags.title("EURO500 Dashboard")),
    ui.tags.script(
        """
        (function () {
          const LABEL = "Market Cap (EUR mio.)";
          const TIP = "Reporting Price: Close (day before quarter start)";
          const formatNumber = new Intl.NumberFormat("en-US", {
            maximumFractionDigits: 0,
          });
          function applyTip() {
            const root = document.getElementById("tbl") || document;
            const nodes = root.querySelectorAll(
              "th, [role='columnheader'], .reactable-column-header, .rt-th"
            );
            let hit = false;
            for (const n of nodes) {
              const text = (n.textContent || "").trim();
              if (text === LABEL) {
                n.title = TIP;
                hit = true;
              }
            }
            return hit;
          }
          function formatMcap() {
            try {
              const root = document.getElementById("tbl") || document;
              const thead = root.querySelector("thead");
              const headerRow = thead ? thead.querySelector("tr") : null;
              if (!headerRow || !headerRow.children) return false;
              const headers = Array.from(headerRow.children);
              const colIdx = headers.findIndex(
                (h) => (h.textContent || "").trim() === LABEL
              );
              if (colIdx < 0) return false;
              const rows = root.querySelectorAll("tbody tr");
              rows.forEach((row) => {
                const cell = row.children[colIdx];
                if (!cell) return;
                const raw = (cell.textContent || "").trim();
                if (!raw || raw.startsWith("€")) return;
                let cleaned = raw.replace(/[^\\d.,-]/g, "");
                if (!cleaned) return;
                cleaned = cleaned.replace(/,/g, "");
                const dots = (cleaned.match(/\\./g) || []).length;
                if (dots > 1) cleaned = cleaned.replace(/\\./g, "");
                const numeric = parseFloat(cleaned);
                if (Number.isFinite(numeric)) {
                  const formatted = `€ ${formatNumber.format(Math.round(numeric))} mio.`;
                  if (cell.textContent !== formatted) cell.textContent = formatted;
                }
              });
              return true;
            } catch (e) {
              return false;
            }
          }
          function observe() {
            const root = document.getElementById("tbl") || document.body;
            if (!root) return;
            const obs = new MutationObserver(() => {
              applyTip();
              formatMcap();
            });
            obs.observe(root, { childList: true, subtree: true, characterData: true });
            let tries = 0;
            const timer = setInterval(() => {
              tries += 1;
              applyTip();
              formatMcap();
              if (tries > 20) clearInterval(timer);
            }, 200);
          }
          if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", observe);
          } else {
            observe();
          }
        })();
        """
    ),
    # Small bit of CSS to make it feel more like a dashboard template
    ui.tags.style(
        """
        :root {
          --ink: #1f2937;
          --muted: #6b7280;
          --accent: #0ea5a4;
          --accent-soft: #e6f7f6;
          --card-bg: #ffffff;
          --stroke: #e5e7eb;
        }
        body { color: var(--ink); background: #f8fafc; }
        .app-title { margin-top: 0.9rem; margin-bottom: 0.35rem; letter-spacing: 0.2px; }
        .title-link { color: inherit; text-decoration: none; }
        .title-link:hover { text-decoration: none; }
        .muted { color: var(--muted); }
        .card-title { margin-bottom: 0.25rem; }
        .vb-number { font-size: 1.7rem; font-weight: 700; line-height: 1.2; }
        .vb-label { font-size: 0.9rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
        .vb-row { margin-bottom: 0.15rem; }
        /* Make KPI cards in vb-row equal-height by stretching columns */
        .vb-row { align-items: stretch; }
        .vb-row > div[class^="col"], .vb-row > div[class*=" col"] { display: flex; }
        .vb-row > div[class^="col"] > .card, .vb-row > div[class*=" col"] > .card { width: 100%; }
        .table-card { margin-top: -0.25rem; }
        .main-stack { display: flex; flex-direction: column; gap: 0.4rem; }
        .plot-card { margin-top: 0.25rem; }
        .plot-card .card-body { padding: 0.5rem 0.75rem; }
        .html-widget { width: 100% !important; display: block; }
        .plotly-graph-div { width: 100% !important; height: 100% !important; }
        .card { background: var(--card-bg); border: 1px solid var(--stroke); box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04); }
        /* Ensure selectize dropdowns aren't clipped by cards/containers */
        .card, .card-body, .main-stack, .sidebar { overflow: visible !important; }
        .selectize-control { position: relative; }
        .selectize-dropdown { z-index: 3000 !important; }
        .selectize-dropdown-content { max-height: 420px; }
        shiny-data-frame#tbl .shiny-data-grid > table {
          table-layout: fixed;
        }
        shiny-data-frame#tbl .shiny-data-grid > table > thead > tr > th:last-child,
        shiny-data-frame#tbl .shiny-data-grid > table > tbody > tr > td:last-child {
          width: 50px !important;
          min-width: 50px !important;
          max-width: 50px !important;
          white-space: nowrap;
        }
        shiny-data-frame#tbl .shiny-data-grid > table > thead > tr > th:first-child,
        shiny-data-frame#tbl .shiny-data-grid > table > tbody > tr > td:first-child {
          width: 280px !important;
          min-width: 280px !important;
          max-width: 280px !important;
        }
        shiny-data-frame#tbl .shiny-data-grid > table > thead > tr > th:first-child {
          white-space: nowrap;
        }
        shiny-data-frame#tbl .shiny-data-grid > table > tbody > tr > td:first-child {
          white-space: normal !important;
          overflow-wrap: anywhere;
          word-break: break-word;
          line-height: 1.25;
        }
        shiny-data-frame#tbl .shiny-data-grid > table > thead > tr > th:nth-child(2),
        shiny-data-frame#tbl .shiny-data-grid > table > tbody > tr > td:nth-child(2) {
          width: 130px !important;
          min-width: 130px !important;
          max-width: 130px !important;
          white-space: nowrap;
        }
        .card-header { background: var(--accent-soft); border-bottom: 1px solid var(--stroke); font-weight: 600; }
        .sidebar { background: #f3f6fb; border-right: 1px solid var(--stroke); }
        .btn-primary { background: var(--accent); border-color: var(--accent); }
        .tight-label { margin: 0; }
        .tight-value { display: block; margin: 0 0 0.2rem 0; }
        """
    ),

    ui.h2(
        ui.input_action_link("go_home", "Euro500 Equity Universe Explorer", class_="title-link"),
        class_="app-title fw-bold",
    ),
    ui.p(
        "A snapshot of the Euro500 equity universe: The 500 largest euro-area headquartered, non-financial public primary equities (ordinary/common/registered/voting shares and preference shares), ranked by point-in-time market capitalization at each quarterly formation date.",
        class_="muted",
    ),
    ui.layout_sidebar(
        ui.sidebar(
            ui.h5("Filter by Quarter", class_="fw-bold"),

            ui.input_select(
                "year",
                "Year",
                choices=[str(y) for y in YEARS],
                selected=str(YEARS[-1]) if YEARS else None,
            ),

            ui.input_selectize(
                "quarter",
                "Quarter (optional)",
                choices=[],              # filled by server (update_selectize)
                multiple=False,
                options={"placeholder": "All quarters in selected year"},
            ),
            ui.output_ui("back_to_main_btn"),
            ui.hr(),
            ui.input_action_button("toggle_view", "Explore Time Variation"),
            ui.hr(),
            ui.input_action_button("toggle_company", "Explore by Company"),
            ui.hr(),
            ui.p("Created by:", class_="muted tight-label"),
            ui.tags.span("Jakob Sarrazin", class_="tight-value", title="jakob.sarrazin@students.uni-mannheim.de"),
            width=320,
        ),

        ui.output_ui("main_panel"),
    ),
)

from shiny import reactive, render, ui
import pandas as pd

# -----------------------------
# Server
# -----------------------------
from shiny import reactive, render, ui
import pandas as pd


def server(input, output, session):
    show_time = reactive.value(False)
    page = reactive.value("main")  # "main" | "company"

    def _first_existing_col(d: pd.DataFrame, candidates: list[str]) -> str | None:
        for c in candidates:
            if c in d.columns:
                return c
        return None

    def _company_id_col(d: pd.DataFrame) -> str | None:
        return _first_existing_col(d, ["firm_id", "FirmID", "FIRM_ID", "ISIN", "isin"])

    def _sector_col(d: pd.DataFrame) -> str | None:
        return _first_existing_col(d, ["sector", "trbc_sector", "trbc_sector_code"])

    def _latest_quarter_label(d: pd.DataFrame) -> str:
        if d is None or d.empty:
            return ""
        dd = d.copy()
        dd["date"] = pd.to_datetime(dd["date"], errors="coerce")
        dd = dd.loc[dd["date"].notna()].copy()
        if dd.empty:
            return ""
        latest_date = dd["date"].max()
        latest_rows = dd.loc[dd["date"] == latest_date].copy()
        if "q_label" in latest_rows.columns and latest_rows["q_label"].notna().any():
            return str(latest_rows["q_label"].dropna().astype(str).iloc[0])
        return str(latest_date.to_period("Q"))

    @reactive.effect
    @reactive.event(input.toggle_view)
    def _toggle_view():
        show_time.set(not show_time.get())

    @reactive.effect
    @reactive.event(input.go_home)
    def _go_home():
        page.set("main")
        show_time.set(False)

    @reactive.effect
    @reactive.event(input.go_home_sidebar)
    def _go_home_sidebar():
        page.set("main")
        show_time.set(False)

    @reactive.effect
    @reactive.event(input.toggle_company)
    def _toggle_company():
        # Toggle between main dashboard and company page
        page.set("main" if page.get() == "company" else "company")

    # ---- Quarter choices based on selected year ----
    @reactive.effect
    def _update_quarters():
        y = input.year()
        if y is None or str(y).strip() == "":
            ui.update_selectize("quarter", choices=[], selected="")
            return

        y = int(y)
        year_col = "q_year" if "q_year" in DF.columns else "year"
        d = DF.loc[DF[year_col] == y, ["date", "q_label"]].copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna()

        if "q_label" in d.columns:
            qlabels = d["q_label"].sort_values().unique().tolist()
        else:
            qlabels = (
                d["date"]
                .dt.to_period("Q")
                .astype(str)
                .sort_values()
                .unique()
                .tolist()
            )
        default_q = _latest_quarter_label(d)
        if default_q and default_q not in qlabels:
            default_q = qlabels[-1] if qlabels else ""
        ui.update_selectize("quarter", choices=qlabels, selected=default_q)

    # ---- Main filtered data ----
    @reactive.calc
    def filtered() -> pd.DataFrame:
        # Always return a DataFrame (never crash UI)
        try:
            if DF is None or DF.empty or "year" not in DF.columns:
                return pd.DataFrame()

            year_col = "q_year" if "q_year" in DF.columns else "year"
            y = input.year()
            if y is None or str(y).strip() == "":
                y_int = int(DF[year_col].max())
            else:
                y_int = int(y)

            d = DF.loc[DF[year_col] == y_int].copy()

            q = input.quarter()
            if q is not None and str(q).strip() != "":
                if "q_label" in d.columns:
                    d = d.loc[d["q_label"].astype(str) == str(q)].copy()
                else:
                    dq = pd.to_datetime(d["date"], errors="coerce").dt.to_period("Q").astype(str)
                    d = d.loc[dq == str(q)].copy()
            else:
                # If no quarter selected, default to the latest available quarter
                default_q = _latest_quarter_label(d)
                if default_q:
                    if "q_label" in d.columns:
                        d = d.loc[d["q_label"].astype(str) == str(default_q)].copy()
                    else:
                        dq = pd.to_datetime(d["date"], errors="coerce").dt.to_period("Q").astype(str)
                        d = d.loc[dq == str(default_q)].copy()

            # Sort
            sort_cols = []
            asc = []

            if "date" in d.columns:
                sort_cols.append("date"); asc.append(False)
            if "rank_mcap" in d.columns:
                d["rank_mcap"] = pd.to_numeric(d["rank_mcap"], errors="coerce")
                sort_cols.append("rank_mcap"); asc.append(True)
            elif "mcap_eur" in d.columns:
                sort_cols.append("mcap_eur"); asc.append(False)
            id_col = _company_id_col(d)
            if id_col:
                sort_cols.append(id_col); asc.append(True)

            if sort_cols:
                d = d.sort_values(sort_cols, ascending=asc, kind="mergesort")

            return d

        except Exception:
            return pd.DataFrame()

    # ---- Debug text (shows you what's going on) ----
    @render.text
    def debug():
        try:
            y = input.year()
            q = input.quarter()
            d = filtered()
            return (
                f"year input: {y}\n"
                f"quarter input: {q}\n"
                f"DF rows: {len(DF):,}\n"
                f"filtered rows: {len(d):,}\n"
                f"filtered cols: {list(d.columns)[:12]}"
            )
        except Exception as e:
            return f"debug error: {repr(e)}"

    @render.ui
    def back_to_main_btn():
        if page.get() == "company" or show_time.get():
            return ui.input_action_button("go_home_sidebar", "Back to Main Page", class_="btn-primary w-100")
        return None

    # ---- Value boxes (never blank) ----
    @render.ui
    def vb_rows():
        d = filtered()
        if "mcap_eur" in d.columns:
            total = d["mcap_eur"].sum(skipna=True)
            total_b = total / 1e9
            value = f"€ {total_b:,.0f} bn"
            label = "index market cap"
        else:
            value = "€ 0"
            label = "index market cap"
        return ui.div(
            ui.div(value, class_="vb-number"),
            ui.div(label, class_="vb-label"),
        )

    @render.ui
    def vb_firms():
        d = filtered()
        id_col = _company_id_col(d)
        n = int(d[id_col].nunique()) if id_col else 0
        return ui.div(
            ui.div(f"{n:,}".replace(",", "."), class_="vb-number"),
            ui.div("unique companies", class_="vb-label"),
        )

    @render.ui
    def vb_countries():
        d = filtered()
        col = "hq_code" if "hq_code" in d.columns else ("hq_country" if "hq_country" in d.columns else None)
        n = int(d[col].nunique()) if col else 0
        return ui.div(
            ui.div(f"{n:,}".replace(",", "."), class_="vb-number"),
            ui.div("HQ countries", class_="vb-label"),
        )

    @render.ui
    def vb_sectors():
        d = filtered()
        col = _sector_col(d)
        n = int(d[col].nunique()) if col else 0
        return ui.div(
            ui.div(f"{n:,}".replace(",", "."), class_="vb-number"),
            ui.div("Economic sectors", class_="vb-label"),
        )

    @render.ui
    def vb_company_years():
        d = _company_df()
        if d.empty:
            years = 0.0
        else:
            if "q_label" in d.columns:
                qn = int(d["q_label"].dropna().astype(str).nunique())
            elif "date" in d.columns:
                q = pd.to_datetime(d["date"], errors="coerce").dt.to_period("Q").astype(str)
                qn = int(q.dropna().nunique())
            else:
                qn = 0
            years = qn / 4.0

        if years.is_integer():
            value = str(int(years))
        else:
            value = f"{years:.2f}".rstrip("0").rstrip(".")
        return ui.div(
            ui.div(value, class_="vb-number"),
            ui.div("quarters / 4", class_="vb-label"),
        )

    @render.ui
    def vb_company_best_rank():
        d = _company_df()
        if d.empty or "rank_mcap" not in d.columns:
            value = "–"
        else:
            r = pd.to_numeric(d["rank_mcap"], errors="coerce")
            r = r.where(r >= 1)  # ignore 0 / invalid encodings
            if r.dropna().empty:
                value = "–"
            else:
                value = str(int(r.min()))
        return ui.div(
            ui.div(value, class_="vb-number"),
            ui.div("best (min) rank", class_="vb-label"),
        )

    def _most_common_str(d: pd.DataFrame, col: str) -> str:
        if col not in d.columns:
            return ""
        s = d[col].dropna().astype(str)
        s = s[s.str.strip() != ""]
        if s.empty:
            return ""
        return str(s.value_counts().idxmax())

    @render.ui
    def vb_company_hq_country():
        d = _company_df()
        if d.empty:
            value = "–"
        else:
            col = "hq_country" if "hq_country" in d.columns else ("hq_code" if "hq_code" in d.columns else "")
            v = _most_common_str(d, col) if col else ""
            value = v if v else "–"
        return ui.div(
            ui.div(value, class_="vb-number"),
            ui.div("", class_="vb-label"),
        )

    @render.ui
    def vb_company_sector():
        d = _company_df()
        if d.empty:
            value = "–"
        else:
            col = _sector_col(d) or ""
            v = _most_common_str(d, col) if col else ""
            value = v if v else "–"
        return ui.div(
            ui.div(value, class_="vb-number"),
            ui.div("", class_="vb-label"),
        )

    # ---- Table ----
    @render.data_frame
    def tbl():
        d = filtered()
        d = d.drop(
            columns=["date", "year", "q_year", "q_num", "q_label", "hq_code", "trbc_sector_code", "firm_id", "FirmID", "FIRM_ID", "ISIN", "isin"],
            errors="ignore",
        )
        if "mcap_eur" in d.columns:
            d["mcap_eur"] = pd.to_numeric(d["mcap_eur"], errors="coerce") / 1e6
        if "rank_mcap" in d.columns:
            d["rank_mcap"] = d["rank_mcap"].map(
                lambda x: str(int(x)) if pd.notna(x) else ""
            )
        rename_map = {
            "name": "Company",
            "hq_country": "HQ Country",
            "sector": "Economic Sector",
            "trbc_sector": "Economic Sector",
            "mcap_eur": "Market Cap (EUR mio.)",
            "rank_mcap": "Rank",
        }
        sector_col = _first_existing_col(d, ["sector", "trbc_sector"])
        preferred_order = ["name", "hq_country"] + ([sector_col] if sector_col else []) + ["mcap_eur", "rank_mcap"]
        ordered_cols = [c for c in preferred_order if c in d.columns]
        if ordered_cols:
            d = d[ordered_cols]
        d = d.rename(columns={k: v for k, v in rename_map.items() if k in d.columns})
        return render.DataGrid(
            d,
            row_selection_mode="multiple",
            filters=True,
            height="720px",
        )

    # ---- Time variation helpers ----
    def _time_series_labels(d: pd.DataFrame) -> tuple[str, list[str]]:
        if {"q_year", "q_num", "q_label"}.issubset(d.columns):
            order = (
                d[["q_year", "q_num", "q_label"]]
                .drop_duplicates()
                .sort_values(["q_year", "q_num"])
            )
            return "q_label", order["q_label"].astype(str).tolist()
        if "date" in d.columns:
            q = pd.to_datetime(d["date"], errors="coerce").dt.to_period("Q").astype(str)
            d["q_label_tmp"] = q
            labels = q.dropna().sort_values().unique().tolist()
            return "q_label_tmp", labels
        return "", []

    def _safe_input(name: str, default=""):
        # Inputs on the company page are created dynamically. Guard access here to
        # avoid server-side errors during initial render / page switches.
        try:
            fn = getattr(input, name)
        except Exception:
            return default
        try:
            return fn()
        except Exception:
            return default

    def _series_clean_str(d: pd.DataFrame, col: str) -> pd.Series:
        if col not in d.columns:
            return pd.Series([""] * len(d), index=d.index, dtype="object")
        return d[col].fillna("").astype(str).str.strip()

    def _with_company_key(d: pd.DataFrame) -> pd.DataFrame:
        if d is None or d.empty:
            dd = d.copy() if isinstance(d, pd.DataFrame) else pd.DataFrame()
            dd["_company_key"] = ""
            return dd

        dd = d.copy()
        fid_col = _first_existing_col(dd, ["firm_id", "FirmID", "FIRM_ID"])
        isin_col = _first_existing_col(dd, ["ISIN", "isin"])

        fid = _series_clean_str(dd, fid_col) if fid_col else pd.Series([""] * len(dd), index=dd.index, dtype="object")
        isin = _series_clean_str(dd, isin_col) if isin_col else pd.Series([""] * len(dd), index=dd.index, dtype="object")
        name = _series_clean_str(dd, "name")
        hq = _series_clean_str(dd, "hq_code")

        # Prefer firm_id as stable entity key; fall back to ISIN, then name(+hq).
        key = fid.copy()
        key = key.where(key != "", isin)
        name_fallback = name.where(hq == "", name + " | " + hq)
        key = key.where(key != "", name_fallback)
        dd["_company_key"] = key
        return dd

    @reactive.calc
    def _company_df() -> pd.DataFrame:
        company_key = str(_safe_input("company_choice", "")).strip()
        if company_key == "":
            return pd.DataFrame()
        d = _with_company_key(DF)
        if "_company_key" not in d.columns:
            return pd.DataFrame()
        return d.loc[d["_company_key"].astype(str) == company_key].copy()

    @reactive.calc
    def _companies_master() -> pd.DataFrame:
        d = _with_company_key(DF)
        if d.empty or "_company_key" not in d.columns:
            return pd.DataFrame()

        d["_company_key"] = d["_company_key"].astype(str).str.strip()
        d = d.loc[d["_company_key"] != ""].copy()
        if d.empty:
            return pd.DataFrame()

        if "date" in d.columns:
            d["_sort_date"] = pd.to_datetime(d["date"], errors="coerce")
            d = d.sort_values("_sort_date", kind="mergesort")
        else:
            d["_sort_date"] = pd.NaT

        if "name" in d.columns:
            d["_display_name"] = _series_clean_str(d, "name")
        else:
            d["_display_name"] = ""

        d["_display_name"] = d["_display_name"].where(d["_display_name"] != "", d["_company_key"])

        fid_col = _first_existing_col(d, ["firm_id", "FirmID", "FIRM_ID"])
        isin_col = _first_existing_col(d, ["ISIN", "isin"])
        d["_firm_id"] = _series_clean_str(d, fid_col) if fid_col else ""
        d["_isin"] = _series_clean_str(d, isin_col) if isin_col else ""

        master = d.groupby("_company_key", as_index=False).tail(1).copy()
        master["_search_blob"] = (
            master["_company_key"].astype(str).str.upper()
            + " "
            + master["_display_name"].astype(str).str.upper()
            + " "
            + master["_firm_id"].astype(str).str.upper()
            + " "
            + master["_isin"].astype(str).str.upper()
        )
        return master[["_company_key", "_display_name", "_firm_id", "_isin", "_search_blob"]]

    @reactive.effect
    def _update_company_choices():
        if page.get() != "company":
            return

        q = str(_safe_input("company_search", "")).strip()
        if q == "":
            ui.update_selectize("company_choice", choices=[], selected=[])
            return

        master = _companies_master()
        if master.empty:
            ui.update_selectize("company_choice", choices=[], selected=[])
            return

        q_upper = q.upper()
        blob = master["_search_blob"].fillna("").astype(str)

        # Ranking: exact key/firm_id/isin > startswith > contains in any searchable field.
        contains_any = blob.str.contains(q_upper, na=False, regex=False)

        matches = master.loc[contains_any].copy()
        if matches.empty:
            ui.update_selectize("company_choice", choices=[], selected=[])
            return

        m_fid = matches["_firm_id"].astype(str)
        m_key = matches["_company_key"].astype(str)
        m_nm = matches["_display_name"].astype(str)
        m_isin = matches["_isin"].astype(str)

        m_exact = (
            m_key.str.upper().eq(q_upper)
            | m_fid.str.upper().eq(q_upper)
            | m_isin.str.upper().eq(q_upper)
        )
        m_starts = (
            m_key.str.upper().str.startswith(q_upper)
            | m_fid.str.upper().str.startswith(q_upper)
            | m_isin.str.upper().str.startswith(q_upper)
        )
        matches["_rank"] = (
            m_exact.map({True: 0, False: 1}).astype(int) * 100
            + m_starts.map({True: 0, False: 1}).astype(int) * 10
        )
        matches["_name_sort"] = m_nm.str.upper()

        matches = matches.sort_values(["_rank", "_name_sort", "_company_key"], kind="mergesort").head(50)

        # Show company names only in the UI; keep stable company key as internal value.
        labels = matches["_display_name"].astype(str).tolist()
        values = matches["_company_key"].astype(str).tolist()
        # For selectize, dict keys are the *values* sent to server; dict values are labels shown to user.
        choices = dict(zip(values, labels))

        selected = _safe_input("company_choice", "")
        if selected not in set(values):
            # If the query is an exact ID match, auto-select it; else leave empty.
            if q_upper in set(v.upper() for v in values):
                # pick the first exact match (case-insensitive)
                for v in values:
                    if v.upper() == q_upper:
                        selected = v
                        break
            else:
                selected = ""

        ui.update_selectize("company_choice", choices=choices, selected=selected)

    # ---- Main panel switch ----
    @render.ui
    def main_panel():
        if page.get() == "company":
            return ui.div(
                ui.card(
                    ui.card_header("Explore by Company"),
                    ui.row(
                        ui.column(
                            7,
                            ui.input_text(
                                "company_search",
                                "Search",
                                value="",
                                width="100%",
                                placeholder="Type a company name",
                            ),
                        ),
                        ui.column(
                            5,
                            ui.input_selectize(
                                "company_choice",
                                "Company",
                                choices={},
                                selected="",
                                multiple=False,
                                width="100%",
                                options={"placeholder": "Matches will appear here"},
                            ),
                        ),
                    ),
                ),
                ui.row(
                    ui.column(
                        3,
                        ui.card(
                            ui.h6("Years in Index", class_="card-title"),
                            ui.output_ui("vb_company_years"),
                            full_screen=False,
                        ),
                    ),
                    ui.column(
                        3,
                        ui.card(
                            ui.h6("Best Rank Ever", class_="card-title"),
                            ui.output_ui("vb_company_best_rank"),
                            full_screen=False,
                        ),
                    ),
                    ui.column(
                        3,
                        ui.card(
                            ui.h6("HQ Country", class_="card-title"),
                            ui.output_ui("vb_company_hq_country"),
                            full_screen=False,
                        ),
                    ),
                    ui.column(
                        3,
                        ui.card(
                            ui.h6("Sector", class_="card-title"),
                            ui.output_ui("vb_company_sector"),
                            full_screen=False,
                        ),
                    ),
                    class_="vb-row",
                ),
                ui.card(
                    ui.card_header("Market Cap by Quarter (0 if not in index)"),
                    output_widget("plot_company_mcap", width="100%", height="360px"),
                    class_="plot-card company-mcap-card",
                    full_screen=False,
                ),
                ui.card(
                    ui.card_header("Rank in Index Over Time"),
                    output_widget("plot_company_rank", width="100%", height="360px"),
                    class_="plot-card",
                    full_screen=False,
                ),
                class_="main-stack",
            )

        if not show_time.get():
            return ui.div(
                ui.row(
                    ui.column(
                        3,
                        ui.card(
                        ui.h6("Index Market Cap", class_="card-title"),
                            ui.output_ui("vb_rows"),
                            full_screen=False,
                        ),
                    ),
                    ui.column(
                        3,
                        ui.card(
                        ui.h6("Companies", class_="card-title"),
                            ui.output_ui("vb_firms"),
                        ),
                    ),
                    ui.column(
                        3,
                        ui.card(
                        ui.h6("Headquarters Countries", class_="card-title"),
                            ui.output_ui("vb_countries"),
                        ),
                    ),
                    ui.column(
                        3,
                        ui.card(
                        ui.h6("Industry Sectors", class_="card-title"),
                            ui.output_ui("vb_sectors"),
                        ),
                    ),
                    class_="vb-row",
                ),
                ui.card(
                    ui.card_header("Constituent Firms"),
                    ui.output_data_frame("tbl"),
                    full_screen=True,
                    class_="table-card",
                ),
                class_="main-stack",
            )

        return ui.div(
            ui.row(
                ui.column(
                    6,
            ui.card(
                ui.card_header("Headquarters Mix Over Time"),
                output_widget("plot_hq_time", width="100%", height="360px"),
                class_="plot-card",
                full_screen=False,
            ),
                ),
                ui.column(
                    6,
            ui.card(
                ui.card_header("Index Market Cap Over Time"),
                output_widget("plot_mcap_time", width="100%", height="360px"),
                class_="plot-card",
                full_screen=False,
            ),
                ),
            ),
            ui.row(
                ui.column(
                    6,
            ui.card(
                ui.card_header("Top 5 Sectors — Share of Index"),
                output_widget("plot_top5_sectors", width="100%", height="360px"),
                class_="plot-card",
                full_screen=False,
            ),
                ),
                ui.column(
                    6,
            ui.card(
                ui.card_header("Top 5 HQ Countries (% of Index)"),
                output_widget("plot_top5_countries", width="100%", height="360px"),
                class_="plot-card",
                full_screen=False,
            ),
                ),
            ),
            class_="main-stack",
        )

    def _five_year_ticks(labels: list[str]) -> tuple[list[str], list[str]]:
        years = []
        for lbl in labels:
            try:
                years.append(int(str(lbl)[:4]))
            except Exception:
                years.append(None)
        tickvals = []
        ticktext = []
        for i, y in enumerate(years):
            if y is None:
                continue
            if y % 5 == 0 and (i == 0 or years[i - 1] != y):
                tickvals.append(labels[i])
                ticktext.append(str(y))
        return tickvals, ticktext

    @render_widget
    def plot_hq_time():
        d = DF.copy()
        label_col, labels = _time_series_labels(d)
        if "hq_country" not in d.columns or not labels or not label_col:
            fig = px.line()
            fig.add_annotation(text="No HQ data available", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig
        series = d.groupby(label_col)["hq_country"].nunique()
        series = series.reindex(labels)
        tickvals, ticktext = _five_year_ticks(labels)
        fig = px.line(x=labels, y=series.values, markers=False)
        fig.update_layout(
            xaxis_title="Year",
            yaxis_title="Unique HQ countries",
            margin=dict(l=60, r=20, t=20, b=60),
            hovermode="x unified",
            plot_bgcolor="white",
            paper_bgcolor="white",
            autosize=True,
        )
        fig.update_traces(line=dict(color="#0ea5a4", width=3))
        fig.update_xaxes(showgrid=False, automargin=True)
        fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb", automargin=True)
        if tickvals:
            fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        fig.update_layout(
            dragmode=False,
            modebar_remove=[
                "zoom2d","pan2d","zoomIn2d","zoomOut2d","autoScale2d","resetScale2d",
                "zoom3d","pan3d","orbitRotation","tableRotation",
                "resetViewMapbox","zoomInGeo","zoomOutGeo","resetGeo",
                "select2d","lasso2d","toImage","toggleSpikelines"
            ],
        )
        return fig

    @render_widget
    def plot_mcap_time():
        d = DF.copy()
        label_col, labels = _time_series_labels(d)
        if "mcap_eur" not in d.columns or not labels or not label_col:
            fig = px.line()
            fig.add_annotation(text="No market cap data available", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig
        series = d.groupby(label_col)["mcap_eur"].sum()
        series = series.reindex(labels) / 1e9
        tickvals, ticktext = _five_year_ticks(labels)
        fig = px.line(x=labels, y=series.values, markers=False)
        fig.update_layout(
            xaxis_title="Year",
            yaxis_title="€ bn",
            margin=dict(l=60, r=20, t=20, b=60),
            hovermode="x unified",
            plot_bgcolor="white",
            paper_bgcolor="white",
            autosize=True,
        )
        fig.update_traces(line=dict(color="#1d4ed8", width=3))
        fig.update_xaxes(showgrid=False, automargin=True)
        fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb", automargin=True)
        if tickvals:
            fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        fig.update_layout(
            dragmode=False,
            modebar_remove=[
                "zoom2d","pan2d","zoomIn2d","zoomOut2d","autoScale2d","resetScale2d",
                "zoom3d","pan3d","orbitRotation","tableRotation",
                "resetViewMapbox","zoomInGeo","zoomOutGeo","resetGeo",
                "select2d","lasso2d","toImage","toggleSpikelines"
            ],
        )
        return fig

    @render_widget
    def plot_top5_sectors():
        d = DF.copy()
        label_col, labels = _time_series_labels(d)
        sector_col = _sector_col(d)
        if (
            "mcap_eur" not in d.columns
            or not sector_col
            or d.empty
            or not label_col
            or not labels
        ):
            fig = px.bar()
            fig.add_annotation(text="No sector data available", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig
        total_by_sector = d.groupby(sector_col)["mcap_eur"].sum().sort_values(ascending=False)
        top5 = total_by_sector.head(5).index.tolist()
        by_q_sector = (
            d.groupby([label_col, sector_col])["mcap_eur"]
            .sum()
            .reset_index()
        )
        total_by_q = d.groupby(label_col)["mcap_eur"].sum().reset_index()
        by_q_sector = by_q_sector.merge(total_by_q, on=label_col, suffixes=("", "_total"))
        by_q_sector["share"] = (by_q_sector["mcap_eur"] / by_q_sector["mcap_eur_total"]) * 100
        by_q_sector = by_q_sector[by_q_sector[sector_col].isin(top5)]
        by_q_sector[label_col] = by_q_sector[label_col].astype(str)
        fig = px.line(
            by_q_sector,
            x=label_col,
            y="share",
            color=sector_col,
        )
        fig.update_layout(
            xaxis_title="Year",
            yaxis_title="Share of index (%)",
            margin=dict(l=60, r=20, t=10, b=60),
            plot_bgcolor="white",
            paper_bgcolor="white",
            hovermode="x unified",
            legend_title_text="",
            legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0, font=dict(size=12)),
            legend_font_size=12,
            autosize=True,
        )
        tickvals, ticktext = _five_year_ticks(labels)
        if tickvals:
            fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb")
        fig.update_traces(
            hovertemplate="Year: %{x}<br>Sector: %{fullData.name}<br>Index Share: %{y:.1f}%<extra></extra>"
        )
        fig.update_layout(
            dragmode=False,
            modebar_remove=[
                "zoom2d","pan2d","zoomIn2d","zoomOut2d","autoScale2d","resetScale2d",
                "zoom3d","pan3d","orbitRotation","tableRotation",
                "resetViewMapbox","zoomInGeo","zoomOutGeo","resetGeo",
                "select2d","lasso2d","toImage","toggleSpikelines"
            ],
        )
        return fig

    @render_widget
    def plot_top5_countries():
        d = DF.copy()
        label_col, labels = _time_series_labels(d)
        if (
            "mcap_eur" not in d.columns
            or "hq_country" not in d.columns
            or d.empty
            or not label_col
            or not labels
        ):
            fig = px.bar()
            fig.add_annotation(text="No HQ data available", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig
        total_by_country = d.groupby("hq_country")["mcap_eur"].sum().sort_values(ascending=False)
        top5 = total_by_country.head(5).index.tolist()
        by_q_country = (
            d.groupby([label_col, "hq_country"])["mcap_eur"]
            .sum()
            .reset_index()
        )
        total_by_q = d.groupby(label_col)["mcap_eur"].sum().reset_index()
        by_q_country = by_q_country.merge(total_by_q, on=label_col, suffixes=("", "_total"))
        by_q_country["share"] = (by_q_country["mcap_eur"] / by_q_country["mcap_eur_total"]) * 100
        by_q_country = by_q_country[by_q_country["hq_country"].isin(top5)]
        by_q_country[label_col] = by_q_country[label_col].astype(str)
        fig = px.line(
            by_q_country,
            x=label_col,
            y="share",
            color="hq_country",
        )
        fig.update_layout(
            xaxis_title="Year",
            yaxis_title="Share of index (%)",
            margin=dict(l=60, r=20, t=10, b=45),
            plot_bgcolor="white",
            paper_bgcolor="white",
            hovermode="x unified",
            legend_title_text="",
            legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0, font=dict(size=12)),
            legend_font_size=12,
            autosize=True,
        )
        tickvals, ticktext = _five_year_ticks(labels)
        if tickvals:
            fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb")
        fig.update_traces(
            hovertemplate="Year: %{x}<br>Country: %{fullData.name}<br>Index Share: %{y:.1f}%<extra></extra>"
        )
        fig.update_layout(
            dragmode=False,
            modebar_remove=[
                "zoom2d","pan2d","zoomIn2d","zoomOut2d","autoScale2d","resetScale2d",
                "zoom3d","pan3d","orbitRotation","tableRotation",
                "resetViewMapbox","zoomInGeo","zoomOutGeo","resetGeo",
                "select2d","lasso2d","toImage","toggleSpikelines"
            ],
        )
        return fig

    @render_widget
    def plot_company_mcap():
        if page.get() != "company":
            return px.bar()

        company_key = str(_safe_input("company_choice", "")).strip()
        if company_key == "":
            fig = px.bar()
            fig.add_annotation(text="Search and select a company to see the chart.", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig

        d_all = DF.copy()
        label_col, labels = _time_series_labels(d_all)
        if not labels or not label_col:
            fig = px.bar()
            fig.add_annotation(text="No quarter information available in dataset.", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig

        d = _company_df().copy()
        if d.empty:
            fig = px.bar()
            fig.add_annotation(text="No data found for selected company.", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig

        if "mcap_eur" not in d.columns:
            fig = px.bar()
            fig.add_annotation(text="Dataset has no 'mcap_eur' column.", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig

        # Ensure company df has the same label column as the global label list.
        if label_col not in d.columns:
            if label_col == "q_label_tmp" and "date" in d.columns:
                q = pd.to_datetime(d["date"], errors="coerce").dt.to_period("Q").astype(str)
                d["q_label_tmp"] = q
            else:
                fig = px.bar()
                fig.add_annotation(text="Quarter labeling not available for this dataset.", x=0.5, y=0.5, showarrow=False)
                fig.update_xaxes(visible=False)
                fig.update_yaxes(visible=False)
                return fig

        # One bar per quarter. If duplicates exist within a quarter, use max mcap.
        series = d.groupby(label_col)["mcap_eur"].max()
        series = series.reindex(labels).fillna(0.0) / 1e9

        name = ""
        if "name" in d.columns:
            try:
                name = str(d["name"].dropna().iloc[0])
            except Exception:
                name = ""

        x = [str(lbl) for lbl in labels]
        y = series.values.tolist()
        title = name if name else ""

        fig = px.bar(x=x, y=y)
        fig.update_layout(
            title=title,
            xaxis_title="Quarter",
            yaxis_title="Market cap (EUR bn)",
            margin=dict(l=60, r=20, t=50, b=45),
            plot_bgcolor="white",
            paper_bgcolor="white",
            autosize=True,
        )
        fig.update_traces(marker_color="#0ea5a4", hovertemplate="Quarter: %{x}<br>Market cap: %{y:.1f} bn<extra></extra>")
        fig.update_xaxes(showgrid=False, type="category", automargin=True)
        fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb", automargin=True)
        tickvals, ticktext = _five_year_ticks(labels)
        if tickvals:
            fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        fig.update_layout(
            dragmode=False,
            modebar_remove=[
                "zoom2d","pan2d","zoomIn2d","zoomOut2d","autoScale2d","resetScale2d",
                "zoom3d","pan3d","orbitRotation","tableRotation",
                "resetViewMapbox","zoomInGeo","zoomOutGeo","resetGeo",
                "select2d","lasso2d","toImage","toggleSpikelines"
            ],
        )
        return fig

    @render_widget
    def plot_company_rank():
        if page.get() != "company":
            return px.line()

        company_key = str(_safe_input("company_choice", "")).strip()
        if company_key == "":
            fig = px.line()
            fig.add_annotation(text="Search and select a company to see the chart.", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig

        if "rank_mcap" not in DF.columns:
            fig = px.line()
            fig.add_annotation(text="Dataset has no 'rank_mcap' column.", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig

        d_all = DF.copy()
        label_col, labels = _time_series_labels(d_all)
        if not labels or not label_col:
            fig = px.line()
            fig.add_annotation(text="No quarter information available in dataset.", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig

        d = _company_df().copy()
        if d.empty:
            fig = px.line()
            fig.add_annotation(text="No data found for selected company.", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig

        if label_col not in d.columns:
            if label_col == "q_label_tmp" and "date" in d.columns:
                q = pd.to_datetime(d["date"], errors="coerce").dt.to_period("Q").astype(str)
                d["q_label_tmp"] = q
            else:
                fig = px.line()
                fig.add_annotation(text="Quarter labeling not available for this dataset.", x=0.5, y=0.5, showarrow=False)
                fig.update_xaxes(visible=False)
                fig.update_yaxes(visible=False)
                return fig

        # One rank per quarter; use best (minimum) rank if multiple rows exist.
        series = pd.to_numeric(d["rank_mcap"], errors="coerce")
        # Guard against datasets that encode "not ranked / not in index" as 0.
        series = series.where(series >= 1)
        d["_rank_num"] = series
        s = d.groupby(label_col)["_rank_num"].min()
        s = s.reindex(labels)  # keep NaN for quarters not in index

        name = ""
        if "name" in d.columns:
            try:
                name = str(d["name"].dropna().iloc[0])
            except Exception:
                name = ""

        x = [str(lbl) for lbl in labels]
        y = s.values.tolist()
        title = name if name else ""

        fig = px.line(x=x, y=y, markers=False)
        fig.update_layout(
            title=title,
            xaxis_title="Quarter",
            yaxis_title="Rank (1 = largest)",
            margin=dict(l=60, r=20, t=50, b=45),
            hovermode="x unified",
            plot_bgcolor="white",
            paper_bgcolor="white",
            autosize=True,
        )
        fig.update_traces(line=dict(color="#111827", width=3), hovertemplate="Quarter: %{x}<br>Rank: %{y:.0f}<extra></extra>")
        fig.update_xaxes(showgrid=False, type="category", automargin=True)
        ymax = None
        try:
            vmax = float(pd.Series(y).dropna().max())
            if vmax >= 1:
                ymax = vmax
        except Exception:
            ymax = None
        if ymax is not None:
            fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb", autorange=False, range=[ymax, 1], automargin=True)
        else:
            fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb", autorange="reversed", automargin=True)
        tickvals, ticktext = _five_year_ticks(labels)
        if tickvals:
            fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        fig.update_layout(
            dragmode=False,
            modebar_remove=[
                "zoom2d","pan2d","zoomIn2d","zoomOut2d","autoScale2d","resetScale2d",
                "zoom3d","pan3d","orbitRotation","tableRotation",
                "resetViewMapbox","zoomInGeo","zoomOutGeo","resetGeo",
                "select2d","lasso2d","toImage","toggleSpikelines"
            ],
        )
        return fig

app = App(app_ui, server)
