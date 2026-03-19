<p align="center">
  <img src="frontend/public/logo.svg" alt="Labo" width="300" />
</p>

Labo's emphasis is on enabling continuous data acquisition in the lab, seamless access to data in notebooks like Jupyter and Marimo, and trivial setup with minimal dependencies.

## How to run Labo
There are only two core requirements for Labo: uv and bun. DOCX and PDF export relies on pandoc. Once these are installed

```sh
make install
make build-frontend
make run
```

## Serving over HTTPS using Tailscale
For actual deployment, using Tailscale serve is recommended. With Tailscale installed

```sh
make serve
```

## Development with hot code reloading on frontend and backend
```sh
make dev
```
