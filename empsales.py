import os
import time
import json
from datetime import datetime, timezone, timedelta
from azure.identity import ClientSecretCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI

# ----------------------
# Azure & OpenAI config
# ----------------------
TENANT_ID = "84fb2f67-688c-4c94-ba8b-b678a58d4857"
CLIENT_ID = "3731420b-a071-4869-98be-05293d9bd43c"
CLIENT_SECRET = "Awg8Q~Fo6FHfFXXkI5qo-~Ca_QJpli1-6qoTdbT5"

SUBSCRIPTION_ID = "48594b89-7eba-4cb8-9135-8182a22be6b9"
RESOURCE_GROUP = "RG-NetflixProject"
ADF_NAME = "adf-netflixproject-umesh"

PIPELINES = {
    "employee": "pl_dynamic",
    "sales": "pl_dynamic"
}

STORAGE_ACCOUNT_URL = "https://pocsstorageaccountofmine.blob.core.windows.net"
RAW_CONTAINER_NAME = "raw-data"
PROCESSED_CONTAINER_NAME = "processed-data"

AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")

# ----------------------
# Setup clients
# ----------------------
credential = ClientSecretCredential(
    tenant_id=TENANT_ID,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
)

adf_client = DataFactoryManagementClient(credential, SUBSCRIPTION_ID)
blob_service_client = BlobServiceClient(account_url=STORAGE_ACCOUNT_URL, credential=credential)
openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

# ----------------------
# Helper Functions
# ----------------------
def classify_intent(user_text):
    prompt = f"""
You are an intent classifier for an Azure DataOps assistant.
User input: "{user_text}"
Possible intents: greet, trigger_etl, check_status, check_latest_files, last_success, exit, unknown.
Return JSON with fields:
- intent: one of above intents
- message: optional reply message to user
"""
    response = openai_client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    content = response.choices[0].message.content.strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        result = {"intent": "unknown", "message": "Sorry, I didn't understand that."}
    return result

def list_new_files():
    container_client = blob_service_client.get_container_client(RAW_CONTAINER_NAME)
    blobs = container_client.list_blobs()
    now_utc = datetime.now(timezone.utc)
    threshold = now_utc - timedelta(hours=24)
    new_files = []
    for blob in blobs:
        if blob.last_modified and blob.last_modified >= threshold:
            new_files.append(blob.name)
    return new_files

def get_last_successful_run(pipeline_name):
    runs = adf_client.pipeline_runs.query_by_factory(
        RESOURCE_GROUP,
        ADF_NAME,
        filter_parameters={
            "lastUpdatedAfter": datetime(2000, 1, 1),
            "lastUpdatedBefore": datetime.now(timezone.utc)
        }
    )
    succeeded_runs = [r for r in runs.value if r.pipeline_name == pipeline_name and r.status.lower() == "succeeded"]
    if not succeeded_runs:
        return None
    succeeded_runs.sort(key=lambda r: r.run_start, reverse=True)
    return succeeded_runs[0]

def check_pipeline_status(run_id):
    status = adf_client.pipeline_runs.get(RESOURCE_GROUP, ADF_NAME, run_id)
    start = status.run_start or "Unknown"
    end = status.run_end or "Running"
    elapsed = (status.run_end - status.run_start).total_seconds() if status.run_end and status.run_start else None
    return {
        "status": status.status,
        "start_time": start,
        "end_time": end,
        "elapsed_seconds": elapsed
    }

def trigger_pipeline(name, business_unit):
    print(f"Triggering pipeline '{name}' with business_unit parameter '{business_unit}' ...")
    run = adf_client.pipelines.create_run(
        RESOURCE_GROUP,
        ADF_NAME,
        name,
        parameters={"business_unit": business_unit}  # Pass business_unit only; pipeline resolves paths internally
    )
    print(f"RunId: {run.run_id}")
    return run.run_id

def detect_business_unit(text):
    units = PIPELINES.keys()
    text_lower = text.lower()
    for unit in units:
        if unit in text_lower:
            return unit
    return None

# ----------------------
# Main interactive loop
# ----------------------
def main():
    print("Azure DataOps Agent (type 'exit' to quit)\n")

    awaiting_pipeline_choice = False

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in ("exit", "quit", "bye"):
            print("Agent: Goodbye!")
            break

        # Detect business unit from input if possible
        detected_unit = detect_business_unit(user_input)

        if detected_unit:
            run_id = trigger_pipeline(PIPELINES[detected_unit], detected_unit)
            print(f"Agent: Detected business unit '{detected_unit}'. Pipeline triggered. RunId: {run_id}")
            continue

        if awaiting_pipeline_choice:
            choice = user_input.lower()
            if choice in PIPELINES:
                run_id = trigger_pipeline(PIPELINES[choice], choice)
                print(f"Agent: Pipeline triggered. RunId: {run_id}")
            else:
                print(f"Agent: Invalid pipeline '{choice}'. Please type 'employee' or 'sales'.")
                continue
            awaiting_pipeline_choice = False
            continue

        intent_resp = classify_intent(user_input)
        intent = intent_resp.get("intent", "unknown")
        message = intent_resp.get("message", "")

        if intent == "greet":
            print(f"Agent: {message or 'Hello! How can I assist you?'}")

        elif intent == "trigger_etl":
            print("Agent: Which ETL pipeline do you want to trigger? Options: employee, sales")
            awaiting_pipeline_choice = True

        elif intent == "check_latest_files":
            new_files = list_new_files()
            if new_files:
                print(f"Agent: New files detected in last 24 hours: {new_files}")
            else:
                print("Agent: No new files detected in the last 24 hours.")

        elif intent == "last_success":
            for key, pipeline_name in PIPELINES.items():
                run = get_last_successful_run(pipeline_name)
                if run:
                    print(f"Agent: Last successful run of pipeline '{key}' was at {run.run_start} UTC.")
                else:
                    print(f"Agent: No successful runs found yet for pipeline '{key}'.")

        elif intent == "check_status":
            print("Agent: Please provide the RunId to check status:")
            run_id = input("RunId: ").strip()
            if run_id:
                status = check_pipeline_status(run_id)
                print(f"Agent: Status: {status['status']}")
                print(f"Start Time: {status['start_time']}")
                print(f"End Time: {status['end_time']}")
                if status['elapsed_seconds']:
                    print(f"Elapsed Time (seconds): {status['elapsed_seconds']:.1f}")
            else:
                print("Agent: No RunId provided.")

        else:
            print(f"Agent: {message or 'Sorry, I did not understand. Please try again.'}")

if __name__ == "__main__":
    main()
