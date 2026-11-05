"""Builds the n8n workflow JSON (n8n/royalty-summary-workflow.json).

Kept as a generator so the JavaScript in the Code nodes lives in readable files
(n8n/code/*.js) instead of escaped strings inside JSON.
"""
import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent
CODE = HERE / "code"


def code(name):
    return (CODE / name).read_text()


def node(name, type_, pos, params, version=1, **extra):
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"bookleaf/{name}")),
        "name": name,
        "type": type_,
        "typeVersion": version,
        "position": pos,
        "parameters": params,
        **extra,
    }


respond = lambda name, pos, body_expr, status: node(
    name,
    "n8n-nodes-base.respondToWebhook",
    pos,
    {
        "respondWith": "json",
        "responseBody": body_expr,
        "options": {"responseCode": status},
    },
    version=1.1,
)

nodes = [
    node(
        "Webhook (from Bubble)",
        "n8n-nodes-base.webhook",
        [0, 300],
        {
            "httpMethod": "POST",
            "path": "royalty-summary",
            "authentication": "headerAuth",
            "responseMode": "responseNode",
            "options": {},
        },
        version=2,
        webhookId="bookleaf-royalty-summary",
        credentials={"httpHeaderAuth": {"id": "", "name": "BookLeaf webhook secret"}},
    ),
    node(
        "Validate & de-duplicate",
        "n8n-nodes-base.code",
        [240, 300],
        {"jsCode": code("validate_and_dedupe.js")},
        version=2,
    ),
    node(
        "Valid request?",
        "n8n-nodes-base.if",
        [480, 300],
        {
            "conditions": {
                "options": {"caseSensitive": True, "typeValidation": "loose"},
                "combinator": "and",
                "conditions": [
                    {
                        "leftValue": "={{ $json.ok }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
            },
            "options": {},
        },
        version=2,
    ),
    respond("Respond: rejected", [720, 520], "={{ { status: 'Failed', error_message: $json.error, completed_at: $now.toISO() } }}", 200),
    node(
        "Compute royalty facts",
        "n8n-nodes-base.code",
        [720, 200],
        {"jsCode": code("compute_facts.js")},
        version=2,
    ),
    node(
        "Claude: write summary email",
        "n8n-nodes-base.httpRequest",
        [960, 200],
        {
            "method": "POST",
            "url": "https://api.anthropic.com/v1/messages",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "anthropic-version", "value": "2023-06-01"},
                    {"name": "content-type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.anthropic_request) }}",
            "options": {"timeout": 60000},
        },
        version=4.2,
        credentials={"httpHeaderAuth": {"id": "", "name": "Anthropic API key"}},
        retryOnFail=True,
        maxTries=3,
        waitBetweenTries=3000,
        onError="continueErrorOutput",
    ),
    node(
        "Parse email",
        "n8n-nodes-base.code",
        [1200, 120],
        {"jsCode": code("parse_email.js")},
        version=2,
    ),
    node(
        "Email usable?",
        "n8n-nodes-base.if",
        [1440, 120],
        {
            "conditions": {
                "options": {"caseSensitive": True, "typeValidation": "loose"},
                "combinator": "and",
                "conditions": [
                    {
                        "leftValue": "={{ $json.ok }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
            },
            "options": {},
        },
        version=2,
    ),
    respond(
        "Respond: success",
        [1680, 40],
        "={{ { status: 'Success', request_id: $json.request_id, email_subject: $json.subject, email_body: $json.body, model: $json.model, completed_at: $now.toISO() } }}",
        200,
    ),
    node(
        "Describe AI failure",
        "n8n-nodes-base.code",
        [1200, 340],
        {"jsCode": code("describe_ai_failure.js")},
        version=2,
    ),
    respond(
        "Respond: failed",
        [1680, 300],
        "={{ { status: 'Failed', request_id: $json.request_id, error_message: $json.error, completed_at: $now.toISO() } }}",
        200,
    ),
]

connections = {
    "Webhook (from Bubble)": {"main": [[{"node": "Validate & de-duplicate", "type": "main", "index": 0}]]},
    "Validate & de-duplicate": {"main": [[{"node": "Valid request?", "type": "main", "index": 0}]]},
    "Valid request?": {
        "main": [
            [{"node": "Compute royalty facts", "type": "main", "index": 0}],
            [{"node": "Respond: rejected", "type": "main", "index": 0}],
        ]
    },
    "Compute royalty facts": {"main": [[{"node": "Claude: write summary email", "type": "main", "index": 0}]]},
    "Claude: write summary email": {
        "main": [
            [{"node": "Parse email", "type": "main", "index": 0}],
            [{"node": "Describe AI failure", "type": "main", "index": 0}],
        ]
    },
    "Parse email": {"main": [[{"node": "Email usable?", "type": "main", "index": 0}]]},
    "Email usable?": {
        "main": [
            [{"node": "Respond: success", "type": "main", "index": 0}],
            [{"node": "Describe AI failure", "type": "main", "index": 0}],
        ]
    },
    "Describe AI failure": {"main": [[{"node": "Respond: failed", "type": "main", "index": 0}]]},
}

workflow = {
    "name": "BookLeaf – AI royalty summary",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
}

out = HERE / "royalty-summary-workflow.json"
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False))
print(f"wrote {out} ({len(nodes)} nodes)")
