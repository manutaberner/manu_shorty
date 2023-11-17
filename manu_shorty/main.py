import validators
from fastapi import Depends, FastAPI, HTTPException, Request, Form
from sqlalchemy.orm import Session
from fastapi.responses import RedirectResponse, HTMLResponse
import crud, models, schemas
from database import SessionLocal, engine
from starlette.datastructures import URL
from config import get_settings
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
models.Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def raise_bad_request(message):
    raise HTTPException(status_code=400, detail=message)

def raise_not_found(request):
    message = f"URL '{request.url}' doesn't exist"
    raise HTTPException(status_code=404, detail=message)

@app.post("/url", response_model=schemas.URLInfo)
def create_url(url: schemas.URLBase, db: Session = Depends(get_db)):
    if not validators.url(url.target_url):
        raise_bad_request(message="Your provided URL is not valid")
    db_url = crud.create_db_url(db=db, url=url)
    return get_admin_info(db_url)

# HTML form handling
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def show_form(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/form", response_class=HTMLResponse, include_in_schema=False)
async def create_url_form(request: Request, url: str = Form(...), db: Session = Depends(get_db)):
    if not validators.url(url):
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error_message": "Your provided URL is not valid"
        })

     # Create a schemas.URLBase object using the provided URL string
    url_base = schemas.URLBase(target_url=url)

    # Process the URL as needed
    db_url = crud.create_db_url(db=db, url=url_base)

    # Construct the shortened URL
    shortened_url = f"{get_settings().base_url}/{db_url.key}"
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "success_message": "URL shortened successfully!",
        "shortened_url": shortened_url  # Pass the shortened URL to the HTML template
    })


@app.get("/{url_key}")
def forward_to_target_url(
        url_key: str,
        request: Request,
        db: Session = Depends(get_db)
    ):
    if db_url := crud.get_db_url_by_key(db=db, url_key=url_key):
        crud.update_db_clicks(db=db, db_url=db_url)
        return RedirectResponse(db_url.target_url)
    else:
        raise_not_found(request)

@app.get(
    "/admin/{secret_key}",
    name="administration info",
    response_model=schemas.URLInfo,
)
def get_url_info(
    secret_key: str, request: Request, db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        return get_admin_info(db_url)
    else:
        raise_not_found(request)

def get_admin_info(db_url: models.URL) -> schemas.URLInfo:
    base_url = URL(get_settings().base_url)
    admin_endpoint = app.url_path_for(
        "administration info", secret_key=db_url.secret_key
    )
    db_url.url = str(base_url.replace(path=db_url.key))
    db_url.admin_url = str(base_url.replace(path=admin_endpoint))
    return db_url

@app.delete("/admin/{secret_key}")
def delete_url(
    secret_key: str, request: Request, db: Session = Depends(get_db)
):
    if db_url := crud.deactivate_db_url_by_secret_key(db, secret_key=secret_key):
        message = f"Successfully deleted shortened URL for '{db_url.target_url}'"
        return {"detail": message}
    else:
        raise_not_found(request)