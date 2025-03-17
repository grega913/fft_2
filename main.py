
# region Imports

from typing import Union
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uvicorn
import time
import os

#templates
from fastapi import FastAPI, Request, WebSocket, Depends, APIRouter, HTTPException, Body, status, Response, Path
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import escape

from icecream import ic

import firebase_admin
from firebase_admin import credentials, firestore, auth

from uuid import UUID, uuid4
from helperz import cookie, backend, verifier, SessionData, ModelName, Item

import stripe


from dotenv import load_dotenv
load_dotenv()

YOUR_DOMAIN = 'http://localhost:8000'

# Stripe settings
stripe_keys = {
    "secret_key": os.environ["STRIPE_SECRET_KEY"],
    "publishable_key": os.environ["STRIPE_PUBLISHABLE_KEY"],
    "endpoint_secret": os.environ["STRIPE_ENDPOINT_SECRET"]
}

ic(stripe_keys["secret_key"])

stripe.api_key = stripe_keys["secret_key"]

# endregion


# region Lifespan
# https://fastapi.tiangolo.com/advanced/events/#lifespan

def fake_answer_to_everything_ml_model(x: float):
    return x * 42


ml_models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the ML model
    ic("def lifespan")
    ml_models["answer_to_everything"] = fake_answer_to_everything_ml_model

    # Firebase Admin SDK setup
    cred = credentials.Certificate("firebase_auth.json")
    firebase_admin.initialize_app(cred)

    ic("after firebase initialization")

    ic(ml_models)
    yield
    # Clean up the ML models and release the resources
    ic("before mlmodels clean")
    ml_models.clear()


# endregion


# region App settings
app = FastAPI(lifespan=lifespan)


# mapping static file
app.mount("/static", StaticFiles(directory="static"), name="static") 
templates = Jinja2Templates(directory="static/templates/")

# endregion


# region Routes



@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")

@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html")

@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request):
    return templates.TemplateResponse(request=request, name="signup.html")
    
@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse(request=request, name="terms.html")

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse(request=request, name="privacy.html")

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse(request=request, name="about.html")

@app.get("/reset_password")
async def reset_password():
    return "OK"

# Define the dashboard route with the verifier and cookie dependencies
@app.get("/dashboard", dependencies=[Depends(cookie)], response_class=HTMLResponse)
async def dashboard(request: Request, session_data: SessionData = Depends(verifier)):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"session_data": session_data})

@app.api_route("/auth", methods=["POST", "GET"])
async def authorize(request: Request):
    ic(("def authorize"))

    if request.method == "GET":
        return JSONResponse(content={"status": "auth endpoint"}, status_code=200)
        
    token = request.headers.get('Authorization')
    ic(token)
    if not token or not token.startswith('Bearer '):
        ic("unauthorized cause we do not have token")
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = token[7:]  # Strip off 'Bearer ' to get the actual token
    ic(token)
    ic("before try")
    try:
        decoded_token = auth.verify_id_token(token, check_revoked=True, clock_skew_seconds=60)
        user_id = decoded_token['uid']  # Get user ID from decoded token
        ic(decoded_token)
        ic(user_id)
        
        # Create session and response
        response = JSONResponse(content={"message": "Authorized"}, status_code=200)
        await create_session(user_id, response)
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Unauthorized: {str(e)}")

# endregion


# region Websockets


@app.get("/test_websocket", response_class=HTMLResponse)
async def test_websocket(request: Request):
    return templates.TemplateResponse(request=request, name="test_websocket.html")



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")



# endregion


# region Routes - other

@app.get("/predict")
async def predict(x: float):
    result = ml_models["answer_to_everything"](x)
    return {"result": result}



@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}




@app.get("/models/{model_name}")
async def get_model(model_name: ModelName):
    if model_name is ModelName.alexnet:
        return {"model_name": model_name, "message": "Deep Learning FTW!"}

    if model_name.value == "lenet":
        return {"model_name": model_name, "message": "LeCNN all the images"}

    return {"model_name": model_name, "message": "Have some residuals"}



@app.post("/items/")
async def create_item(item: Item):
    return item

# endregion


# region Routes Session

    
@app.post("/create_session/{name}")
async def create_session(name: str, response: Response):

    ic("def create_session")

    session = uuid4()
    data = SessionData(usr=name)

    await backend.create(session, data)
    cookie.attach_to_response(response, session)

    return f"created session for {name}"


@app.get("/whoami", dependencies=[Depends(cookie)])
async def whoami(session_data: SessionData = Depends(verifier)):
    return session_data


@app.post("/delete_session")
async def del_session(response: Response, session_id: UUID = Depends(cookie)):
    await backend.delete(session_id)
    cookie.delete_from_response(response)
    return "deleted session for session_id" + str(session_id)



@app.get("/logout")
async def logout(response: Response, session_id: UUID = Depends(cookie)):
    ic("def logout")
    ic(session_id)

    # Check if the session_id is valid
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id")

    await backend.delete(session_id)

    # Remove the session cookie
    cookie.delete_from_response(response)

    # Redirect to home page
    return Response(status_code=status.HTTP_302_FOUND, headers={"Location": "/home"})


# endregion


# region Stripe

@app.get("/stripe123", response_class=HTMLResponse)
async def stripe123(request: Request):
    return templates.TemplateResponse(request=request, name="stripe123.html")

@app.get("/stripe_success", response_class=HTMLResponse)
async def stripe_success(request: Request):
    return templates.TemplateResponse(request=request, name="stripe_success.html")


@app.get("/stripe_cancelled", response_class=HTMLResponse)
async def stripe_cancelled(request: Request):
    return templates.TemplateResponse(request=request, name="stripe_cancelled.html")

@app.get("/stripe_checkout", response_class=HTMLResponse)
async def stripe_checkout(request: Request):
    return templates.TemplateResponse(request=request, name="stripe_checkout.html")

@app.get("/stripe_checkout2", response_class=HTMLResponse)
async def stripe_checkout2(request: Request):
    return templates.TemplateResponse(request=request, name="stripe_checkout2.html")

@app.get("/stripe_config")
def get_publishable_key():
    stripe_config = {"publicKey": stripe_keys["publishable_key"]}
    return JSONResponse(stripe_config)



@app.post('/create-checkout-session')
def create_checkout_session():

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    # Provide the exact Price ID (for example, pr_1234) of the product you want to sell
                    'price': 'price_1R17DJB4j30g5cZMjWNlbREF',
                    'quantity': 1,
                },
            ],
            mode='payment',
            success_url=YOUR_DOMAIN + '/stripe_success',
            cancel_url=YOUR_DOMAIN + '/stripe_cancel'
        )

        ic(checkout_session)

        return JSONResponse({"sessionId": checkout_session.id})

        

    except Exception as e:
        return str(e)


# endregion












if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)

