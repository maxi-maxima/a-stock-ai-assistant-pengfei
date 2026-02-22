import os
import sys


def _get_env(name, default=""):
    val = os.getenv(name, default)
    return val.strip() if isinstance(val, str) else val


def main():
    model = _get_env("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    target_dir = _get_env("EMBEDDING_MODEL_DIR", os.path.join("data", "embeddings", model.replace("/", "_")))
    hf_endpoint = _get_env("HF_ENDPOINT", "")
    if hf_endpoint:
        os.environ.setdefault("HF_ENDPOINT", hf_endpoint)
        os.environ.setdefault("HUGGINGFACE_HUB_BASE_URL", hf_endpoint)

    try:
        from huggingface_hub import snapshot_download
    except Exception:
        print("huggingface_hub not installed. Install via: pip install huggingface_hub", file=sys.stderr)
        return 2

    print(f"Downloading model: {model}")
    print(f"Target dir: {target_dir}")
    try:
        snapshot_download(repo_id=model, local_dir=target_dir, local_dir_use_symlinks=False)
    except Exception as e:
        print(f"Download failed: {e}", file=sys.stderr)
        return 1

    print("Done. Set EMBEDDING_MODEL_PATH to:")
    print(target_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
