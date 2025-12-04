"""
n8n Workflow Generator for Container Tracking Automation

This script generates an n8n workflow JSON file that:
1. Monitors emails from sri.sunkara@silkandsnow.com
2. Downloads and classifies 3 attachments (Bill PDF, CI XLSX, PKL XLSX)
3. Extracts container numbers from Bill using OpenRouter LLM
4. Extracts SKU and quantities from PKL using OpenRouter LLM
"""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List

# Centralized prompt strings
PROMPTS = {
    "bill_system": (
        "You are an expert at extracting container numbers from shipping documents. "
        "Extract all container numbers from the provided text. Container numbers typically "
        "follow formats like ABCD1234567 or ABCD 123456 7. Return ONLY a JSON object with "
        "a 'container_numbers' array of strings."
    ),
    "pkl_system": (
        "You read packing lists exported from Excel. "
        "You are given one sheet as a JSON array of rows. "
        "Each row is an array of cells in order: [cell_0, cell_1, ...]. Some rows are headers, some are product lines, some are totals.\n\n"
        "Your tasks:\n\n"
        "1. Identify which column is the SKU column (codes like SNSFNWO5006NR2, usually alphanumeric, stable per product line).\n"
        "2. Identify which column is the line quantity column (count of units for that SKU).\n"
        "   - Prefer columns whose header contains QTY or QUANTITY.\n"
        "   - Do not use weights, CBM, dimensions, or totals as quantity.\n"
        "3. For each product row with a SKU, output one object with:\n"
        "   - sku (string)\n"
        "   - qty_expected (number, quantity for that SKU on that row)\n"
        "4. If the sheet contains a \"Total\" row (cells like Total, TOTAL etc.), extract the document-level total quantity from the appropriate quantity column.\n"
        "5. Compute the sum of all your qty_expected values.\n"
        "6. Set checksum_ok = true if your sum equals the document-level total quantity (when present), otherwise false.\n\n"
        "Return ONLY a JSON object with this shape:\n"
        "{\n"
        "  \"items\": [{\"sku\": \"SNSFNWO5006NR2\", \"qty_expected\": 82}, ...],\n"
        "  \"doc_total_qty_from_sheet\": 113,\n"
        "  \"qty_sum\": 113,\n"
        "  \"checksum_ok\": true\n"
        "}"
    ),
}

# Configuration dataclass
@dataclass
class WorkflowConfig:
    openrouter_model: str
    email_from: str = "sri.sunkara@silkandsnow.com"
    gmail_cred_id: str = "1"
    openrouter_cred_id: str = "1"
    prompt_version: str = "2025-12-02-01"

def generate_uuid():
    """Generate a UUID for n8n nodes"""
    return str(uuid.uuid4())

def create_openrouter_chat_node(name: str, position: List[int], config: WorkflowConfig) -> Dict[str, Any]:
    """Create a shared OpenRouter Chat Model node"""
    return {
        "parameters": {
            "model": config.openrouter_model,
            "options": {}
        },
        "id": generate_uuid(),
        "name": name,
        "type": "@n8n/n8n-nodes-langchain.lmChatOpenRouter",
        "typeVersion": 1,
        "position": position,
        "credentials": {
            "openRouterApi": {
                "id": config.openrouter_cred_id,
                "name": "OpenRouter account"
            }
        }
    }

def create_email_trigger_node(config: WorkflowConfig):
    """Create Gmail trigger node"""
    return {
        "parameters": {
            "pollTimes": {
                "item": [
                    {
                        "mode": "everyMinute"
                    }
                ]
            },
            "simple": False,
            "filters": {
                "sender": config.email_from
            },
            "options": {
                "downloadAttachments": True
            }
        },
        "id": generate_uuid(),
        "name": "Gmail Trigger",
        "type": "n8n-nodes-base.gmailTrigger",
        "typeVersion": 1,
        "position": [-768, 112],
        "webhookId": "gmail-trigger",
            "credentials": {
                "gmailOAuth2": {
                    "id": config.gmail_cred_id,
                    "name": "Gmail account"
                }
            }
    }


