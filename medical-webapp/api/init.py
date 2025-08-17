import azure.functions as func
from fastapi import FastAPI
from mangum import Mangum  # optional adapter if using ASGI

app = FastAPI()

@app.get("/hello")
def read_root():
    return {"message": "Hello from FastAPI Function!"}

# Azure Functions handler
def main(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    from fastapi.responses import JSONResponse
    # Basic FastAPI route handling
    path = req.route_params.get('path', '')
    if path == "hello":
        return JSONResponse({"message": "Hello from FastAPI Function!"})
    return JSONResponse({"error": "Not found"}, status_code=404)
