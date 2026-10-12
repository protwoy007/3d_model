import os, shutil, uuid
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from PIL import Image

# MODE=local -> TripoSR on your NVIDIA GPU | MODE=hf -> free Hugging Face Space
MODE = os.environ.get("MODE", "hf").lower()

os.makedirs("outputs", exist_ok=True)
os.makedirs("static", exist_ok=True)

if MODE == "local":
    from local_triposr import generate as local_generate
else:
    from gradio_client import Client, handle_file
    client = Client("stabilityai/stable-fast-3d", token=os.environ.get("HF_TOKEN"))

app = FastAPI()


@app.get("/config")
def config():
    return {"mode": MODE}


@app.post("/convert")
def convert(file: UploadFile):
    name = uuid.uuid4().hex
    raw_path = f"outputs/{name}_raw"
    img_path = f"outputs/{name}.png"
    glb_path = f"outputs/{name}.glb"

    with open(raw_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        Image.open(raw_path).convert("RGBA").save(img_path)
    except Exception:
        raise HTTPException(status_code=400, detail="That file is not a valid image.")
    finally:
        os.remove(raw_path)

    try:
        if MODE == "local":
            local_generate(img_path, glb_path)
        else:
            _, model_path = client.predict(
                input_image=handle_file(img_path),
                foreground_ratio=0.85,
                remesh_option="None",
                vertex_count=-1,
                texture_size=1024,
                api_name="/run_button",
            )
            shutil.copy(model_path, glb_path)
    except Exception as e:
        print("GENERATION ERROR:", repr(e))
        raise HTTPException(status_code=502, detail=str(e))

    return {"model_url": f"/outputs/{name}.glb"}


app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