def create_split_attachments_node():
    """Create code node to split Gmail attachments into separate items"""
    return {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """// Split Gmail attachments into separate items
// Gmail provides attachments as binary fields: attachment_0, attachment_1, attachment_2, etc.
const allItems = [];

// Process all input items
for (const inputItem of $input.all()) {
  const binary = inputItem.binary || {};
  const json = inputItem.json || {};
  
  // Find all attachment binary fields
  const attachmentKeys = Object.keys(binary).filter(key => key.startsWith('attachment_'));
  
  // If no attachment_ keys found, check if binary has 'data' key (from previous processing)
  if (attachmentKeys.length === 0 && binary.data) {
    // Already split, pass through
    allItems.push({
      json: json,
      binary: binary
    });
  } else {
    // Create one item per attachment
    for (const key of attachmentKeys) {
      const attachmentNum = key.replace('attachment_', '');
      const attachmentData = binary[key];
      
      allItems.push({
        json: {
          ...json,
          attachmentKey: key,
          attachmentIndex: parseInt(attachmentNum),
          filename: attachmentData.fileName || attachmentData.filename || `attachment_${attachmentNum}`,
          mimeType: attachmentData.mimeType || attachmentData.mime || 'application/octet-stream',
          fileExtension: attachmentData.fileExtension || (attachmentData.fileName ? attachmentData.fileName.split('.').pop() : '')
        },
        binary: {
          data: attachmentData
        }
      });
    }
  }
}

return allItems;"""
        },
        "id": generate_uuid(),
        "name": "Split Attachments",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [-320, 112]
    }

def create_classify_attachment_node():
    """Create code node to classify attachments"""
    return {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """// Classify attachment by filename
const allItems = [];
const emailData = $('Gmail Trigger').item.json;

function hasExt(name, ext) {
  return name.toLowerCase().endsWith(ext.toLowerCase());
}

function containsWord(name, word) {
  return new RegExp(`\\\\b${word}\\\\b`, 'i').test(name);
}

for (const inputItem of $input.all()) {
  const item = inputItem.json;
  const binary = inputItem.binary || {};
  const filenameRaw = item.filename || item.name || '';
  const filename = filenameRaw.toLowerCase();

  let attachmentType = 'unknown';

  if ((containsWord(filename, 'bill') || containsWord(filename, 'bol')) && hasExt(filename, '.pdf')) {
    attachmentType = 'bill';
  } else if (containsWord(filename, 'ci') && hasExt(filename, '.xlsx')) {
    attachmentType = 'commercial_invoice';
  } else if (
    (containsWord(filename, 'pkl') || containsWord(filename, 'pack') || containsWord(filename, 'packing')) &&
    hasExt(filename, '.xlsx')
  ) {
    attachmentType = 'packaging_list';
  }

  allItems.push({
    json: {
      ...item,
      attachmentType,
      filename: filenameRaw,
      emailSubject: emailData.subject || '',
      emailDate: emailData.date || '',
      emailFrom: emailData.from || emailData.sender || ''
    },
    binary,
  });
}

return allItems;"""
        },
        "id": generate_uuid(),
        "name": "Classify Attachment",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [-96, 112]
    }

def create_download_attachment_node():
    """Create code node to prepare attachment for processing"""
    return {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """// Prepare attachment data for processing
// Pass through all items as-is, ensuring binary is properly structured
const allItems = [];

for (const inputItem of $input.all()) {
  allItems.push({
    json: inputItem.json,
    binary: inputItem.binary || {}
  });
}

return allItems;"""
        },
        "id": generate_uuid(),
        "name": "Prepare Attachment",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [128, 112]
    }

