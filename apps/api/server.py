import uvicorn
import os
import ipaddress

from whitebox.main import app


if __name__ == "__main__":
    host = os.getenv("WHITEBOX_API_HOST", "127.0.0.1")
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() == "localhost"
    if not loopback:
        raise SystemExit("Whitebox API 尚无网络认证，拒绝监听非回环地址")
    uvicorn.run(app, host=host, port=int(os.getenv("WHITEBOX_API_PORT", "8001")), log_level="info")
