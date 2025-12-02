# Workflow Connections Map

This document shows all expected connections in the n8n Container Tracking workflow.

## Connection Flow

```
Gmail Trigger
    ↓
Filter Email
    ↓
Split Attachments
    ↓
Classify Attachment
    ↓
Prepare Attachment
    ↓
Route by Type
    ├─→ [TRUE]  → PDF to Text
    │              ↓
    │              Extract Container Numbers
    │              ↓
    │              Parse Container Response
    │              ↓
    │              Merge Results (Input 1)
    │
    └─→ [FALSE] → Filter PKL Only
                   ↓
                   Read XLSX
                   ↓
                   Extract SKU & Quantities
                   ↓
                   Parse PKL Response
                   ↓
                   Merge Results (Input 2)

Merge Results
    ↓
Format Output
```

## Detailed Connections

1. **Gmail Trigger** → Filter Email
2. **Filter Email** → Split Attachments
3. **Split Attachments** → Classify Attachment
4. **Classify Attachment** → Prepare Attachment
5. **Prepare Attachment** → Route by Type
6. **Route by Type** → 
   - TRUE path: PDF to Text
   - FALSE path: Filter PKL Only
7. **PDF to Text** → Extract Container Numbers
8. **Extract Container Numbers** → Parse Container Response
9. **Parse Container Response** → Merge Results (Input 1)
10. **Filter PKL Only** → Read XLSX
11. **Read XLSX** → Extract SKU & Quantities
12. **Extract SKU & Quantities** → Parse PKL Response
13. **Parse PKL Response** → Merge Results (Input 2)
14. **Merge Results** → Format Output

## Troubleshooting

If connections appear missing in n8n:

1. **Verify JSON structure**: Check that `workflow.json` has a top-level `connections` object
2. **Node names must match exactly**: Connection references use exact node names
3. **IF node connections**: The "Route by Type" IF node has two outputs:
   - First array element = TRUE path
   - Second array element = FALSE path
4. **Import method**: Use "Import from File" in n8n, not copy-paste
5. **Node positions**: If nodes are too far apart, connections may not render visually but will still work

## Verification Command

Run this PowerShell command to verify connections:
```powershell
$workflow = Get-Content "workflow.json" -Raw | ConvertFrom-Json
$workflow.connections.PSObject.Properties | ForEach-Object {
    Write-Host "$($_.Name) -> $($_.Value.main[0][0].node)"
}
```

