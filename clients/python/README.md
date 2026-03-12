# Labo Python Client

Pathlib-style access to [Labo](https://github.com/hessammehr/labo) lab notebook attachments.

## Install

```bash
pip install labo
```

## Quick start

```python
from labo import Resource

# Connect with a scoped API token (create one in the Labo sharing modal)
r = Resource("https://my-labo.example.com", "labo_abc123...")

# List entries in a notebook
for entry in r.iterdir():
    print(entry.name, entry.is_dir())

# Read a file
data = (r / "Experiment 1" / "data.csv").read_text()

# Write a file
(r / "Experiment 1" / "results.csv").write_text("col1,col2\n1,2\n")

# Binary read/write
img = (r / "Experiment 1" / "photo.png").read_bytes()
(r / "Experiment 1" / "output.bin").write_bytes(b"\x00\x01\x02")
```

## Streaming

For large files or live data acquisition:

```python
# Streaming read
with (r / "Experiment 1" / "big_file.bin").open("rb") as f:
    for chunk in f:
        process(chunk)

# Streaming write (data sent on close)
with (r / "Experiment 1" / "live_data.csv").open("w") as f:
    f.write("timestamp,value\n")
    for ts, val in acquire_data():
        f.write(f"{ts},{val}\n")
```

## Path operations

`Resource` implements `os.PathLike` and supports familiar path operations:

```python
file = r / "Experiment 1" / "data.csv"

file.name       # "data.csv"
file.stem       # "data"
file.suffix     # ".csv"
file.parent     # Resource pointing to "Experiment 1"
file.parts      # ("Experiment 1", "data.csv")
```

## Context manager

```python
with Resource("https://my-labo.example.com", "labo_...") as r:
    data = (r / "entry" / "file.csv").read_text()
# HTTP client is closed automatically
```