def create_if_node_route_attachments():
    """Create IF node to route attachments to different processing paths"""
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 1
                },
                "conditions": [
                    {
                        "id": generate_uuid(),
                        "leftValue": "={{ $json.attachmentType }}",
                        "rightValue": "bill",
                        "operator": {
                            "type": "string",
                            "operation": "equals"
                        }
                    }
                ],
                "combinator": "and"
            },
            "options": {}
        },
        "id": generate_uuid(),
        "name": "Route by Type",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [352, 112]
    }

def create_filter_pkl_node():
    """Create filter node to only process PKL files (not CI)"""
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": False,
                    "leftValue": "",
                    "typeValidation": "strict"
                },
                "conditions": [
                    {
                        "id": generate_uuid(),
                        "leftValue": "={{ $json.attachmentType }}",
                        "rightValue": "packaging_list",
                        "operator": {
                            "type": "string",
                            "operation": "equals"
                        }
                    }
                ],
                "combinator": "and"
            },
            "options": {}
        },
        "id": generate_uuid(),
        "name": "Filter PKL Only",
        "type": "n8n-nodes-base.filter",
        "typeVersion": 2,
        "position": [576, 208]
    }


def create_openrouter_model_node(config: WorkflowConfig):
    """Create OpenRouter Chat Model node"""
    return create_openrouter_chat_node("OpenRouter Chat Model", [600, 16], config)

def create_openrouter_model_node_pkl(config: WorkflowConfig):
    """Create OpenRouter Chat Model node for PKL path"""
    return create_openrouter_chat_node("OpenRouter Chat Model1", [600, 208], config)

def create_pdf_to_text_node():
    """Create node to convert PDF to text"""
    return {
        "parameters": {
            "operation": "pdf",
            "options": {
                "joinPages": True
            },
            "binaryPropertyName": "data"
        },
        "id": generate_uuid(),
        "name": "PDF to Text",
        "type": "n8n-nodes-base.extractFromFile",
        "typeVersion": 1,
        "position": [600, 16]
    }

def create_prepare_bill_data_node():
    """Create Code node to prepare bill data for LLM extraction"""
    return {
        "parameters": {
            "mode": "runOnceForEachItem",
            "jsCode": """// Prepare bill data for LLM extraction
// The PDF text should already be extracted in the 'text' field
const item = $input.item.json;
const binary = $input.item.binary || {};

// Get text from extracted PDF
const textContent = item.text || '';

// Create chatInput field that LLM Chain expects
return {
  json: {
    ...item,
    chatInput: textContent,
    text: textContent
  },
  binary: binary
};"""
        },
        "id": generate_uuid(),
        "name": "Prepare Bill Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [800, 16]
    }

def create_openrouter_bill_extraction_node(config: WorkflowConfig):
    """Create Basic LLM Chain node to extract container numbers from bill"""
    return {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.chatInput || $json.text || '' }}",
            "messages": {
                "messageValues": [
                    {
                        "id": "system",
                        "message": PROMPTS["bill_system"]
                    },
                    {
                        "id": "user",
                        "message": "={{ $json.chatInput || $json.text || '' }}"
                    }
                ]
            },
            "options": {
                "responseFormat": {
                    "type": "json_object"
                }
            }
        },
        "id": generate_uuid(),
        "name": "Extract Container Numbers",
        "type": "@n8n/n8n-nodes-langchain.chainLlm",
        "typeVersion": 1.5,
        "position": [1000, 16]
    }

def create_parse_openrouter_response_node():
    """Create Code node to parse LLM response and aggregate all container numbers"""
    return {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """// Parse and aggregate all container numbers from LLM responses
const allContainers = [];

function extractJson(text) {
  if (!text) return null;

  // Remove fenced code blocks
  text = text.replace(/```json([\\s\\S]*?)```/gi, '$1').trim();

  // If it doesn't start with {, try to slice first {...} block
  if (!text.trim().startsWith('{')) {
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start !== -1 && end !== -1 && end > start) {
      text = text.slice(start, end + 1);
    }
  }

  try {
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
}

for (const item of $input.all()) {
  const text = item.json.text || item.json.response || '';
  const parsed = extractJson(text);
  if (!parsed) continue;

  if (parsed.container_numbers && Array.isArray(parsed.container_numbers)) {
    allContainers.push(...parsed.container_numbers);
  }
}

// Remove duplicates and return single item with aggregated containers
return [{
  json: {
    container_numbers: [...new Set(allContainers)]
  }
}];"""
        },
        "id": generate_uuid(),
        "name": "Parse Container Response",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1224, 16]
    }


