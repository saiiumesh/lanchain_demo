"""
LangGraph Azure DataOps Agent (GPT-4.0 Intent Driven)
------------------------------------------------------
This AI agent uses GPT-4.0 (Azure OpenAI) to classify user intents dynamically.
It can:
1. Check for new files in Azure Blob / ADLS Gen2
2. Trigger Azure Data Factory ETL pipeline when asked
3. Check status of the latest pipeline run
4. Detect if files are unchanged since the last check
"""

# ================================================================
# STEP 0: SSL Fix for Python on Windows (only needed locally)
# ================================================================
import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()

import json
import requests
from typing import TypedDict
from datetime import datetime, timezone, timedelta
from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient
from langgraph.graph import StateGraph, END
from openai import AzureOpenAI  # <-- Azure OpenAI client

# ================================================================
# STEP 1: AZURE CONFIGURATION - credentials and resource names
# ================================================================
TENANT_ID = "84fb2f67-688c-4c94-ba8b-b678a58d4857"
CLIENT_ID = "3731420b-a071-4869-98be-05293d9bd43c"
CLIENT_SECRET = "Awg8Q~Fo6FHfFXXkI5qo-~Ca_QJpli1-6qoTdbT5"

SUBSCRIPTION_ID = "48594b89-7eba-4cb8-9135-8182a22be6b9"
RESOURCE_GROUP = "RG-NetflixProject"
ADF_NAME = "adf-netflixproject-umesh"
PIPELINE_NAME = "pl_copy_files"

STORAGE_ACCOUNT_URL = "https://pocsstorageaccountofmine.blob.core.windows.net"
CONTAINER_NAME = "raw-data"
PROCESSED_CONTAINER_NAME = "processed-data"

# ================================================================
# STEP 2: READ AZURE OPENAI CONFIG FROM ENV (backend sets these)
# ================================================================
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")  # default deployment name

if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_VERSION:
    raise ValueError("Azure OpenAI configuration missing in environment variables.")

# ================================================================
# STEP 3: AUTHENTICATION & CLIENT SETUP
# ================================================================
credential = ClientSecretCredential(
    tenant_id=TENANT_ID,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET
)

blob_service_client = BlobServiceClient(
    account_url=STORAGE_ACCOUNT_URL,
    credential=credential
)

gpt_client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

# ================================================================
# STEP 4: STATE SCHEMA FOR LANGGRAPH
# ================================================================
class AgentState(TypedDict):
    input: str
    intent: str
    output: str

graph = StateGraph(AgentState)

latest_run_id = {"run_id": None}
last_blob_state = {"files": {}, "last_check": None}  # Use dict for filename->datetime

# ================================================================
# STEP 5: HELPER FUNCTIONS
# ================================================================
def get_bearer_token():
    return credential.get_token("https://management.azure.com/.default").token

def list_blob_files_with_dates():
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)
    blobs = container_client.list_blobs()
    # Return dict of filename -> last_modified datetime (UTC)
    return {b.name: b.last_modified for b in blobs}

def list_processed_files():
    container_client = blob_service_client.get_container_client(PROCESSED_CONTAINER_NAME)
    blobs = container_client.list_blobs()
    return [b.name for b in blobs]

def trigger_adf_pipeline():
    token = get_bearer_token()
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.DataFactory/factories/{ADF_NAME}/pipelines/{PIPELINE_NAME}/createRun"
        f"?api-version=2018-06-01"
    )
    response = requests.post(url, headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.json().get("runId", "N/A")

def get_pipeline_status(run_id):
    token = get_bearer_token()
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.DataFactory/factories/{ADF_NAME}/pipelineruns/{run_id}"
        f"?api-version=2018-06-01"
    )
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.json().get("status", "Unknown")

# ================================================================
# STEP 6: GPT-4.0 (Azure) POWERED INTENT CLASSIFICATION
# ================================================================
def classify_intent(state: AgentState) -> AgentState:
    user_input = state["input"]

    prompt = f"""
You are an intent classification system for an Azure DataOps agent.
Possible intents: "greet", "check_data", "trigger_etl", "check_status", "unknown".
Read the user input and output a JSON object with exactly two fields:
- intent: one of the above intents
- message: a friendly, short response to the user if appropriate.

User input: "{user_input}"
Output JSON:
"""

    try:
        completion = gpt_client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw_output = completion.choices[0].message.content.strip()
        parsed = json.loads(raw_output)

        state["intent"] = parsed.get("intent", "unknown")
        state["output"] = parsed.get("message", "")

    except Exception as e:
        state["intent"] = "unknown"
        state["output"] = f"Intent classification error: {str(e)}"

    return state

