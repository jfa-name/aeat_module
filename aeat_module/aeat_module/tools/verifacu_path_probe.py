#!/usr/bin/env python3
"""
Probe script to find the correct VERI*FACTU endpoint path.
Usage: python tools/verifactu_path_probe.py --base https://prewww1.aeat.es \
    --cert /path/cert.pem --key /path/key.pem --ca /path/ca.pem
"""
import argparse, requests, json, sys

CANDIDATES = [
    "/api/verifactu/v1/emitidas",
    "/verifactu/v1/emitidas",
    "/api/verifactu/emitidas",
    "/verifactu/emitidas",
    "/api/v1/emitidas",
    "/api/emitidas",
    "/api/verifactu/v1/registro/emitidas",
    "/api/sii/verifactu/emitidas",
    "/verifactu/api/v1/emitidas",
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--cert", default=None)
    p.add_argument("--key", default=None)
    p.add_argument("--ca", default=None)
    p.add_argument("--method", default="POST")
    p.add_argument("--payload", default='{}')
    args = p.parse_args()

    s = requests.Session()
    if args.cert and args.key:
        s.cert = (args.cert, args.key)
    verify = args.ca if args.ca else True
    headers = {"Content-Type": "application/json"}

    for path in CANDIDATES:
        url = args.base.rstrip("/") + "/" + path.lstrip("/")
        try:
            print("="*80)
            print("Trying:", url)
            if args.method.upper() == "GET":
                r = s.get(url, timeout=15, verify=verify)
            else:
                r = s.post(url, data=args.payload.encode("utf-8"), headers=headers, timeout=15, verify=verify)
            print("Status:", r.status_code)
            print("Response headers:", {k:v for k,v in r.headers.items() if k.lower() in ("content-type","www-authenticate")})
            body = r.text.strip()
            print("Body (first 1000 chars):")
            print(body[:1000])
        except Exception as e:
            print("Error:", type(e).__name__, str(e))

if __name__ == "__main__":
    main()
