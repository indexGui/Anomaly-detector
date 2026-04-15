# 🔍 Anomaly-detector

> Sistema di rilevamento anomalie in tempo reale per asset finanziari

---

## 📋 Panoramica

**Anomaly-detector** è un sistema di rilevamento anomalie in tempo reale per asset finanziari. Scarica dati intraday (OHLCV) tramite **yfinance**, calcola feature statistiche e z-score robusti, e invia alert via **Telegram** e/o li logga in **CSV** quando vengono rilevati movimenti anomali.

---

## 🏗️ Architettura

Il sistema è composto da **5 moduli principali**:

### 1. `config.py` — Configurazione

Dataclass `Config` con valori di default:

| Parametro | Valore Default | Descrizione |
|---|---|---|
| `symbols` | `["CL=F", "BZ=F", "USO", "XLE"]` | Simboli monitorati (futures e ETF energetici) |
| `benchmark` | `SPY` | Benchmark di riferimento (S&P 500) |
| `interval` | `5m` | Intervallo delle barre OHLCV |
| `zscore_threshold` | `2.5` | Soglia z-score per return, volume e range |
| `abs_return_threshold` | `1.5%` | Soglia return assoluto per "strong move" |
| `min_signals` | `2` | Segnali minimi anomali per emettere un alert |
| `cooldown_seconds` | `300` | Cooldown per simbolo (5 minuti) |
| `scan_interval_seconds` | `60` | Intervallo tra le scansioni |
| `cross_asset_filter` | `0.5` | Soglia filtro cross-asset (50%) |

### 2. `data.py` — Ingestione Dati

- Usa **`yfinance`** per scaricare barre OHLCV intraday
- Normalizza i nomi delle colonne
- Gestisce errori per singolo simbolo senza bloccare gli altri

### 3. `features.py` — Feature Engineering

Aggiunge colonne derivate al DataFrame OHLCV:

| Feature | Descrizione |
|---|---|
| `pct_return` | Variazione percentuale del Close |
| `log_return` | Log-return |
| `candle_range_pct` | `(High - Low) / Close` |
| `dollar_volume` | `Close × Volume` |
| `ema_fast` | Media mobile esponenziale veloce (10 periodi) |
| `ema_slow` | Media mobile esponenziale lenta (30 periodi) |
| `return_zscore` | Z-score robusto sul return |
| `volume_zscore` | Z-score robusto sul volume |
| `range_zscore` | Z-score robusto sul range della candela |

**Z-score robusti** basati su MAD (Median Absolute Deviation):

```
Z = (x - rolling_median) / (1.4826 × rolling_MAD)
```

> Finestra rolling di default: **50 barre**

### 4. `engine.py` — Motore di Rilevamento

- **`AnomalyEngine`**: classe principale che orchestra tutto il flusso
  - `scan_once()` → esegue un singolo ciclo di scansione
  - `run()` → loop continuo con gestione degli errori
- **`StateManager`**: gestisce il cooldown per simbolo

**Regole di anomalia** — un alert viene emesso se:
- ✅ Almeno **≥ 2 segnali anomali** (z-score sopra soglia), **oppure**
- ✅ Il **return assoluto** supera la soglia di "strong move" (1.5%)

**Filtro cross-asset**: esclude segnali se il benchmark (SPY) si è mosso nella stessa direzione per almeno il **50%** del movimento dell'asset, indicando che il movimento è di mercato generale e non specifico dell'asset.

**Cooldown**: previene alert duplicati per lo stesso simbolo (default **5 minuti**).

### 5. `alerts.py` — Sistema di Notifiche

- **`TelegramAlerter`**: invia messaggi formattati in Markdown via Telegram Bot API
  - Retry automatico: **3 tentativi** con backoff esponenziale
  - Credenziali da variabili d'ambiente o parametri diretti
- **`CSVAlertLogger`**: appende ogni alert in un file CSV per audit trail

**Formato messaggio alert**:
```
🚨 ANOMALY DETECTED: <SIMBOLO>
📅 <timestamp>
📈/📉 Direction: <UP/DOWN>
💹 Return: <valore>%
📊 Volume Z-Score: <valore>
📐 Range Z-Score: <valore>
🔔 Signals: <lista segnali attivati>
```

---

## 📁 Struttura del Progetto

```
Anomaly-detector/
├── .env.example          # Template variabili d'ambiente
├── .gitignore
├── AnomalyFinder         # Placeholder
├── alerts.py             # Modulo alerting (Telegram + CSV)
├── config.py             # Configurazione engine (dataclass)
├── data.py               # Ingestione dati via yfinance
├── engine.py             # Motore di rilevamento anomalie
├── features.py           # Feature engineering + z-scores
├── main.py               # Entry-point dell'applicazione
├── requirements.txt      # Dipendenze Python
└── tests/
    ├── __init__.py
    ├── test_alerts.py
    ├── test_config.py
    ├── test_data.py
    ├── test_engine.py
    ├── test_features.py
    └── test_main.py
```

---

## ⚙️ Installazione e Configurazione

```bash
# 1. Clona il repository
git clone https://github.com/indexGui/Anomaly-detector.git
cd Anomaly-detector

# 2. Crea un virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# oppure
.venv\Scripts\activate      # Windows

# 3. Installa le dipendenze
pip install -r requirements.txt

# 4. Configura le variabili d'ambiente
cp .env.example .env
# Modifica .env con le tue credenziali Telegram
```

---

## 📦 Dipendenze

| Pacchetto | Versione minima | Utilizzo |
|---|---|---|
| `yfinance` | `>= 0.2.18` | Download dati OHLCV intraday |
| `pandas` | `>= 2.0.0` | Manipolazione DataFrame |
| `numpy` | `>= 1.24.0` | Calcoli numerici e statistici |
| `requests` | `>= 2.28.0` | Chiamate HTTP API Telegram |

---

## 🔐 Variabili d'Ambiente

Copia `.env.example` in `.env` e compila i valori:

| Variabile | Default | Descrizione |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Token del bot Telegram (obbligatorio per alert Telegram) |
| `TELEGRAM_CHAT_ID` | — | ID della chat/canale Telegram |
| `TELEGRAM_ENABLED` | `true` | Abilita/disabilita l'invio di alert via Telegram |
| `SCAN_INTERVAL_SECONDS` | `60` | Intervallo tra le scansioni (secondi) |
| `COOLDOWN_SECONDS` | `300` | Cooldown per simbolo per evitare alert duplicati |
| `CSV_LOG_ENABLED` | `false` | Abilita il logging degli alert su file CSV |
| `CSV_LOG_PATH` | `alerts.csv` | Percorso del file CSV per il logging |

---

## ▶️ Esecuzione

```bash
python main.py
```

Il sistema avvierà il loop di scansione continua, analizzando i simboli configurati ogni 60 secondi (default) e inviando alert quando vengono rilevate anomalie.

---

## 🧪 Test

Il progetto include una suite di test completa nella cartella `tests/` con copertura per tutti i moduli:

```bash
pytest tests/
```

| File di test | Modulo testato |
|---|---|
| `test_config.py` | Configurazione e valori di default |
| `test_data.py` | Ingestione dati e normalizzazione |
| `test_features.py` | Feature engineering e z-score |
| `test_engine.py` | Motore di rilevamento e regole |
| `test_alerts.py` | Alerting Telegram e CSV |
| `test_main.py` | Entry-point e integrazione |
