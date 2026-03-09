# Labo
_Labo_ is a minimalist laboratory notebook for trivial self-hosting, online data capture and in situ data analysis. It is almost exclusively LLM-written; only the documentation is handwritten by a human.

## Dependencies
- tailscale
- bun
- uv

## How to run
```
make install
```

To test locally
```
make dev
```

To serve over HTTPS using tailscale funnel:
```
make build-frontend
make serve
```
