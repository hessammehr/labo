"""Indigo chemistry service endpoints consumed by Ketcher's RemoteStructService.

Every endpoint receives a JSON body like::

    {"struct": "<mol/ket/smiles>", "output_format": "chemical/x-indigo-ket", "options": {...}}

and returns::

    {"struct": "<result>", "format": "chemical/x-indigo-ket"}

Options are passed through to ``Indigo.setOption`` where applicable.
"""

from __future__ import annotations

import base64
import logging
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from indigo import Indigo, IndigoException
from indigo.renderer import IndigoRenderer
from indigo.inchi import IndigoInchi

logger = logging.getLogger(__name__)

router = APIRouter(tags=["indigo"])

# ---------------------------------------------------------------------------
# MIME types used by Ketcher
# ---------------------------------------------------------------------------

MIME_KET = "chemical/x-indigo-ket"
MIME_MOLFILE = "chemical/x-mdl-molfile"
MIME_RXNFILE = "chemical/x-mdl-rxnfile"
MIME_SMILES = "chemical/x-daylight-smiles"
MIME_SMARTS = "chemical/x-daylight-smarts"
MIME_CML = "chemical/x-cml"
MIME_INCHI = "chemical/x-inchi"
MIME_INCHI_AUX = "chemical/x-inchi-aux"
MIME_INCHI_KEY = "chemical/x-inchi-key"
MIME_CDXML = "chemical/x-cdxml"
MIME_CDX = "chemical/x-cdx"
MIME_SDF = "chemical/x-sdf"
MIME_FASTA = "chemical/x-fasta"
MIME_SEQUENCE = "chemical/x-sequence"
MIME_IDT = "chemical/x-idt"
MIME_HELM = "chemical/x-helm"

# Map of output format MIME → serialisation helper
# Each value is a callable (indigo_object) → str
_FORMAT_WRITERS: dict[str, Any] = {}  # populated in _serialise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _indigo_session():
    """Create a fresh Indigo instance per request (thread-safe)."""
    ind = Indigo()
    yield ind


def _set_options(ind: Indigo, options: dict[str, Any] | None) -> None:
    if not options:
        return
    for key, value in options.items():
        if value is None:
            continue
        # Some options are ketcher-internal and not real Indigo options
        try:
            ind.setOption(key, value)
        except IndigoException:
            pass  # ignore unknown options silently


def _load_compound(ind: Indigo, struct: str):
    """Load a molecule or reaction from any supported format."""
    # Try molecule first, then reaction
    try:
        return ind.loadMolecule(struct)
    except IndigoException:
        pass
    try:
        return ind.loadReaction(struct)
    except IndigoException:
        pass
    try:
        return ind.loadQueryMolecule(struct)
    except IndigoException:
        pass
    try:
        return ind.loadQueryReaction(struct)
    except IndigoException:
        pass
    raise IndigoException("Cannot load structure")


def _is_reaction(obj) -> bool:
    try:
        obj.countReactants()
        return True
    except IndigoException:
        return False


def _serialise(ind: Indigo, obj, output_format: str | None) -> tuple[str, str]:
    """Serialise an Indigo object to the requested format.

    Returns (struct_string, mime_type).
    """
    fmt = (output_format or MIME_KET).strip()

    if fmt == MIME_KET or fmt == "application/json":
        return obj.json(), MIME_KET
    if fmt == MIME_MOLFILE:
        return obj.molfile(), MIME_MOLFILE
    if fmt == MIME_RXNFILE:
        return obj.rxnfile(), MIME_RXNFILE
    if fmt in (MIME_SMILES, "chemical/x-chemaxon-cxsmiles"):
        return obj.smiles(), MIME_SMILES
    if fmt == MIME_SMARTS:
        return obj.smarts(), MIME_SMARTS
    if fmt == MIME_CML:
        return obj.cml(), MIME_CML
    if fmt == MIME_INCHI:
        inchi = IndigoInchi(ind)
        return inchi.getInchi(obj), MIME_INCHI
    if fmt == MIME_INCHI_AUX:
        inchi = IndigoInchi(ind)
        inchi.getInchi(obj)
        return inchi.getAuxInfo(), MIME_INCHI_AUX
    if fmt == MIME_INCHI_KEY:
        inchi = IndigoInchi(ind)
        inchi_str = inchi.getInchi(obj)
        return inchi.getInchiKey(inchi_str), MIME_INCHI_KEY
    if fmt == MIME_CDXML:
        return obj.cdxml(), MIME_CDXML
    if fmt == MIME_SDF:
        return obj.sdf() if hasattr(obj, "sdf") else obj.molfile(), MIME_SDF

    # Default to KET
    return obj.json(), MIME_KET


