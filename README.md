# mini

A minimal coding agent: four tools (bash, read, edit, write) in one chat-completions loop, in
86 lines of Python. Built to learn which parts of a coding-agent harness actually matter when the
model is a local open-weights model (Qwen 3.8 served by vLLM behind a LiteLLM gateway).

```bash
docker run --rm -i -v "$PWD:/work" -w /work -v /tmp/mini-out:/out \
  -e LITELLM_KEY=... -e BASE_URL=http://host:4000/v1 -e MODEL=your-model \
  python-with-openai python3 /path/to/mini_harness.py "your task"
```

Run it only in a container that mounts nothing but the work folder: it executes whatever shell
commands the model asks for.
