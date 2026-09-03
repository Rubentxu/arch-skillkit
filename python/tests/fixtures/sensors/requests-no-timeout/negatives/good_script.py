"""Fixture: requests.get WITH timeout — SHOULD NOT MATCH (negative fixture)."""
import requests

url = "https://httpbin.org/get"
result = requests.get(url, timeout=10)
print(result.status_code)
