# EURO500 Dashboard

This repository contains the codebase to my dashboard **EURO500 equity universe**, defined as the **500 largest non-financial firms by market capitalization headquartered in euro-area countries**.

The project was developed as part of a Master’s thesis in Economics and combines a transparent data construction pipeline with an interactive dashboard built using **Shiny for Python**.

Web Page to the Dashboard:
https://jakobsar.shinyapps.io/euro500/

---

## Project Overview

- An **interactive dashboard** that:
  - Allows exploration of EURO500 constituents by year (and quarter)
  - Displays firm-level characteristics and summary statistics
  - Supports filtering, searching, and sorting

---

## Data Definition

The **EURO500** universe is defined as:

- The **top 500 firms by market capitalization**
- **Headquartered in euro-area countries** (country membership varies over time)
- **Non-financial firms** (TRBC sector “Financials” excluded)
- Instruments without a valid TRBC sector (e.g. ETFs, funds) are excluded

The universe is rebalanced **quarterly**.

---

## Setup

### 1. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Dashboard
To run the code you need the data file Project_Data/intermediate/euro500.parquet
```bash
shiny run euro500_dashboard_app.py
```

The dashboard will be available at
http://localhost:8000