def create_xlsx_read_node():
    """Create node to read XLSX file - using Extract From File node which can handle XLSX"""
    return {
        "parameters": {
            "operation": "xlsx",
            "options": {
                "sheetName": "",
                "range": "",
                "headerRow": False
            },
            "binaryPropertyName": "data"
        },
        "id": generate_uuid(),
        "name": "Read XLSX",
        "type": "n8n-nodes-base.extractFromFile",
        "typeVersion": 1,
        "position": [600, 208]
    }

def create_normalize_pkl_grid_node():
    """Create Code node to prepare PKL data - send raw rows as JSON to LLM"""
    return {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """// Generic PKL pre-processor.
// ExtractFromFile gives one item per row as json.row (your sample).
// We do NOT assume any fixed columns; we just send all rows as JSON.

const rows = $input.all()
  .map(i => i.json.row || [])
  .filter(r => Array.isArray(r) && r.length > 0);

// chatInput is a JSON string with the array-of-rows.
return [{
  json: {
    rows,
    chatInput: JSON.stringify(rows)
  }
}];"""
        },
        "id": generate_uuid(),
        "name": "Normalize PKL Grid",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [800, 208]
    }

def create_openrouter_pkl_extraction_node(config: WorkflowConfig):
    """Create Basic LLM Chain node to extract SKU and quantities from PKL"""
    return {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.chatInput }}",
            "messages": {
                "messageValues": [
                    {
                        "id": "system",
                        "message": PROMPTS["pkl_system"]
                    },
                    {
                        "id": "user",
                        "message": "=Here is the sheet as JSON array-of-rows:\n\n{{ $json.chatInput }}"
                    }
                ]
            },
            "options": {
                "responseFormat": {
                    "type": "json_object"
                }
            }
        },
        "id": generate_uuid(),
        "name": "Extract SKU & Quantities",
        "type": "@n8n/n8n-nodes-langchain.chainLlm",
        "typeVersion": 1.5,
        "position": [1000, 208]
    }

