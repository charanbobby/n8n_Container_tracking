"""
n8n Workflow Generator for Container Tracking Automation

This script generates an n8n workflow JSON file that:
1. Monitors emails from sri.sunkara@silkandsnow.com
2. Downloads and classifies 3 attachments (Bill PDF, CI XLSX, PKL XLSX)
3. Extracts container numbers from Bill using OpenRouter LLM
4. Extracts SKU and quantities from PKL using OpenRouter LLM
"""

import json
import uuid
from datetime import datetime

# Configuration
OPENROUTER_API_KEY = "YOUR_OPENROUTER_API_KEY_HERE"  # Replace with your API key
OPENROUTER_MODEL = "openai/gpt-4o"  # You can change this to any OpenRouter model
EMAIL_FROM = "sri.sunkara@silkandsnow.com"

def generate_uuid():
    """Generate a UUID for n8n nodes"""
    return str(uuid.uuid4())

def create_email_trigger_node():
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
                "sender": EMAIL_FROM
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
                "id": "1",
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
// Process all input items
const allItems = [];
const emailData = $('Gmail Trigger').item.json;

for (const inputItem of $input.all()) {
  const item = inputItem.json;
  const binary = inputItem.binary || {};
  const filename = (item.filename || item.name || '').toLowerCase();

  let attachmentType = 'unknown';
  if (filename.includes('bill') && (filename.endsWith('.pdf') || filename.includes('.pdf'))) {
    attachmentType = 'bill';
  } else if (filename.includes('ci') && (filename.endsWith('.xlsx') || filename.includes('.xlsx'))) {
    attachmentType = 'commercial_invoice';
  } else if ((filename.includes('pkl') || filename.includes('packaging')) && (filename.endsWith('.xlsx') || filename.includes('.xlsx'))) {
    attachmentType = 'packaging_list';
  }

  allItems.push({
    json: {
      ...item,
      attachmentType: attachmentType,
      filename: item.filename,
      emailSubject: emailData.subject || '',
      emailDate: emailData.date || '',
      emailFrom: emailData.from || emailData.sender || ''
    },
    binary: binary
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


def create_openrouter_model_node():
    """Create OpenRouter Chat Model node"""
    return {
        "parameters": {
            "model": OPENROUTER_MODEL,
            "options": {}
        },
        "id": generate_uuid(),
        "name": "OpenRouter Chat Model",
        "type": "@n8n/n8n-nodes-langchain.lmChatOpenRouter",
        "typeVersion": 1,
        "position": [600, 16],
        "credentials": {
            "openRouterApi": {
                "id": "1",
                "name": "OpenRouter account"
            }
        }
    }

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

def create_openrouter_bill_extraction_node():
    """Create Basic LLM Chain node to extract container numbers from bill"""
    return {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.chatInput || $json.text || '' }}",
            "messages": {
                "messageValues": [
                    {
                        "id": "system",
                        "message": "You are an expert at extracting container numbers from shipping documents. Extract all container numbers from the provided text. Container numbers typically follow formats like: ABCD1234567, ABCD 123456 7, or similar patterns with 4 letters followed by numbers. Return ONLY a JSON object with a 'container_numbers' array containing all found container numbers. If no container numbers are found, return an empty array."
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
    """Create node to parse LLM response"""
    return {
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "id": generate_uuid(),
                        "name": "container_numbers",
                        "value": "={{ JSON.parse($json.response).container_numbers }}",
                        "type": "array"
                    },
                    {
                        "id": generate_uuid(),
                        "name": "email_data",
                        "value": "={{ $('Gmail Trigger').item.json }}",
                        "type": "object"
                    }
                ]
            },
            "options": {}
        },
        "id": generate_uuid(),
        "name": "Parse Container Response",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [1224, 16]
    }


def create_xlsx_read_node():
    """Create node to read XLSX file"""
    return {
        "parameters": {
            "operation": "read",
            "binaryPropertyName": "data",
            "options": {
                "sheetName": "",
                "range": "",
                "headerRow": True
            }
        },
        "id": generate_uuid(),
        "name": "Read XLSX",
        "type": "n8n-nodes-base.spreadsheetFile",
        "typeVersion": 3,
        "position": [600, 208]
    }

def create_prepare_pkl_data_node():
    """Create Code node to prepare PKL data for LLM extraction"""
    return {
        "parameters": {
            "mode": "runOnceForEachItem",
            "jsCode": """// Prepare PKL data for LLM extraction
// The XLSX data should be in item.data after reading
const item = $input.item.json;
const binary = $input.item.binary || {};

// Get XLSX data (should be an array of rows)
const xlsxData = item.data || [];

// Create chatInput field that LLM Chain expects
return {
  json: {
    ...item,
    chatInput: JSON.stringify(xlsxData),
    data: xlsxData
  },
  binary: binary
};"""
        },
        "id": generate_uuid(),
        "name": "Prepare PKL Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [800, 208]
    }

def create_openrouter_pkl_extraction_node():
    """Create Basic LLM Chain node to extract SKU and quantities from PKL"""
    return {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.chatInput || JSON.stringify($json.data) || '' }}",
            "messages": {
                "messageValues": [
                    {
                        "id": "system",
                        "message": "You are an expert at extracting SKU codes and quantities from packaging lists. Extract all SKU codes (format like SNSFNWO5006NR2 - typically starts with letters and contains alphanumeric characters) and their corresponding expected quantities (qty expected). Return ONLY a JSON object with an 'items' array, where each item has 'sku' (string) and 'qty_expected' (number) fields. If a row doesn't have a valid SKU, skip it."
                    },
                    {
                        "id": "user",
                        "message": "=Extract SKU codes and quantities from this packaging list data: {{ $json.chatInput || JSON.stringify($json.data) || '' }}"
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
    """Create node to parse PKL extraction response"""
    return {
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "id": generate_uuid(),
                        "name": "pkl_items",
                        "value": "={{ JSON.parse($json.response).items }}",
                        "type": "array"
                    },
                    {
                        "id": generate_uuid(),
                        "name": "email_data",
                        "value": "={{ $('Gmail Trigger').item.json }}",
                        "type": "object"
                    }
                ]
            },
            "options": {}
        },
        "id": generate_uuid(),
        "name": "Parse PKL Response",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [1224, 208]
    }

