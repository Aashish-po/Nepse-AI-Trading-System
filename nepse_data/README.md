# 📈 NEPSE Daily Data Scraper (ShareSansar + Merolagani)

A Python scraper that extracts daily **NEPSE** share data from:

- **ShareSansar** (today-share-price page, Selenium)
- **Merolagani** (Floorsheet, HTML form + ViewState)

It saves cleaned CSV files for NEPSE analysis.

---

## ✨ What it produces

CSV output is stored under:

- `nepse_data/data/sharesansar/YYYY-MM-DD.csv`
- `nepse_data/data/merolagani/YYYY-MM-DD.csv`

Each file includes a `date` column plus scraped rows for that trading day.

> **Trading days:** NEPSE trades **Mon–Fri**. The scraper will skip weekends automatically.

---

## 🚀 Quickstart

### Prerequisites

- Python **3.12+**
- Google Chrome (required for ShareSansar scraping)
- ChromeDriver is installed automatically by `chromedriver-autoinstaller`

### Install

From the repository root:

```bash
pip install -r nepse_data/requirements.txt
```

---

## 🧰 Usage

Run from the repository root:

```bash
python nepse_data/scraper.py [OPTIONS]
```

### Supported CLI options

| Option | Description | Default |
|---|---|---|
| `--source {all,sharesansar,merolagani}` | Select one source or both | `all` |
| `--start YYYY-MM-DD` | Start date (inclusive) | `today - 14 days` |
| `--end YYYY-MM-DD` | End date (inclusive) | `today` |
| `--today` | Scrape today only (overrides date range) | false |
| `--force` | Re-download even if CSV already exists | false |

### Common commands

Scrape last 14 trading days from both sources:

```bash
python nepse_data/scraper.py
```

Scrape today only (all sources):

```bash
python nepse_data/scraper.py --today
```

Scrape only ShareSansar for a custom range:

```bash
python nepse_data/scraper.py --source sharesansar --start 2025-06-01 --end 2025-06-20
```

Scrape only Merolagani for today:

```bash
python nepse_data/scraper.py --source merolagani --today
```

Force re-download for a range (single source):

```bash
python nepse_data/scraper.py --source sharesansar --start 2025-06-01 --end 2025-06-20 --force
```

Help:

```bash
python nepse_data/scraper.py --help
```

---

## 🧾 Output example

```text
nepse_data/data/
├── sharesansar/
│   └── 2025-06-16.csv
└── merolagani/
    └── 2025-06-16.csv
```

---

## 🛡️ Resilience & behavior

- If a day returns no data (e.g., no matching floor-sheet rows), the scraper logs a warning and continues.
- Existing CSVs are skipped unless `--force` is used.
- Built-in delays are used to reduce rate-limit / bot-detection issues.

---

## 🧰 Technology stack

| Category | Tools / Libraries |
|---|---|
| Language | Python 3.12+ |
| HTTP | `requests` |
| Browser automation | `selenium`, `chromedriver-autoinstaller` (ShareSansar) |
| Parsing | `beautifulsoup4`, `lxml` |
| Data | `pandas` |
| CLI | `argparse` (built-in) |

Dependencies are in `nepse_data/requirements.txt`.

---

## 🧪 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| ShareSansar returns no data | Page layout / selector changes | Update the ShareSansar scraping logic in `SharesansarScraper._scrape()` |
| 403 / rate limit | Too many requests | Use smaller date ranges; run during off-peak hours |
| Empty output for a date | No trading/holiday or no matching rows | Try a different trading day; verify you selected the correct `--start/--end` |
| `ModuleNotFoundError` | Missing dependencies | Reinstall: `pip install -r nepse_data/requirements.txt` |

---

## 🤝 Contributing

1. Create a branch: `git checkout -b feature/your-change`
2. Make changes (keep formatting consistent)
3. Test CLI locally: `python nepse_data/scraper.py --help`
4. Open a PR with a clear description of the change

---

## 📜 License

MIT (see repo `LICENSE`).
