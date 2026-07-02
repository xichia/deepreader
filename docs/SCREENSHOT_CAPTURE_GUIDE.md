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

### A. Demo Workbench Composite View
- **Target File:** `docs/screenshots/demo-workbench.png`
- **Wording / Warding:** Do not crop or split this composite screenshot into separate files. It must capture the jobs panel, the records/summaries panel, and the search results panel together in a single browser window.
- **Actions:**
  1. Arrange the dashboard so that the job steps/status list, selected record summaries, and search results (for query `what causes low flow?` showing scores and chips) are visible in one view.
  2. Ensure search results display retrieval methods, aggregate scores, location metadata, and score chips clearly.
  3. Capture the full browser window/workbench viewport and save as `docs/screenshots/demo-workbench.png`.
- **Note:** Individual job lifecycle or separate records/search files are no longer separate targets in this pass.

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
