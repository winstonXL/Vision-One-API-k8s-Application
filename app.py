from flask import Flask, jsonify, render_template, request
import requests
import json
import boto3
import os
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

URL_BASE        = 'https://api.xdr.trendmicro.com'
URL_PATH        = '/v3.0/workbench/alerts'
URL_PATH_MODELS = '/v3.0/dmm/models'

# ── Secrets are injected as environment variables from k8s secret ──
TOKEN_ALERTS          = os.environ.get('TOKEN_ALERTS').strip()
TOKEN_MODELS          = os.environ.get('TOKEN_MODELS').strip()
AWS_ACCESS_KEY_ID     = os.environ.get('AWS_ACCESS_KEY_ID').strip()
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY').strip()
AWS_REGION            = os.environ.get('AWS_REGION', 'us-east-1').strip()
BEDROCK_MODEL_ID      = 'amazon.nova-lite-v1:0'


def get_date_range():
    now   = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    return (
        start.strftime('%Y-%m-%dT%H:%M:%SZ'),
        now.strftime('%Y-%m-%dT%H:%M:%SZ')
    )


def get_bedrock_client():
    return boto3.client(
        service_name          = 'bedrock-runtime',
        region_name           = AWS_REGION,
        aws_access_key_id     = AWS_ACCESS_KEY_ID,
        aws_secret_access_key = AWS_SECRET_ACCESS_KEY
    )


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/alerts')
def get_alerts():
    start_dt, end_dt = get_date_range()

    query_params = {
        'startDateTime': start_dt,
        'endDateTime':   end_dt,
        'orderBy':       'severity desc'
    }
    headers = {
        'Authorization': 'Bearer ' + TOKEN_ALERTS,
        'TMV1-Filter':   "investigationStatus eq 'New'"
    }

    try:
        r = requests.get(URL_BASE + URL_PATH, params=query_params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json() if 'application/json' in r.headers.get('Content-Type', '') else {}
        return jsonify({
            'success':       True,
            'data':          data,
            'startDateTime': start_dt,
            'endDateTime':   end_dt,
            'refreshedAt':   datetime.now(timezone.utc).strftime('%b %d, %Y · %H:%M UTC')
        })
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/models')
def get_models():
    now = datetime.now(timezone.utc)

    query_params = {
        'startDateTime': '1970-01-01T00:00:00Z',
        'endDateTime':   now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'orderBy':       'riskLevel asc',
        'filter':        "riskLevel eq 'Critical'"
    }
    headers = {
        'Authorization': 'Bearer ' + TOKEN_MODELS
    }

    try:
        r = requests.get(URL_BASE + URL_PATH_MODELS, params=query_params, headers=headers, timeout=15)
        r.raise_for_status()
        data  = r.json() if 'application/json' in r.headers.get('Content-Type', '') else {}
        items = data.get('items', [])[:10]
        return jsonify({'success': True, 'models': items})
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/summarize', methods=['POST'])
def summarize_alert():
    alert = request.get_json()
    if not alert:
        return jsonify({'success': False, 'error': 'No alert data provided'}), 400

    alert_id   = alert.get('id', 'Unknown')
    model_name = alert.get('model', 'Unknown')
    severity   = alert.get('severity', 'Unknown')
    score      = alert.get('score', 'N/A')
    created    = alert.get('createdDateTime', 'Unknown')
    status     = alert.get('investigationStatus', 'Unknown')

    entities = [
        e.get('entityValue', '')
        for e in alert.get('impactScope', {}).get('entities', [])
    ]
    indicators = [
        f"{i.get('field', '')}: {i.get('value', '')}"
        for i in alert.get('indicators', [])
    ]
    rules = [
        f.get('name', '')
        for r in alert.get('matchedRules', [])
        for f in r.get('matchedFilters', [])
    ]

    prompt = f"""You are a cybersecurity analyst assistant reviewing a Trend Micro Vision One workbench alert.

Alert details:
- ID: {alert_id}
- Detection model: {model_name}
- Severity: {severity} (score: {score})
- Created: {created}
- Investigation status: {status}
- Affected entities: {', '.join(entities) or 'None'}
- Indicators: {', '.join(indicators) or 'None'}
- Matched filters: {', '.join(rules) or 'None'}

Please provide a concise security summary covering:
1. What likely happened (2-3 sentences)
2. Why it is concerning
3. Recommended immediate actions (2-3 bullet points)

Keep the tone professional and actionable. Do not repeat the raw field values verbatim."""

    try:
        client = get_bedrock_client()
        body   = json.dumps({
            "messages": [
                {"role": "user", "content": [{"text": prompt}]}
            ],
            "inferenceConfig": {
                "maxTokens": 512,
                "temperature": 0.4
            }
        })

        response = client.invoke_model(
            modelId     = BEDROCK_MODEL_ID,
            contentType = 'application/json',
            accept      = 'application/json',
            body        = body
        )

        result  = json.loads(response['body'].read())
        summary = result['output']['message']['content'][0]['text']
        return jsonify({'success': True, 'summary': summary})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
