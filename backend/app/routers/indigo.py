"""Indigo chemistry service endpoints consumed by Ketcher's RemoteStructService.

Most endpoints receive a JSON body like::

    {"struct": "<mol/ket/smiles>", "output_format": "chemical/x-indigo-ket", "options": {...}}

and return::

    {"struct": "<result>", "format": "chemical/x-indigo-ket"}

Options are passed through to ``Indigo.setOption`` where applicable.
"""

from __future__ import annotations

import base64
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from indigo import Indigo, IndigoException
from indigo.renderer import IndigoRenderer
from indigo.inchi import IndigoInchi

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
MIME_SDF = "chemical/x-sdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_options(ind: Indigo, options: dict[str, Any] | None) -> None:
    if not options:
        return
    for key, value in options.items():
        if value is None:
            continue
        try:
            ind.setOption(key, value)
        except IndigoException:
            pass  # ignore unknown options silently


def _load_compound(ind: Indigo, struct: str):
    """Load a molecule or reaction from any supported format."""
    for loader in (ind.loadMolecule, ind.loadReaction,
                   ind.loadQueryMolecule, ind.loadQueryReaction):
        try:
            return loader(struct)
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
    """Serialise an Indigo object to the requested format."""
    fmt = (output_format or MIME_KET).strip()

    if fmt in (MIME_KET, "application/json"):
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
    if fmt == MIME_CDXML:
        return obj.cdxml(), MIME_CDXML
    if fmt == MIME_SDF:
        return obj.sdf() if hasattr(obj, "sdf") else obj.molfile(), MIME_SDF
    if fmt == MIME_INCHI:
        return IndigoInchi(ind).getInchi(obj), MIME_INCHI
    if fmt == MIME_INCHI_AUX:
        inchi = IndigoInchi(ind)
        inchi.getInchi(obj)
        return inchi.getAuxInfo(), MIME_INCHI_AUX
    if fmt == MIME_INCHI_KEY:
        inchi = IndigoInchi(ind)
        return inchi.getInchiKey(inchi.getInchi(obj)), MIME_INCHI_KEY

    return obj.json(), MIME_KET


def _error(exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc)})


# ---------------------------------------------------------------------------
# Generic transform endpoint factory
# ---------------------------------------------------------------------------
# Most Ketcher endpoints follow the same pattern: load a structure, apply a
# mutation, serialise back.  We register them from a table instead of writing
# each one by hand.


def _make_transform(mutate: Callable):
    """Return an endpoint handler that loads a struct, applies *mutate*, and
    serialises the result."""

    async def handler(request: Request):
        body = await request.json()
        try:
            ind = Indigo()
            _set_options(ind, body.get("options"))
            obj = _load_compound(ind, body["struct"])
            mutate(obj, body)
            struct, fmt = _serialise(ind, obj, body.get("output_format"))
            return {"struct": struct, "format": fmt}
        except IndigoException as exc:
            return _error(exc)

    return handler


_TRANSFORMS: dict[str, Callable] = {
    "convert":                     lambda obj, body: None,
    "layout":                      lambda obj, body: obj.layout(),
    "clean":                       lambda obj, body: obj.clean2d(),
    "aromatize":                   lambda obj, body: obj.aromatize(),
    "dearomatize":                 lambda obj, body: obj.dearomatize(),
    "calculate_cip":               lambda obj, body: obj.addCIPStereoDescriptors(),
    "automap":                     lambda obj, body: (
        obj.automap(body.get("mode", "discard")) if _is_reaction(obj) else None
    ),
    "convert_explicit_hydrogens":  lambda obj, body: (
        obj.foldHydrogens() if body.get("mode") == "fold" else obj.unfoldHydrogens()
    ),
}

for _name, _mutate in _TRANSFORMS.items():
    router.add_api_route(
        f"/indigo/{_name}", _make_transform(_mutate), methods=["POST"],
    )


# ---------------------------------------------------------------------------
# Non-generic endpoints
# ---------------------------------------------------------------------------


@router.get("/indigo/info")
@router.get("/info")
def info():
    """Service info — called by Ketcher on init to verify availability.

    Ketcher calls ``apiPath + 'info'`` (no ``indigo/`` prefix), so we mount
    this at both ``/info`` and ``/indigo/info``.
    """
    ind = Indigo()
    return {
        "indigo_version": ind.version(),
        "imago_versions": [],
        "isAvailable": True,
    }


@router.post("/indigo/check")
async def check(request: Request):
    body = await request.json()
    try:
        ind = Indigo()
        _set_options(ind, body.get("options"))
        obj = _load_compound(ind, body["struct"])
        result: dict[str, str] = {}
        for check_type in body.get("types", []):
            try:
                result[check_type] = obj.check(check_type)
            except IndigoException:
                result[check_type] = ""
        return result
    except IndigoException as exc:
        return _error(exc)


@router.post("/indigo/calculate")
async def calculate(request: Request):
    body = await request.json()
    try:
        ind = Indigo()
        _set_options(ind, body.get("options"))
        obj = _load_compound(ind, body["struct"])

        prop_map: dict[str, Callable] = {
            "molecular-weight":  lambda o: str(o.molecularWeight()),
            "most-abundant-mass": lambda o: str(o.mostAbundantMass()),
            "monoisotopic-mass": lambda o: str(o.monoisotopicMass()),
            "gross-formula":     lambda o: o.grossFormula(),
            "mass-composition":  lambda o: o.massComposition(),
        }

        result: dict[str, str] = {}
        for prop_name in body.get("properties", {}):
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
    body = await request.json()
    try:
        ind = Indigo()
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


@router.post("/indigo/calculateMacroProperties")
async def calculate_macro_properties(request: Request):
    body = await request.json()
    try:
        ind = Indigo()
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
