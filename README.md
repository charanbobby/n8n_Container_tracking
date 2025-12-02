# n8n Container Tracking Automation

## Overview
This automation processes emails from `sri.sunkara@silkandsnow.com` that contain shipping documents, extracts key information using AI, and organizes the data for container tracking.

## Email Processing Flow

### Input
- **Email Source**: `sri.sunkara@silkandsnow.com`
- **Attachments**: 3 files per email
  1. **Bill (PDF)**: Contains container number(s)
  2. **Commercial Invoice (XLSX)**: File with "CI" in title
  3. **Packaging List (XLSX)**: File with "PKL" in title - contains SKU and quantity information

### Processing Steps

1. **Gmail Trigger**
   - Monitor Gmail inbox for emails from `sri.sunkara@silkandsnow.com`
   - Automatically filters by sender

2. **Attachment Download & Classification**
   - Download all attachments
   - Classify attachments by filename:
     - PDF with "bill" in title → Bill document
     - XLSX with "CI" in title → Commercial Invoice
     - XLSX with "PKL" in title → Packaging List

3. **Data Extraction**

   **From Packaging List (PKL):**
   - Extract SKU codes (format: `SNSFNWO5006NR2`)
   - Extract expected quantities (qty expected)
   - Use OpenRouter API with LLM for extraction

   **From Bill (PDF):**
   - Extract container number(s)
   - Use OpenRouter API with LLM for extraction

4. **Output**
   - Structured data with:
     - Container number(s)
     - SKU codes
     - Quantities

## Technology Stack
- **n8n**: Workflow automation platform
- **OpenRouter API**: LLM service for document extraction
- **Python**: Script to generate n8n workflow JSON

## Files
- `generate_workflow.py`: Python script to generate n8n workflow JSON
- `workflow.json`: Generated n8n workflow file (output)

## Setup Instructions

1. Activate virtual environment:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. Install dependencies (if any are added later):
   ```powershell
   pip install -r requirements.txt
   ```

3. Configure OpenRouter API key:
   - Open `generate_workflow.py`
   - Find the line: `OPENROUTER_API_KEY = "YOUR_OPENROUTER_API_KEY_HERE"`
   - Replace with your actual OpenRouter API key

4. Run the generator:
   ```powershell
   python generate_workflow.py
   ```
   This will create `workflow.json` in the current directory.

5. Import `workflow.json` into n8n:
   - Open n8n
   - Go to Workflows
   - Click "Import from File"
   - Select `workflow.json`

6. Configure in n8n:
   - Set up Gmail OAuth2 credentials in the "Gmail Trigger" node
   - Verify OpenRouter API key is set in both HTTP Request nodes (if not using the script's default)
   - Test with a sample email

## Configuration

### OpenRouter API
- Set your OpenRouter API key in the Python script
- Choose appropriate LLM model (default: recommended model)

### Email Configuration
- Configure Gmail OAuth2 credentials in n8n
- Set up Gmail account connection in the "Gmail Trigger" node
- The trigger will automatically filter emails from `sri.sunkara@silkandsnow.com`

