import platform
import threading

from app.core.config import settings

_model_lock = threading.Lock()
_tokenizer = None
_ort_session = None


def _ensure_onnx_model():
    """Lazily download and load a lightweight quantized ONNX MiniLM-L6-v2 model (~160 MB RAM, no PyTorch)."""
    global _tokenizer, _ort_session
    if _tokenizer is None or _ort_session is None:
        with _model_lock:
            if _tokenizer is None or _ort_session is None:
                import onnxruntime as ort
                from huggingface_hub import hf_hub_download
                from tokenizers import Tokenizer

                repo_id = (
                    settings.EMBEDDING_MODEL_NAME
                    if "/" in settings.EMBEDDING_MODEL_NAME
                    else f"sentence-transformers/{settings.EMBEDDING_MODEL_NAME}"
                )
                tok_path = hf_hub_download(repo_id, "tokenizer.json")

                arch = platform.machine().lower()
                candidates = (
                    ["onnx/model_qint8_arm64.onnx", "onnx/model.onnx"]
                    if "arm" in arch or "aarch64" in arch
                    else ["onnx/model_quint8_avx2.onnx", "onnx/model.onnx"]
                )
                onnx_path = None
                for filename in candidates:
                    try:
                        onnx_path = hf_hub_download(repo_id, filename)
                        break
                    except Exception:
                        continue
                if onnx_path is None:
                    raise RuntimeError("Could not download ONNX embedding model.")

                tok = Tokenizer.from_file(tok_path)
                tok.enable_truncation(max_length=256)

                sess_opts = ort.SessionOptions()
                sess_opts.intra_op_num_threads = 1
                sess_opts.inter_op_num_threads = 1
                sess = ort.InferenceSession(
                    onnx_path, sess_opts, providers=["CPUExecutionProvider"]
                )

                _tokenizer = tok
                _ort_session = sess
    return _tokenizer, _ort_session


def generate_embedding(text: str) -> list[float]:
    """Generate a normalized 384-dimensional vector embedding locally via ONNX Runtime."""
    import numpy as np

    tokenizer, session = _ensure_onnx_model()
    cleaned = " ".join(text.split()) or "empty"
    encoded = tokenizer.encode(cleaned)

    input_ids = np.array([encoded.ids], dtype=np.int64)
    attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
    token_type_ids = np.array([encoded.type_ids], dtype=np.int64)

    outputs = session.run(
        None,
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )[0]

    mask = attention_mask[:, :, None].astype(np.float32)
    pooled = (outputs * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
    normed = pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)
    return normed[0].tolist()
