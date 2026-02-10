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
# - RIC
#
# Optional (used if available):
# name, hq_country, hq_code, trbc_sector, trbc_sector_code, mcap_eur, rank_mcap
# =============================================================================

DATA_FILE = Path("euro500.parquet")


def load_euro500_data() -> pd.DataFrame:
    # --- debug: show what Python sees ---
    print("Working directory:", Path.cwd())
    print("Looking for data at:", DATA_FILE)
    print("Exists?", DATA_FILE.exists())

    if not DATA_FILE.exists():
        # show helpful directory listing
        parent = DATA_FILE.parent
        msg = [f"Euro500 parquet not found at:\n{DATA_FILE}\n"]
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
        "date", "year", "RIC", "name",
        "hq_country", "hq_code",
        "trbc_sector", "trbc_sector_code",
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
          const LABEL = "Market Cap (EUR)";
          const TIP = "Reporting Price: Close (day before quarter start)";
          const formatNumber = new Intl.NumberFormat("de-DE", {
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
                const cleaned = raw.replace(/[^0-9-]/g, "");
                if (!cleaned) return;
                const numeric = Number(cleaned);
                if (Number.isFinite(numeric)) {
                  const formatted = `€ ${formatNumber.format(numeric)}`;
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
        .muted { color: var(--muted); }
        .card-title { margin-bottom: 0.25rem; }
        .vb-number { font-size: 1.7rem; font-weight: 700; line-height: 1.2; }
        .vb-label { font-size: 0.9rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
        .vb-row { margin-bottom: 0.15rem; }
        .table-card { margin-top: -0.25rem; }
        .main-stack { display: flex; flex-direction: column; gap: 0.4rem; }
        .plot-card { margin-top: 0.25rem; }
        .plot-card .card-body { padding: 0.5rem 0.75rem; }
        .html-widget { width: 100% !important; display: block; }
        .plotly-graph-div { width: 100% !important; height: 100% !important; }
        .card { background: var(--card-bg); border: 1px solid var(--stroke); box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04); }
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
          width: 100px !important;
          min-width: 100px !important;
          max-width: 100px !important;
          white-space: nowrap;
        }
        .card-header { background: var(--accent-soft); border-bottom: 1px solid var(--stroke); font-weight: 600; }
        .sidebar { background: #f3f6fb; border-right: 1px solid var(--stroke); }
        .btn-primary { background: var(--accent); border-color: var(--accent); }
        .tight-label { margin: 0; }
        .tight-value { display: block; margin: 0 0 0.2rem 0; }
        """
    ),

    ui.h2("Euro500 Equity Universe Explorer", class_="app-title fw-bold"),
    ui.p(
        "A snapshot of the Euro500 equity universe: the 500 largest non‑financial companies by market cap headquartered in the euro area.",
        class_="muted",
    ),
    ui.layout_sidebar(
        ui.sidebar(
            ui.h5("Filter by Quarter", class_="fw-bold"),

            ui.input_select(
                "year",
                "Year",
                choices=[str(y) for y in YEARS],
                selected="2026" if 2026 in YEARS else (str(YEARS[0]) if YEARS else None),
            ),

            ui.input_selectize(
                "quarter",
                "Quarter (optional)",
                choices=[],              # filled by server (update_selectize)
                multiple=False,
                options={"placeholder": "All quarters in selected year"},
            ),
            ui.hr(),
            ui.input_action_button("toggle_view", "Explore Time Variation"),
            ui.hr(),
            ui.p("Data Source:", class_="muted tight-label"),
            ui.span("LSEG Datastream", class_="tight-value"),
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

    @reactive.effect
    @reactive.event(input.toggle_view)
    def _toggle_view():
        show_time.set(not show_time.get())

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
        # Default to Q1 2026 if available, otherwise first quarter in the list
        if "2026Q1" in qlabels:
            default_q = "2026Q1"
        else:
            default_q = qlabels[0] if qlabels else ""
        ui.update_selectize("quarter", choices=qlabels, selected=default_q)

    # ---- Main filtered data ----
    @reactive.calc
    def filtered() -> pd.DataFrame:
        # Always return a DataFrame (never crash UI)
        try:
            if DF is None or DF.empty or "year" not in DF.columns:
                return pd.DataFrame()

            y = input.year()
            if y is None or str(y).strip() == "":
                y_int = int(DF["year"].min())
            else:
                y_int = int(y)

            year_col = "q_year" if "q_year" in DF.columns else "year"
            d = DF.loc[DF[year_col] == y_int].copy()

            q = input.quarter()
            if q is not None and str(q).strip() != "":
                if "q_label" in d.columns:
                    d = d.loc[d["q_label"].astype(str) == str(q)].copy()
                else:
                    dq = pd.to_datetime(d["date"], errors="coerce").dt.to_period("Q").astype(str)
                    d = d.loc[dq == str(q)].copy()
            else:
                # If no quarter selected, default to Q1 2026 if present, otherwise first quarter
                if "q_label" in d.columns and not d.empty:
                    qlabels = d["q_label"].sort_values().astype(str).tolist()
                    if "2026Q1" in qlabels:
                        default_q = "2026Q1"
                    else:
                        default_q = qlabels[0]
                    d = d.loc[d["q_label"].astype(str) == str(default_q)].copy()

            # Sort
            sort_cols = []
            asc = []

            if "date" in d.columns:
                sort_cols.append("date"); asc.append(False)
            if "mcap_eur" in d.columns:
                sort_cols.append("mcap_eur"); asc.append(False)
            if "RIC" in d.columns:
                sort_cols.append("RIC"); asc.append(True)

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
        n = int(d["RIC"].nunique()) if ("RIC" in d.columns) else 0
        return ui.div(
            ui.div(f"{n:,}".replace(",", "."), class_="vb-number"),
            ui.div("unique RICs", class_="vb-label"),
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
        col = "trbc_sector" if "trbc_sector" in d.columns else None
        n = int(d[col].nunique()) if col else 0
        return ui.div(
            ui.div(f"{n:,}".replace(",", "."), class_="vb-number"),
            ui.div("TRBC sectors", class_="vb-label"),
        )

    # ---- Table ----
    @render.data_frame
    def tbl():
        d = filtered()
        d = d.drop(
            columns=["date", "year", "q_year", "q_num", "q_label", "hq_code", "trbc_sector_code"],
            errors="ignore",
        )
        if "rank_mcap" in d.columns:
            d["rank_mcap"] = d["rank_mcap"].map(
                lambda x: str(int(x)) if pd.notna(x) else ""
            )
        rename_map = {
            "RIC": "RIC",
            "name": "Company",
            "hq_country": "HQ Country",
            "trbc_sector": "TRBC Sector",
            "mcap_eur": "Market Cap (EUR)",
            "rank_mcap": "Rank",
        }
        preferred_order = ["RIC", "name", "hq_country", "trbc_sector", "mcap_eur", "rank_mcap"]
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

    # ---- Main panel switch ----
    @render.ui
    def main_panel():
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
                        ui.h6("Unique Companies", class_="card-title"),
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
        if (
            "mcap_eur" not in d.columns
            or "trbc_sector" not in d.columns
            or d.empty
            or not label_col
            or not labels
        ):
            fig = px.bar()
            fig.add_annotation(text="No sector data available", x=0.5, y=0.5, showarrow=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig
        total_by_sector = d.groupby("trbc_sector")["mcap_eur"].sum().sort_values(ascending=False)
        top5 = total_by_sector.head(5).index.tolist()
        by_q_sector = (
            d.groupby([label_col, "trbc_sector"])["mcap_eur"]
            .sum()
            .reset_index()
        )
        total_by_q = d.groupby(label_col)["mcap_eur"].sum().reset_index()
        by_q_sector = by_q_sector.merge(total_by_q, on=label_col, suffixes=("", "_total"))
        by_q_sector["share"] = (by_q_sector["mcap_eur"] / by_q_sector["mcap_eur_total"]) * 100
        by_q_sector = by_q_sector[by_q_sector["trbc_sector"].isin(top5)]
        by_q_sector[label_col] = by_q_sector[label_col].astype(str)
        fig = px.line(
            by_q_sector,
            x=label_col,
            y="share",
            color="trbc_sector",
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

app = App(app_ui, server)
