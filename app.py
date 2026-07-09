# -*- coding: utf-8 -*-
"""
🎙️ Acefone Bulk Call Transcriber — Streamlit Edition
Colab notebook se converted. Google Sheet ke Column R se recording URL
uthata hai, Deepgram se transcribe karta hai, aur Column S mein likhta hai.

Auth: Google Service Account (st.secrets se)
Key : Deepgram API key (st.secrets se)
"""

import time
from datetime import datetime

import requests
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

# ─────────────────────────────────────────────────────────────
# Page setup
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Bulk Call Transcriber", page_icon="🎙️", layout="wide")
st.title("🎙️ Bulk Call Transcriber")
st.caption("Google Sheet → Deepgram → Transcript (Column R → Column S) • Auto-resume supported")

# ─────────────────────────────────────────────────────────────
# Secrets check
# ─────────────────────────────────────────────────────────────
missing = []
if "DEEPGRAM_API_KEY" not in st.secrets:
    missing.append("`DEEPGRAM_API_KEY`")
if "gcp_service_account" not in st.secrets:
    missing.append("`[gcp_service_account]` section")

if missing:
    st.error(
        "Secrets missing: " + ", ".join(missing) +
        "\n\nStreamlit Cloud → App → Settings → Secrets mein add karo "
        "(local testing ke liye `.streamlit/secrets.toml`)."
    )
    st.stop()

DEEPGRAM_API_KEY = st.secrets["DEEPGRAM_API_KEY"]

# ─────────────────────────────────────────────────────────────
# Google Sheets client (cached)
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes
    )
    return gspread.authorize(creds)

# ─────────────────────────────────────────────────────────────
# Sidebar — Configuration
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    sheet_id = st.text_input(
        "Google Sheet ID",
        value="",
        help="Sheet URL ka beech wala hissa: docs.google.com/spreadsheets/d/<YEH_WALA>/edit",
    )
    tab_name = st.text_input("Sheet Tab Name", value="Lead Data 1500")

    st.subheader("Columns (1-based)")
    col1, col2 = st.columns(2)
    with col1:
        recording_col = st.number_input("Recording URL col", min_value=1, value=18, help="R = 18")
    with col2:
        transcript_col = st.number_input("Transcript col", min_value=1, value=19, help="S = 19")

    st.subheader("Deepgram Settings")
    dg_model = st.selectbox("Model", ["nova-2", "nova-3", "enhanced", "base"], index=0)
    dg_language = st.selectbox("Language", ["hi", "en", "hi-Latn"], index=0)
    dg_diarize = st.checkbox("Diarize (speaker labels)", value=True)

    st.subheader("Bulk Tuning")
    start_row = st.number_input("Start row", min_value=2, value=2, help="2 = header skip")
    max_rows = st.number_input("Max rows (0 = all pending)", min_value=0, value=0)
    delay_seconds = st.number_input("Delay between rows (sec)", min_value=0.0, value=0.3, step=0.1)
    write_batch_size = st.number_input("Sheet write batch size", min_value=1, value=25)

MAX_DOWNLOAD_RETRIES = 3
MAX_TRANSCRIBE_RETRIES = 3

DG_PARAMS = {
    "model": dg_model,
    "language": dg_language,
    "detect_language": "true",
    "punctuate": "true",
    "diarize": "true" if dg_diarize else "false",
    "smart_format": "true",
}

# ─────────────────────────────────────────────────────────────
# Helpers (Colab version se same logic)
# ─────────────────────────────────────────────────────────────
def download_audio(url, timeout=60, retries=MAX_DOWNLOAD_RETRIES):
    err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code == 200:
                return resp.content, None
            elif resp.status_code == 404:
                return None, "HTTP 404 (recording not found / expired)"
            else:
                err = f"HTTP {resp.status_code}"
        except Exception as e:
            err = str(e)[:120]
        if attempt < retries:
            time.sleep(3 * attempt)
    return None, err


