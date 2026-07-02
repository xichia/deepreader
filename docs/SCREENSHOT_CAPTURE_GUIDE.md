# DeepReader Screenshot Capture Guide

This guide describes how to manually refresh the project's demo screenshots for the `v0.8-demo-assets-polish` milestone. 

All steps are completely local-only, offline, and use mock or deterministic extractive options. **Do not run live Gemini/provider calls, and do not use OpenStax.**

---

## 1. Prerequisites & Services Startup

Run each command in a separate terminal from the repository root:

### Terminal 1: Backend Service (Local Mode)
```bash
cd backend
.venv/bin/python3 -m uvicorn deepreader.api.main:app --host 127.0.0.1 --port 8000
```
*Validates that the main FastAPI backend is running locally.*

### Terminal 2: Frontend Dashboard
```bash
cd frontend
pnpm dev
```
*Launches the Vite dev server at `http://127.0.0.1:5173`.*

---

## 2. Setup Demo Data

1. Open your browser and navigate to `http://127.0.0.1:5173/`.
2. Locate the upload card/button in the **Library** panel.
3. Select and upload the local file: `examples/simple_manual.txt`.
4. Click on the uploaded document in the list to select it.
5. In the **Records** panel, click **Generate summaries**. This executes the local extractive summary generator. Wait for the summaries to appear.

---

## 3. Manual Screenshot Steps

### A. Search Results Provenance Display
- **Target File:** `docs/screenshots/search-results.png`
- **Actions:**
  1. Click on the **Search** tab.
  2. Type the query: `what causes low flow?` and submit.
  3. Ensure that the results display:
     - Retrieval method (e.g. `bm25_source_text` or `bm25_summary_text`).
     - Aggregate search score.
     - Component score chips (clearly separated, readable CSS pills).
     - Record ID / Stable ID.
     - Source location metadata (e.g. `section_title / page_number`).
  4. Crop your browser window to exclude browser borders, tabs, or address bar.
  5. Capture the search results viewport and save it as `docs/screenshots/search-results.png`.

### B. QA Citations and Evidence Provenance
- **Target File:** `docs/screenshots/qa-citations.png`
- **Actions:**
  1. Click on the **QA Workbench** tab.
  2. Ask the question: `What causes low flow?` and submit.
  3. Wait for the deterministic answer and cited segments to render.
  4. Locate the **Evidence Provenance Panel**. Confirm that it clearly classifies:
     - *Used in answer* vs *Available only* evidence cards.
     - Individual retrieval methods, scores, record IDs, and location metadata.
  5. Crop to focus on the QA answer area, cited text, and the Evidence provenance side-by-side.
  6. Capture and save as `docs/screenshots/qa-citations.png`.

### C. Job Step Lifecycle
- **Target File:** `docs/screenshots/jobs.png`
- **Actions:**
  1. Click on the **Processing** or **Jobs** section.
  2. Locate the summary generation job details.
  3. Ensure the view displays the job progress, status, individual job steps, targets (`stable_id`), attempts count, and any error status pills.
  4. Capture the panel and save as `docs/screenshots/jobs.png`.
- **Fallback Rule:** If generating job failure states (e.g. cancelled, skipped) is too time-consuming or risky to recreate manually without active scheduler disruption, **do not capture/overwrite this file**. Keep the existing `jobs.png` unchanged.

### D. Records and Summaries (Optional)
- **Target File:** `docs/screenshots/records-summaries.png`
- **Actions:**
  1. Navigate to the main library and select the document.
  2. Adjust viewport width so that ground-truth source text and generated local summaries are clearly visible side-by-side in the Records list.
  3. Capture the viewport and save as `docs/screenshots/records-summaries.png`.

---

## 4. Shutdown & Cleanup

After capturing the screenshots:
1. Stop the backend process in Terminal 1 (`Ctrl+C`).
2. Stop the frontend server in Terminal 2 (`Ctrl+C`).
3. Confirm that no lingering processes are occupying the ports:
   ```bash
   lsof -i :8000 -i :5173 || true
   ```

---

## 5. Verification Commands

Run the following validation suite before staging or committing the refreshed screenshots:

```bash
# Check that no code syntax issues or trailing whitespaces exist
git diff --check

# Check which screenshots were successfully updated
git status --short

# Display diff stats for verification
git diff --stat

# Confirm files are valid PNGs and non-empty
ls -lh docs/screenshots/*.png
file docs/screenshots/*.png
```
