#!/usr/bin/env bash
# Box setup for the BF16 stack of abl-replication (PLAN.md s1, change log 2026-10-19).
# Runs as onstart on the rented box: fetch pinned weights, convert with the pinned
# llama.cpp commit and the exact package versions used locally, verify GGUF sha256
# against provenance/bf16_gguf_sha256.txt, and only then start the two servers.
# Idempotent; every step logs to /root/setup.log, outcome to /root/setup_status.txt.
set -uo pipefail
exec >> /root/setup.log 2>&1
set -x

COMMIT=fd55cb98fe29d3df0054d3f3e6e6f15958ea72ab
BASE_REV=4d7ae4984b7db7de8f8457170b3f1a419ee76d52
ABL_REV=bfa658000df7d734e0946595ab832abb7e34b1be
EXP_BASE=e59819d361213dc92525fc5d27a829383cbb0cd07dd81624cdbd932b7f81193b
EXP_ABL=5af66a953355d0c22fb696481983b91b925d0e0c3c88f3ba04eb68373329ef5e
G=/root/gguf; H=/root/hf; NP=4
export DEBIAN_FRONTEND=noninteractive
# The token arrives either as instance env (vast --env) or as /root/hf_token (scp'd,
# chmod 600). vast's onstart did not see the env var on 2026-10-19, hence the fallback.
if [ -z "${HUGGINGFACE_READ_TOKEN:-}" ] && [ -f /root/hf_token ]; then
  HUGGINGFACE_READ_TOKEN=$(cat /root/hf_token)
fi
export HF_TOKEN="${HUGGINGFACE_READ_TOKEN:?token missing}"

echo "SETUP_START $(date -Is)"
apt-get update -qq
apt-get install -y -qq git cmake build-essential python3-venv python3-dev python3-pip curl

# 1. llama.cpp at the pinned commit, CUDA build of llama-server only
[ -d /root/llama.cpp ] || git clone -q https://github.com/ggml-org/llama.cpp /root/llama.cpp
cd /root/llama.cpp
git fetch -q --all
git checkout -q "$COMMIT"
if [ ! -x build/bin/llama-server ]; then
  cmake -B build -DGGML_CUDA=ON -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
  cmake --build build -j"$(nproc)" --target llama-server
fi

# 2. convert venv with the exact versions used on geekom (transformers 5.19.0 etc.)
if [ ! -x /root/venv-convert/bin/python ]; then
  python3 -m venv /root/venv-convert
  /root/venv-convert/bin/pip install -q --upgrade pip
  /root/venv-convert/bin/pip install -q torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
  /root/venv-convert/bin/pip install -q transformers==5.19.0 numpy==2.2.6 safetensors==0.8.0 \
      tokenizers==0.23.3 sentencepiece==0.2.2 "huggingface_hub[hf_xet]"
fi

# 3. pinned weight downloads
mkdir -p "$H" "$G"
[ -f "$H/google/model.safetensors.index.json" ] || \
  /root/venv-convert/bin/hf download google/gemma-4-26B-A4B-it --revision "$BASE_REV" --local-dir "$H/google"
[ -f "$H/huihui/model.safetensors.index.json" ] || \
  /root/venv-convert/bin/hf download huihui-ai/Huihui-gemma-4-26B-A4B-it-abliterated --revision "$ABL_REV" --local-dir "$H/huihui"

# 4. convert both to BF16 GGUF (identical command to prep.sh)
cd /root/llama.cpp
if [ ! -s "$G/google-bf16.gguf" ]; then
  /root/venv-convert/bin/python convert_hf_to_gguf.py "$H/google" --outtype bf16 --outfile "$G/google-bf16.gguf"
fi
if [ ! -s "$G/huihui-bf16.gguf" ]; then
  /root/venv-convert/bin/python convert_hf_to_gguf.py "$H/huihui" --outtype bf16 --outfile "$G/huihui-bf16.gguf"
fi

# 5. hash gate: the box's GGUFs must be byte-identical to geekom's conversions
S_BASE=$(sha256sum "$G/google-bf16.gguf" | cut -d' ' -f1)
S_ABL=$(sha256sum "$G/huihui-bf16.gguf" | cut -d' ' -f1)
echo "$S_BASE  google-bf16.gguf" > "$G/sha256.txt"
echo "$S_ABL  huihui-bf16.gguf" >> "$G/sha256.txt"
if [ "$S_BASE" != "$EXP_BASE" ] || [ "$S_ABL" != "$EXP_ABL" ]; then
  echo "HASH_MISMATCH base=$S_BASE abl=$S_ABL" > /root/setup_status.txt
  echo "SETUP_HASH_MISMATCH $(date -Is)"
  exit 0   # keep the box alive for inspection, but never serve unverified weights
fi

# 6. start the two servers, one per GPU (base :18080 = GPU0, abl :18081 = GPU1)
mkdir -p /root/gguf
setsid env CUDA_VISIBLE_DEVICES=0 /root/llama.cpp/build/bin/llama-server \
  -m "$G/google-bf16.gguf" --host 0.0.0.0 --port 18080 -c $((4096*NP)) -np $NP \
  -t 8 -tb 16 -sp --no-webui --seed 0 > /root/server_base.log 2>&1 &
setsid env CUDA_VISIBLE_DEVICES=1 /root/llama.cpp/build/bin/llama-server \
  -m "$G/huihui-bf16.gguf" --host 0.0.0.0 --port 18081 -c $((4096*NP)) -np $NP \
  -t 8 -tb 16 -sp --no-webui --seed 0 > /root/server_abl.log 2>&1 &

echo "SETUP_OK $(date -Is) base=$S_BASE abl=$S_ABL" > /root/setup_status.txt
echo "SETUP_DONE $(date -Is)"