def create_parse_pkl_response_node():
    """Create Code node to parse PKL extraction response, aggregate items, and verify checksum"""
    return {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": """// Parse PKL LLM JSON and enforce our own checksum.

const allItems = [];
let docTotalFromSheet = null;
let llmReportedSum = null;
let llmChecksumOk = null;

function extractJson(text) {
  if (!text) return null;
  text = text.replace(/```json[\\s\\S]*?```/gi, m => m.replace(/```json|```/gi, '')).trim();
  if (!text.trim().startsWith('{')) {
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start !== -1 && end !== -1 && end > start) {
      text = text.slice(start, end + 1);
    }
  }
  try {
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
}

for (const item of $input.all()) {
  const text = item.json.text || item.json.response || '';
  const parsed = extractJson(text);
  if (!parsed) continue;

  if (Array.isArray(parsed.items)) {
    allItems.push(...parsed.items);
  }
  if (parsed.doc_total_qty_from_sheet != null) {
    docTotalFromSheet = Number(parsed.doc_total_qty_from_sheet);
  }
  if (parsed.qty_sum != null) {
    llmReportedSum = Number(parsed.qty_sum);
  }
  if (typeof parsed.checksum_ok === 'boolean') {
    llmChecksumOk = parsed.checksum_ok;
  }
}

// Recompute sum ourselves
const recomputedSum = allItems.reduce(
  (acc, it) => acc + (Number(it.qty_expected) || 0),
  0
);

let checksumOk = null;
if (Number.isFinite(docTotalFromSheet)) {
  checksumOk = recomputedSum === docTotalFromSheet;
}

return [{
  json: {
    pkl_items: allItems,
    qty_sum: recomputedSum,
    doc_total_qty: docTotalFromSheet,
    checksum_ok: checksumOk,
    llm_reported_sum: llmReportedSum,
    llm_checksum_ok: llmChecksumOk
  }
}];"""
        },
        "id": generate_uuid(),
        "name": "Parse PKL Response",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1224, 208]
    }

def create_merge_node():
    """Create Code node to combine data from both parse nodes, handling timing delays"""
    return {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": "// Combine container numbers and PKL items from both parse nodes\n// This handles timing delays by waiting for all inputs\nlet containerNumbers = [];\nlet pklItems = [];\n\n// Process all input items - they may come from either parse node\nfor (const item of $input.all()) {\n  const json = item.json || {};\n  \n  // Check if this item has container_numbers (from Parse Container Response)\n  if (json.container_numbers && Array.isArray(json.container_numbers)) {\n    containerNumbers = json.container_numbers;\n  }\n  \n  // Check if this item has pkl_items (from Parse PKL Response)\n  if (json.pkl_items && Array.isArray(json.pkl_items)) {\n    pklItems = json.pkl_items;\n  }\n}\n\n// Return combined result\nreturn [{\n  json: {\n    container_numbers: containerNumbers,\n    pkl_items: pklItems\n  }\n}];"
        },
        "id": generate_uuid(),
        "name": "Merge Results",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1448, 112]
    }

def create_final_output_node():
    """Create node to format final output with only containers, SKUs, and quantities"""
    return {
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "id": generate_uuid(),
                        "name": "container_numbers",
                        "value": "={{ $json.container_numbers || [] }}",
                        "type": "array"
                    },
                    {
                        "id": generate_uuid(),
                        "name": "sku_items",
                        "value": "={{ $json.pkl_items || [] }}",
                        "type": "array"
                    }
                ]
            },
            "options": {}
        },
        "id": generate_uuid(),
        "name": "Format Output",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [1672, 112]
    }

def validate_workflow(workflow: dict) -> None:
    """Validate workflow structure - check that all connections reference valid nodes"""
    node_names = {n["name"] for n in workflow["nodes"]}
    for from_node, conn in workflow["connections"].items():
        assert from_node in node_names, f"Unknown from-node: {from_node}"
        for outputs in conn.get("main", []):
            for dest in outputs:
                assert dest["node"] in node_names, f"Unknown to-node: {dest['node']}"

def create_workflow(config: WorkflowConfig):
    """Generate the complete n8n workflow"""
    
    # Create all nodes
    email_trigger = create_email_trigger_node(config)
    split_attachments = create_split_attachments_node()
    classify_attachment = create_classify_attachment_node()
    download_attachment = create_download_attachment_node()
    route_by_type = create_if_node_route_attachments()
    
    # Create OpenRouter model nodes (one for each extraction chain)
    openrouter_model = create_openrouter_model_node(config)
    openrouter_model_pkl = create_openrouter_model_node_pkl(config)
    
    # Bill processing path - PDF extraction then prepare data
    pdf_to_text = create_pdf_to_text_node()
    prepare_bill_data = create_prepare_bill_data_node()
    extract_containers = create_openrouter_bill_extraction_node(config)
    parse_containers = create_parse_openrouter_response_node()
    
    # PKL processing path - XLSX reading then normalize grid
    filter_pkl = create_filter_pkl_node()
    read_xlsx = create_xlsx_read_node()
    normalize_pkl_grid = create_normalize_pkl_grid_node()
    extract_pkl = create_openrouter_pkl_extraction_node(config)
    parse_pkl = create_parse_pkl_response_node()
    
    # Merge and output
    merge_results = create_merge_node()
    format_output = create_final_output_node()
    
    # Build top-level connections object (n8n format)
    connections = {
        email_trigger["name"]: {
            "main": [[{"node": split_attachments["name"], "type": "main", "index": 0}]]
        },
        split_attachments["name"]: {
            "main": [[{"node": classify_attachment["name"], "type": "main", "index": 0}]]
        },
        classify_attachment["name"]: {
            "main": [[{"node": download_attachment["name"], "type": "main", "index": 0}]]
        },
        download_attachment["name"]: {
            "main": [[{"node": route_by_type["name"], "type": "main", "index": 0}]]
        },
        route_by_type["name"]: {
            "main": [
                [{"node": pdf_to_text["name"], "type": "main", "index": 0}],  # True: bill path
                [{"node": filter_pkl["name"], "type": "main", "index": 0}]     # False: PKL/CI path
            ]
        },
        openrouter_model["name"]: {
            "ai_languageModel": [
                [{"node": extract_containers["name"], "type": "ai_languageModel", "index": 0}]
            ]
        },
        openrouter_model_pkl["name"]: {
            "ai_languageModel": [
                [{"node": extract_pkl["name"], "type": "ai_languageModel", "index": 0}]
            ]
        },
        pdf_to_text["name"]: {
            "main": [[{"node": prepare_bill_data["name"], "type": "main", "index": 0}]]
        },
        prepare_bill_data["name"]: {
            "main": [[{"node": extract_containers["name"], "type": "main", "index": 0}]]
        },
        extract_containers["name"]: {
            "main": [[{"node": parse_containers["name"], "type": "main", "index": 0}]]
        },
        parse_containers["name"]: {
            "main": [[{"node": merge_results["name"], "type": "main", "index": 0}]]
        },
        filter_pkl["name"]: {
            "main": [[{"node": read_xlsx["name"], "type": "main", "index": 0}]]
        },
        read_xlsx["name"]: {
            "main": [[{"node": normalize_pkl_grid["name"], "type": "main", "index": 0}]]
        },
        normalize_pkl_grid["name"]: {
            "main": [[{"node": extract_pkl["name"], "type": "main", "index": 0}]]
        },
        extract_pkl["name"]: {
            "main": [[{"node": parse_pkl["name"], "type": "main", "index": 0}]]
        },
        parse_pkl["name"]: {
            "main": [[{"node": merge_results["name"], "type": "main", "index": 0}]]
        },
        merge_results["name"]: {
            "main": [[{"node": format_output["name"], "type": "main", "index": 0}]]
        }
    }
    
    # Build workflow
    workflow = {
        "name": "Container Tracking Automation",
        "nodes": [
            email_trigger,
            split_attachments,
            classify_attachment,
            download_attachment,
            route_by_type,
            openrouter_model,
            openrouter_model_pkl,
            pdf_to_text,
            prepare_bill_data,
            extract_containers,
            parse_containers,
            filter_pkl,
            read_xlsx,
            normalize_pkl_grid,
            extract_pkl,
            parse_pkl,
            merge_results,
            format_output
        ],
        "connections": connections,
        "pinData": {},
        "settings": {
            "executionOrder": "v1",
            "promptVersion": config.prompt_version
        },
        "staticData": None,
        "tags": [],
        "triggerCount": 1,
        "updatedAt": datetime.now().isoformat(),
        "versionId": generate_uuid()
    }
    
    return workflow

def main():
    """Main function to generate and save workflow"""
    print("Generating n8n workflow for Container Tracking Automation...")
    
    # Load configuration from environment variables
    config = WorkflowConfig(
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o"),
    )
    
    workflow = create_workflow(config)
    
    # Validate workflow structure
    validate_workflow(workflow)
    
    output_file = "workflow.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Workflow generated successfully!")
    print(f"   Saved to: {output_file}")
    print(f"   Total nodes: {len(workflow['nodes'])}")
    print(f"   Model: {config.openrouter_model}")
    print(f"   Prompt version: {config.prompt_version}")
    print("\nNext steps:")
    print("1. Import workflow.json into n8n")
    print("2. Configure Gmail OAuth2 credentials")
    print("3. Configure OpenRouter API credentials in n8n")
    print("4. Test the workflow with a sample email")

if __name__ == "__main__":
    main()