# ================================================================
# STEP 7: NODE FUNCTIONS
# ================================================================
# IST timezone offset from UTC is +5:30
IST_OFFSET = timedelta(hours=5, minutes=30)

def check_blob(state: AgentState) -> AgentState:
    global last_blob_state
    current_files = list_blob_files_with_dates()

    if not last_blob_state["files"]:
        last_blob_state["files"] = current_files
        last_blob_state["last_check"] = datetime.now(timezone.utc)
        state["output"] = f"Found {len(current_files)} files: {list(current_files.keys())}"
        return state

    old_files_set = set(last_blob_state["files"].keys())
    current_files_set = set(current_files.keys())

    new_files = current_files_set - old_files_set

    if not new_files:
        state["output"] = (
            "No new files detected since last check. "
            f"Last check was at {last_blob_state['last_check'].astimezone().strftime('%Y-%m-%d %H:%M:%S')}."
        )
    else:
        last_blob_state["files"] = current_files
        last_blob_state["last_check"] = datetime.now(timezone.utc)
        state["output"] = f"New files detected: {list(new_files)}"

    return state

def trigger_pipeline(state: AgentState) -> AgentState:
    global last_blob_state, latest_run_id

    current_files = list_blob_files_with_dates()
    old_files = last_blob_state["files"]

    new_files = {}
    for fname, fdate_utc in current_files.items():
        old_date = old_files.get(fname)
        # Consider new if file is not seen before or last_modified is newer
        if not old_date or fdate_utc > old_date:
            new_files[fname] = fdate_utc

    # Get today's date in IST
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + IST_OFFSET
    today_ist = now_ist.date()

    # Filter files with last_modified date in IST == today_ist
    new_today_files = []
    for fname, fdate_utc in new_files.items():
        file_ist_date = (fdate_utc + IST_OFFSET).date()
        if file_ist_date == today_ist:
            new_today_files.append(fname)

    if not new_today_files:
        state["output"] = (
            f"No new data files with today's date ({today_ist}) in IST detected in raw data container. "
            "Pipeline not triggered."
        )
        return state

    run_id = trigger_adf_pipeline()
    latest_run_id["run_id"] = run_id
    state["output"] = f"Pipeline '{PIPELINE_NAME}' triggered successfully! RunId: {run_id}"

    last_blob_state["files"] = current_files
    last_blob_state["last_check"] = now_utc

    return state

def check_pipeline_status(state: AgentState) -> AgentState:
    run_id = latest_run_id.get("run_id")
    if not run_id:
        state["output"] = "No pipeline run tracked yet. Please trigger ETL first."
    else:
        status = get_pipeline_status(run_id)
        response = f"Latest pipeline RunId {run_id} is currently: {status}"

        if status.lower() == "succeeded":
            processed_files = list_processed_files()
            if processed_files:
                response += f"\nFiles copied to '{PROCESSED_CONTAINER_NAME}': {processed_files}"
            else:
                response += f"\nPipeline completed but no files found in '{PROCESSED_CONTAINER_NAME}'."
        state["output"] = response
    return state

# ================================================================
# STEP 8: GRAPH ROUTING LOGIC
# ================================================================
def route_from_classifier(state: AgentState) -> str:
    intent = state["intent"]
    if intent == "check_data":
        return "check_data"
    elif intent == "trigger_etl":
        return "trigger_etl"
    elif intent == "check_status":
        return "check_status"
    elif intent == "greet":
        return END
    else:
        return END

graph.add_node("classifier", classify_intent)
graph.add_node("check_data", check_blob)
graph.add_node("trigger_etl", trigger_pipeline)
graph.add_node("check_status", check_pipeline_status)

graph.add_conditional_edges("classifier", route_from_classifier)
graph.add_edge("check_data", END)
graph.add_edge("trigger_etl", END)
graph.add_edge("check_status", END)

graph.set_entry_point("classifier")
app = graph.compile()

# ================================================================
# STEP 9: INTERACTIVE CLI LOOP
# ================================================================
hour = datetime.now().hour
greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

print(f"Hi Umesh, {greeting}! Azure DataOps Agent is ready. Type 'exit' to quit.\n")

while True:
    user_query = input("You: ").strip()
    if user_query.lower() in ["exit", "quit", "bye"]:
        print("Agent: Goodbye!")
        break

    response = app.invoke({"input": user_query, "intent": "", "output": ""})
    print(f"Agent: {response['output']}\n{'-'*60}")