def detect_content_type(url, audio_bytes):
    url_lower = url.lower()
    if "mp3" in url_lower or url_lower.endswith(".mp3"):
        return "audio/mpeg"
    if "wav" in url_lower or url_lower.endswith(".wav"):
        return "audio/wav"
    if "ogg" in url_lower or url_lower.endswith(".ogg"):
        return "audio/ogg"
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
        return "audio/mpeg"
    if audio_bytes[:4] == b"RIFF":
        return "audio/wav"
    return "audio/mpeg"


def transcribe_audio(audio_bytes, url, api_key, params, retries=MAX_TRANSCRIBE_RETRIES):
    dg_url = "https://api.deepgram.com/v1/listen"
    ctype = detect_content_type(url, audio_bytes)
    headers = {"Authorization": f"Token {api_key}", "Content-Type": ctype}
    err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                dg_url, params=params, headers=headers, data=audio_bytes, timeout=300
            )
            if resp.status_code == 200:
                return resp.json(), None
            err = f"HTTP {resp.status_code} — {resp.text[:150]}"
        except Exception as e:
            err = str(e)[:150]
        if attempt < retries:
            time.sleep(5 * attempt)
    return None, err


def parse_transcript(result):
    try:
        return result["results"]["channels"][0]["alternatives"][0]["paragraphs"]["transcript"]
    except (KeyError, TypeError):
        try:
            return result["results"]["channels"][0]["alternatives"][0].get("transcript", "")
        except Exception:
            return ""

# ─────────────────────────────────────────────────────────────
# Connect + Preview
# ─────────────────────────────────────────────────────────────
if not sheet_id:
    st.info("👈 Sidebar mein Google Sheet ID daalo, phir preview/start karo.")
    st.stop()

try:
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(sheet_id)
    ws = spreadsheet.worksheet(tab_name)
except gspread.exceptions.WorksheetNotFound:
    st.error(f"Tab '{tab_name}' nahi mila. Tab ka naam check karo.")
    st.stop()
except Exception as e:
    st.error(
        f"Sheet open nahi hui: {e}\n\n"
        "⚠️ Check karo ki sheet ko service account email ke saath **Editor** access "
        "se share kiya hai (email `secrets` wali JSON mein `client_email` field mein hai)."
    )
    st.stop()

st.success(f"✅ Connected: **{tab_name}** ({ws.row_count} rows)")

tab_preview, tab_run = st.tabs(["📋 Preview", "🚀 Run Bulk Transcription"])

# ── Preview tab ──────────────────────────────────────────────
with tab_preview:
    if st.button("Preview first 5 data rows"):
        last_col_letter = rowcol_to_a1(1, max(recording_col, transcript_col)).rstrip("1")
        preview_rows = ws.get(f"A1:{last_col_letter}6")
        table = []
        for i, row in enumerate(preview_rows[1:6], start=2):
            row = list(row) + [""] * (max(recording_col, transcript_col) - len(row))
            url = str(row[recording_col - 1])
            done = "✅ done" if str(row[transcript_col - 1]).strip() else "⬜ empty"
            table.append({"Row": i, "Recording URL": url[:70], "Transcript status": done})
        st.dataframe(table, use_container_width=True)
        st.caption("URLs sahi lag rahe hain? To 'Run' tab mein jaake start karo.")

