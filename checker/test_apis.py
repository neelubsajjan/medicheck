import requests
import urllib.parse

def test_models():
    prompt = "What is nephrotic syndrome? Answer in 1 short sentence."
    models = ["openai", "mistral", "llama", "sur", "qwen"]
    for m in models:
        try:
            url = f"https://text.pollinations.ai/{urllib.parse.quote(prompt)}?model={m}"
            res = requests.get(url, timeout=15)
            print(f"Model {m} - GET Status:", res.status_code)
            if res.status_code == 200:
                print(f"Model {m} - GET Response:", res.text[:150].encode('utf-8'))
            else:
                print(f"Model {m} - GET Error:", res.text[:150].encode('utf-8'))
        except Exception as e:
            print(f"Model {m} - Exception:", e)

if __name__ == '__main__':
    test_models()
