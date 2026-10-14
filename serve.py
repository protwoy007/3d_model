"""Starts img23d.

  * the app for this PC:       http://127.0.0.1:8000   (only this computer can open it)
  * the phone capture page:    https://<this PC's address>:8443   (needs HTTPS for the camera and sensors)

Only the phone capture routes are reachable from the network. Set PORT, HTTPS_PORT or
CAPTURE_HOST (the address your phone should use) to change the defaults.
"""
import os
import socket
import threading
import time

import uvicorn

import capture


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no traffic is sent; this only picks the network adapter
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start_phone_listener(host, port):
    try:
        import segno  # noqa: F401
        import certs

        crt, key = certs.ensure_cert(host)
    except Exception as e:  # noqa: BLE001
        capture.configure(host, port, False, f"Live capture needs extra packages ({e}). Run the launcher again to install them.")
        return
    cfg = uvicorn.Config(capture.capture_app, host="0.0.0.0", port=port, ssl_certfile=crt, ssl_keyfile=key, log_level="warning")
    server = uvicorn.Server(cfg)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(80):
        if server.started or not t.is_alive():
            break
        time.sleep(0.1)
    if server.started:
        capture.configure(host, port, True)
        print(f"Phone capture is ready at https://{host}:{port}")
    else:
        capture.configure(host, port, False, f"The phone capture port {port} could not be opened. Is it already in use?")


def main():
    port = int(os.environ.get("PORT", "8000"))
    https_port = int(os.environ.get("HTTPS_PORT", "8443"))
    host = os.environ.get("CAPTURE_HOST") or lan_ip()
    start_phone_listener(host, https_port)
    from main import app

    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