async def _body(request: Request) -> dict:
    return await request.json()


def _error(exc: Exception) -> JSONResponse:
    return JSONResponse(status_code= 400, content={"error": str(exc)})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/indigo/info")
@router.get("/info")
def info():
    """Service info — called by Ketcher on init to verify availability.

    Ketcher calls ``apiPath + 'info'`` (no ``indigo/`` prefix), so we mount
    this at both ``/info`` and ``/indigo/info``.
    """
    with _indigo_session() as ind:
        return {
            "indigo_version": ind.version(),
            "imago_versions": [],
            "isAvailable": True,
        }


@router.post("/indigo/convert")
async def convert(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/layout")
async def layout(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            obj.layout()
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/clean")
async def clean(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            obj.clean2d()
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/aromatize")
async def aromatize(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            obj.aromatize()
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/dearomatize")
async def dearomatize(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            obj.dearomatize()
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/calculate_cip")
async def calculate_cip(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            obj.cipOrderAtoms()
            obj.cipOrderBonds()
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/automap")
async def automap(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            if _is_reaction(obj):
                obj.automap(body.get("mode", "discard"))
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/check")
async def check(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            types = body.get("types", [])
            result: dict[str, str] = {}
            for check_type in types:
                try:
                    result[check_type] = obj.check(check_type)
                except IndigoException:
                    result[check_type] = ""
            return result
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/calculate")
async def calculate(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            properties = body.get("properties", {})
            result: dict[str, str] = {}

            prop_map = {
                "molecular-weight": lambda o: str(o.molecularWeight()),
                "most-abundant-mass": lambda o: str(o.mostAbundantMass()),
                "monoisotopic-mass": lambda o: str(o.monoisotopicMass()),
                "gross-formula": lambda o: o.grossFormula(),
                "mass-composition": lambda o: o.massComposition(),
            }

            for prop_name in properties:
                fn = prop_map.get(prop_name)
                if fn:
                    try:
                        result[prop_name] = fn(obj)
                    except IndigoException:
                        result[prop_name] = ""
                else:
                    result[prop_name] = ""

            return result
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/render")
async def render(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            options = body.get("options", {})
            output_format = options.pop("render-output-format", "svg")

            obj = _load_compound(ind, body["struct"])

            # IndigoRenderer must be created before setting render-* options
            renderer = IndigoRenderer(ind)
            ind.setOption("render-output-format", output_format)
            _set_options(ind, options)

            raw = renderer.renderToBuffer(obj)
            raw_bytes = raw.tobytes() if hasattr(raw, "tobytes") else bytes(raw)

            # Ketcher's generateImage() always runs atob() on the response,
            # so every format (including SVG) must be base64-encoded.
            return PlainTextResponse(
                content=base64.b64encode(raw_bytes).decode("ascii"),
                media_type="text/plain",
            )
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/convert_explicit_hydrogens")
async def convert_explicit_hydrogens(request: Request):
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            mode = body.get("mode", "auto")
            if mode == "fold":
                obj.foldHydrogens()
            else:
                obj.unfoldHydrogens()
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/calculateMacroProperties")
async def calculate_macro_properties(request: Request):
    """Macro-molecule properties — best-effort."""
    body = await _body(request)
    try:
        with _indigo_session() as ind:
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            result: dict[str, str] = {}
            try:
                result["molecular-weight"] = str(obj.molecularWeight())
            except IndigoException:
                pass
            try:
                result["gross-formula"] = obj.grossFormula()
            except IndigoException:
                pass
            return result
    except IndigoException as exc:
        return _error(exc)