def create_merge_node():
    """Create node to merge all extracted data"""
    return {
        "parameters": {
            "mode": "combine",
            "combineBy": "combineByPosition",
            "options": {}
        },
        "id": generate_uuid(),
        "name": "Merge Results",
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3,
        "position": [1448, 112]
    }

def create_final_output_node():
    """Create node to format final output"""
    return {
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "id": generate_uuid(),
                        "name": "container_numbers",
                        "value": "={{ $json[0].json.container_numbers || [] }}",
                        "type": "array"
                    },
                    {
                        "id": generate_uuid(),
                        "name": "sku_items",
                        "value": "={{ $json[1].json.pkl_items || [] }}",
                        "type": "array"
                    },
                    {
                        "id": generate_uuid(),
                        "name": "email_subject",
                        "value": "={{ $json[0].json.email_data.subject || '' }}",
                        "type": "string"
                    },
                    {
                        "id": generate_uuid(),
                        "name": "email_date",
                        "value": "={{ $json[0].json.email_data.date || '' }}",
                        "type": "string"
                    },
                    {
                        "id": generate_uuid(),
                        "name": "processed_at",
                        "value": f"={datetime.now().isoformat()}",
                        "type": "string"
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

def create_workflow():
    """Generate the complete n8n workflow"""
    
    # Create all nodes
    email_trigger = create_email_trigger_node()
    split_attachments = create_split_attachments_node()
    classify_attachment = create_classify_attachment_node()
    download_attachment = create_download_attachment_node()
    route_by_type = create_if_node_route_attachments()
    
    # Create OpenRouter model node (shared by both extraction chains)
    openrouter_model = create_openrouter_model_node()
    
    # Bill processing path - PDF extraction then prepare data
    pdf_to_text = create_pdf_to_text_node()
    prepare_bill_data = create_prepare_bill_data_node()
    extract_containers = create_openrouter_bill_extraction_node()
    parse_containers = create_parse_openrouter_response_node()
    
    # PKL processing path - XLSX reading then prepare data
    filter_pkl = create_filter_pkl_node()
    read_xlsx = create_xlsx_read_node()
    prepare_pkl_data = create_prepare_pkl_data_node()
    extract_pkl = create_openrouter_pkl_extraction_node()
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
                [{"node": extract_containers["name"], "type": "ai_languageModel", "index": 0}],
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
            "main": [[{"node": prepare_pkl_data["name"], "type": "main", "index": 0}]]
        },
        prepare_pkl_data["name"]: {
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
            pdf_to_text,
            prepare_bill_data,
            extract_containers,
            parse_containers,
            filter_pkl,
            read_xlsx,
            prepare_pkl_data,
            extract_pkl,
            parse_pkl,
            merge_results,
            format_output
        ],
        "connections": connections,
        "pinData": {},
        "settings": {
            "executionOrder": "v1"
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
    
    if OPENROUTER_API_KEY == "YOUR_OPENROUTER_API_KEY_HERE":
        print("⚠️  WARNING: Please set your OpenRouter API key in the script!")
        print("   Edit OPENROUTER_API_KEY variable in generate_workflow.py")
    
    workflow = create_workflow()
    
    output_file = "workflow.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Workflow generated successfully!")
    print(f"   Saved to: {output_file}")
    print(f"   Total nodes: {len(workflow['nodes'])}")
    print("\nNext steps:")
    print("1. Import workflow.json into n8n")
    print("2. Configure Gmail OAuth2 credentials")
    print("3. Set OpenRouter API key in the HTTP Request nodes")
    print("4. Test the workflow with a sample email")

if __name__ == "__main__":
    main()

