# Rate-limit resilient API caller with adaptive wait
def call_gemini_safe(client, model, contents, system_instruction=""):
    # Fallback to gemini-2.0-flash if 3.6 hits quotas
    target_model = "gemini-2.0-flash" if "3.6" in model else model
    
    for attempt in range(5):
        try:
            config = {"temperature": 0.2}
            if system_instruction:
                config["system_instruction"] = system_instruction
            resp = client.models.generate_content(
                model=target_model,
                contents=contents,
                config=config
            )
            return resp.text, None
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                # Wait progressively longer: 4s, 8s, 12s, 16s
                wait_sec = 4 * (attempt + 1)
                time.sleep(wait_sec)
                continue
            return None, err_str
            
    return None, "Google free tier limit is full. Please wait ~30 seconds before your next question."
