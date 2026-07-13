# 📞 Call Ops Toolkit

One Streamlit app, two tools in the sidebar:

| Sidebar page | What it does |
|---|---|
| 📊 **Queue Report Builder** | Upload raw call report (CSV/Excel) → parses the **Call Flow** column → builds *Queue Wise Detail*, *Agent Legs*, *Queue Summary*, *Agent × Queue* → download as Excel **or** push all 4 tabs into any Google Sheet |
| 🎙️ **Bulk Call Transcriber** | Your existing app, unchanged — Google Sheet Column R → Deepgram → Column S, with auto-resume |

## Project structure

```
callapp/
├── app.py                  # entry point — sidebar navigation only
├── views/
│   ├── queue_report.py     # Apps Script logic ported to Python/pandas
│   └── transcriber.py      # your existing app.py (set_page_config removed)
├── requirements.txt
└── secrets.toml.example    # template — fill and paste into Streamlit secrets
```

## Deploy on Streamlit Community Cloud (free)

1. **Push to GitHub**: create a repo, upload all files above
   (do NOT upload a real `secrets.toml` — only the `.example`).
2. Go to **https://share.streamlit.io** → *New app* → pick your repo,
   branch `main`, main file **`app.py`** → Deploy.
3. **Add secrets**: App → ⋮ → *Settings* → *Secrets* → paste the contents of
   `secrets.toml.example` with your real values:
   - `DEEPGRAM_API_KEY` — needed by the Transcriber page
   - `[gcp_service_account]` — needed by the Transcriber page **and** the
     "Push to Google Sheet" option of the Queue Report page.
     The Excel-download option works without any secrets.
4. **Share Google Sheets with the service account**: open each sheet
   (transcriber source sheet, and any destination sheet for the queue report)
   → *Share* → add the `client_email` from your service account JSON →
   **Editor** access.

## Run locally

```bash
pip install -r requirements.txt
mkdir -p .streamlit && cp secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml with real values
streamlit run app.py
```

## Notes

- Queue Report talk-time rule (same as your Apps Script):
  *agent talk time = agent answer → next `Inboundqueue` event (transfer), else Hangup / Call End Time.*
- If a header name in your export differs, change it in the sidebar
  **Column Mapping** section — no code edits needed.
- Queue Summary / Agent × Queue in the Google Sheet push are written as
  **computed values** (not live formulas), which is more robust than the
  Apps Script's COUNTIF/SUMIF approach.
