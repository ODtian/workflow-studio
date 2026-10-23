# GPU startup cache

`sm120-cu132.tar.gz` contains generated Triton, CUDA driver and model-registry cache artifacts for RTX PRO 6000 Blackwell (SM 12.0), vLLM 0.32.0, PyTorch 2.13.0+cu132, Triton 3.7.1 and Qwen3.8-27B FP8 with two MTP steps.

The workflow restores this cache before starting vLLM. The cache uses `/tmp/workflow-studio-vllm-cache` as its runtime directory. Framework cache keys select matching artifacts for each GPU kernel and model configuration.

Generated vLLM kernels follow the upstream Apache-2.0 license; Triton components follow the upstream MIT license.
