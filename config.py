import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MODELS_ROOT = Path(os.environ.get("MMFOOD_MODELS_ROOT", REPO_ROOT / "Models"))

VOCAB_PATH = Path(os.environ.get(
    "MMFOOD_VOCAB_PATH", REPO_ROOT / "data" / "vocab" / "cleaned_ingredients_n_v2.txt"
))

CORRECTIONS_DB_PATH = Path(os.environ.get(
    "MMFOOD_CORRECTIONS_DB", REPO_ROOT / "data" / "corrections_db.jsonl"
))

NER_MODEL_DIR = Path(os.environ.get(
    "MMFOOD_NER_MODEL_DIR", MODELS_ROOT / "ingredient_ner" / "model"
))
RE_MODEL_DIR = Path(os.environ.get(
    "MMFOOD_RE_MODEL_DIR", MODELS_ROOT / "relation_extraction" / "finetuned_re_model"
))
SUSPICIOUS_MODEL_PATH = Path(os.environ.get(
    "MMFOOD_SUSPICIOUS_MODEL_PATH", MODELS_ROOT / "suspicious_ingredient" / "best_model_classification.pt"
))
SUSPICIOUS_EMBEDDINGS_PATH = Path(os.environ.get(
    "MMFOOD_SUSPICIOUS_EMBEDDINGS_PATH", MODELS_ROOT / "suspicious_ingredient" / "ingredient_embeddings.pt"
))

NLI_MODEL_NAME = os.environ.get(
    "NLI_MODEL_NAME", "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
)

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")
LLM_MODEL = os.environ.get("LLM_MODEL")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")

AUTO_CORRECT_ENABLED = os.environ.get("AUTO_CORRECT_ENABLED", "false").strip().lower() == "true"

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://host.docker.internal:27017")
CORRECTION_TOOL_PORT = int(os.environ.get("CORRECTION_TOOL_PORT", "5000"))
