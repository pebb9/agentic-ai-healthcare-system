import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from threading import Lock

MEDGEMMA_MODEL = "google/medgemma-27b-text-it"

_tokenizer = None
_model = None
_lock = Lock()

def _load_model():
    """Load processor and model into GPU memory"""
    global _tokenizer, _model

    with _lock:
        if _model is not None:
            return      # model already loaded
        
        print("\nLoading MedGemma model...\n")

        _model = AutoModelForCausalLM.from_pretrained(
            MEDGEMMA_MODEL,
            dtype=torch.bfloat16, # recommended by Google
            device_map="auto",   # spreads across available GPUs
        )
        _tokenizer = AutoTokenizer.from_pretrained(
            MEDGEMMA_MODEL,
            use_fast="False"    # uses slower processor to achieve better results
        )
        _model.eval()

        print("\nModel 27-text-it ready to receive user symptoms.\n\n")


async def ask_medgemma(prompt: str, patient_context: str = "") -> str:
    """
    Send a prompt to MedGemma agent and return the response text.

    If patient_context is provided it is prepended to the prompt, making
    the patient record visible to the model (RAG-style injection).
    """
    _load_model()

    full_prompt = f"Patient background: \n{patient_context}\n\n{prompt}" if patient_context else prompt

    messages = [
        {
            "role": "system",
            "content": """You are a medical triage assistant. Do not share personal data and keep patient privacy."
                         Classify urgency in: high, medium, or low. Also take the patient context into account if provided.
                         - high   = needs emergency care today
                         - medium = should see a doctor within a few days
                         - low    = routine appointment is fine
                         
                         Reply in one word and also provide a brief explanation of which symptoms or context features led to that classification.
                         Then suggest 1-3 doctor specialties that would be a good match for these symptoms.
                         """
        },
        {
            "role": "user",
            "content": full_prompt
        }
    ]

    try:
        inputs = _tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        ).to(_model.device, dtype=torch.bfloat16)

        input_len = inputs["input_ids"].shape[-1]

        with torch.inference_mode():
            generation = _model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False
            )
            generation = generation[0][input_len:]
        
        return _tokenizer.decode(generation, skip_special_tokens=True).strip()
    
    except Exception as exc:
        return f"\n\nMEDGEMMA UNAVAILABLE: {exc}"