# ── Run tab ──────────────────────────────────────────────────
with tab_run:
    st.warning(
        "⚠️ Processing ke दौरान **yeh browser tab open rakho**. Tab band karne se job ruk jayegi. "
        "Lekin tension nahi — auto-resume hai: dobara start karoge to done rows skip ho jayengi."
    )

    if st.button("🚀 Start Bulk Transcription", type="primary"):
        with st.spinner("Sheet data read ho raha hai (single API call)..."):
            all_values = ws.get_all_values()
        total_rows = len(all_values)

        # Identify pending rows
        to_process = []
        for i, row in enumerate(all_values):
            sheet_row = i + 1
            if sheet_row < start_row:
                continue
            row = list(row) + [""] * (max(recording_col, transcript_col) - len(row))
            url = str(row[recording_col - 1]).strip()
            existing_tx = str(row[transcript_col - 1]).strip()
            if not url or not url.startswith("http"):
                continue
            if existing_tx:
                continue
            to_process.append((sheet_row, url))
            if max_rows and len(to_process) >= max_rows:
                break

        st.write(f"**Total rows (incl. header):** {total_rows}")
        st.write(f"**Pending rows to transcribe:** {len(to_process)}")

        if not to_process:
            st.success("✅ Kuch karna nahi hai — saari rows already transcribed hain.")
            st.stop()

        progress = st.progress(0.0, text="Starting...")
        stats_box = st.empty()
        log_box = st.expander("📜 Live log (last 20 entries)", expanded=True)
        log_area = log_box.empty()

        success, failed = 0, 0
        failed_rows = []
        pending_writes = {}
        logs = []

        def flush_writes():
            if not pending_writes:
                return
            data = [
                {"range": rowcol_to_a1(r, transcript_col), "values": [[text]]}
                for r, text in pending_writes.items()
            ]
            ws.batch_update(data, value_input_option="RAW")
            pending_writes.clear()

        start_time = datetime.now()

        for idx, (sheet_row, url) in enumerate(to_process, start=1):
            audio_bytes, dl_err = download_audio(url)
            if not audio_bytes:
                note = f"[ERROR: download failed - {dl_err}]"
                pending_writes[sheet_row] = note
                failed_rows.append((sheet_row, note))
                failed += 1
                logs.append(f"❌ Row {sheet_row}: {note}")
            else:
                result, tx_err = transcribe_audio(audio_bytes, url, DEEPGRAM_API_KEY, DG_PARAMS)
                if result is None:
                    note = f"[ERROR: transcription failed - {tx_err}]"
                    pending_writes[sheet_row] = note
                    failed_rows.append((sheet_row, note))
                    failed += 1
                    logs.append(f"❌ Row {sheet_row}: {note}")
                else:
                    transcript = parse_transcript(result)
                    pending_writes[sheet_row] = transcript or "[EMPTY: no speech detected]"
                    success += 1
                    logs.append(f"✅ Row {sheet_row}: {len(transcript)} chars")

            if len(pending_writes) >= write_batch_size:
                flush_writes()

            # UI updates
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = idx / elapsed if elapsed > 0 else 0
            eta_min = ((len(to_process) - idx) / rate / 60) if rate > 0 else 0
            progress.progress(
                idx / len(to_process),
                text=f"Row {sheet_row} • {idx}/{len(to_process)} • ETA ~{eta_min:.0f} min",
            )
            stats_box.markdown(f"**✅ Success:** {success} &nbsp;&nbsp; **❌ Failed:** {failed}")
            log_area.code("\n".join(logs[-20:]))

            time.sleep(delay_seconds)

        flush_writes()

        # Summary
        st.divider()
        st.subheader("📊 Summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Transcribed", success)
        c2.metric("Failed", failed)
        c3.metric("Total processed", len(to_process))
        st.markdown(f"🔗 [Open Google Sheet](https://docs.google.com/spreadsheets/d/{sheet_id})")

        if failed_rows:
            st.warning("Failed rows (first 20):")
            st.code("\n".join(f"Row {r}: {reason}" for r, reason in failed_rows[:20]))
            st.caption(
                "In rows mein Column S mein [ERROR: ...] note likha gaya hai, isliye yeh dobara "
                "auto-retry nahi hongi. Issue fix karke wo cell clear karo aur dobara Start dabao."
            )

        st.info(
            "💡 Session beech mein toot jaaye to bas dobara Start dabao — "
            "jin rows mein Column S bhara hai wo automatically skip hongi."
        )
