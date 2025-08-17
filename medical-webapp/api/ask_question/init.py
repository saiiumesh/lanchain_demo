import logging
import os
import json
import azure.functions as func
import openai
from azure.storage.blob import BlobServiceClient
import re
import datetime

# --- Load env vars ---
openai.api_type = "azure"
openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_base = os.getenv("OPENAI_API_BASE")
openai.api_version = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
deployment_name = os.getenv("OPENAI_DEPLOYMENT")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "reports"

# --- Connect to Blob and load all reports ---
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)
blobs = list(container_client.list_blobs())

reports = {}
for blob in blobs:
    blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob.name)
    text = blob_client.download_blob().readall().decode("utf-8")
    match = re.search(r'Patient Name:\s*(.*)', text)
    patient_name = match.group(1).strip() if match else blob.name
    reports[patient_name] = text

# --- Azure Function handler ---
def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        patient_name = req_body.get("patient_name")
        question = req_body.get("question")
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    if patient_name not in reports:
        return func.HttpResponse(
            json.dumps({"error": f"Patient '{patient_name}' not found"}),
            status_code=404,
            mimetype="application/json"
        )

    report_text = reports[patient_name]

    # --- Dynamic greeting ---
    now = datetime.datetime.now()
    hour = now.hour
    day_of_week = now.strftime("%A")
    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
    elif 17 <= hour < 21:
        greeting = "Good evening"
    else:
        greeting = "Hello"
    current_time = now.strftime("%I:%M %p")

    # --- Ask Azure OpenAI ---
    try:
        response = openai.ChatCompletion.create(
            engine=deployment_name,
            messages=[
                {"role": "system", "content": "You are a medical assistant AI. Answer strictly based on the report."},
                {"role": "user", "content": f"Report:\n{report_text}\n\nQuestion: {question}"}
            ]
        )
        answer = response.choices[0].message['content']
    except Exception as e:
        logging.error(f"OpenAI Error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

    return func.HttpResponse(
        json.dumps({
            "greeting": f"{greeting}! It's {current_time} on {day_of_week}.",
            "report": report_text,
            "question": question,
            "answer": answer
        }),
        status_code=200,
        mimetype="application/json"
    )