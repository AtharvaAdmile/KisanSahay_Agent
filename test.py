import requests, os

api_key = "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"
invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"

headers = {
  "Authorization": f"Bearer {api_key}",
  "Accept": "application/json"
}

payload = {
  "model": "nvidia/nemotron-nano-12b-v2-vl",
  "messages": [
    {"role": "system", "content": "/think"},
    {"role": "user", "content": [{"type": "text", "text": "hello there"}]}
  ],
  "max_tokens": 1024,
  "temperature": 1.00,
  "top_p": 1.00
}

response = requests.post(invoke_url, headers=headers, json=payload)
print(response.json())

